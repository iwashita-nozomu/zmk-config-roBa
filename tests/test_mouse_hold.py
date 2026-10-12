"""Mouse-entry bindings and the production shared hold; not a Zephyr/HID test."""

import itertools
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import test_keymap as km

ROOT = Path(__file__).resolve().parents[1]

FAKE = r'''
#pragma once
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <pthread.h>
#include <errno.h>
#define DT_HAS_COMPAT_STATUS_OKAY(c) 1
#define DT_NUM_INST_STATUS_OKAY(c) 1
#define DT_INST_PROP(i,p) MANUAL_LAYER
#define ZMK_KEYMAP_LAYERS_LEN 10
#define BUILD_ASSERT(x) _Static_assert(x, #x)
#define ARG_UNUSED(x) (void)(x)
#define IS_ENABLED(x) 0
#define K_FOREVER -1
struct k_mutex { pthread_mutex_t mutex; };
#define K_MUTEX_DEFINE(n) struct k_mutex n = {PTHREAD_MUTEX_INITIALIZER}
static int k_mutex_lock(struct k_mutex *m, int w) {
    (void)w; int e = pthread_mutex_lock(&m->mutex); assert(e == 0); return e;
}
static int k_mutex_unlock(struct k_mutex *m) {
    int e = pthread_mutex_unlock(&m->mutex); assert(e == 0); return e;
}
struct zmk_behavior_binding { const char *behavior_dev; uint32_t param1, param2; };
struct zmk_behavior_binding_event { uint32_t position; int64_t timestamp; };
struct behavior_driver_api {
    int (*binding_pressed)(struct zmk_behavior_binding *, struct zmk_behavior_binding_event);
    int (*binding_released)(struct zmk_behavior_binding *, struct zmk_behavior_binding_event);
};
struct device { const struct behavior_driver_api *api; };
#define BEHAVIOR_DT_INST_DEFINE(i,init,pm,data,cfg,lvl,prio,a) \
    static const struct device hold_device = {.api = a}
static bool active[10];
static uint8_t mapped_layer = MANUAL_LAYER;
static int failure;
static unsigned on_count, off_count;
static uint8_t zmk_keymap_layer_index_to_id(uint8_t n) { assert(n == MANUAL_LAYER); return mapped_layer; }
static int zmk_keymap_layer_activate(uint8_t n) {
    assert(n < 10); if (failure) return failure; active[n] = true; ++on_count; return 0;
}
static int zmk_keymap_layer_deactivate(uint8_t n) {
    assert(n < 10); if (failure) return failure; active[n] = false; ++off_count; return 0;
}
'''

REPLAY = r'''
#include PRODUCTION_SOURCE
static int invoke(uint32_t position, bool pressed) {
    struct zmk_behavior_binding b = {.behavior_dev = "mouse_hold"};
    struct zmk_behavior_binding_event e = {.position = position};
    return pressed ? hold_device.api->binding_pressed(&b,e) : hold_device.api->binding_released(&b,e);
}
int main(void) {
    const uint32_t sources[] = {6, UINT32_MAX - 1};
    for (unsigned i=0; i<2; ++i) {
        assert(invoke(sources[i],true) == 0 && active[MANUAL_LAYER]);
        assert(invoke(sources[i],false) == 0 && !active[MANUAL_LAYER]);
    }
    for (unsigned first=0; first<2; ++first) {
        for (unsigned release_first=0; release_first<2; ++release_first) {
            unsigned starts = on_count, stops = off_count;
            active[2] = true; active[4] = true; active[8] = true;
            assert(invoke(sources[first],true) == 0);
            assert(invoke(sources[1-first],true) == 0);
            assert(invoke(sources[release_first],false) == 0);
            assert(active[MANUAL_LAYER]); /* Keep I/O clicks after either release. */
            assert(on_count == starts+1 && off_count == stops);
            assert(invoke(sources[1-release_first],false) == 0);
            assert(!active[MANUAL_LAYER]);
            assert(off_count == stops+1);
            assert(active[2] && active[4] && active[8]);
        }
    }
    for (unsigned i=0; i<1000; ++i) {
        assert(invoke(sources[1],true) == 0);
        assert(invoke(sources[0],true) == 0);
        assert(invoke(sources[1],false) == 0 && active[MANUAL_LAYER]);
        assert(invoke(sources[0],false) == 0 && !active[MANUAL_LAYER]);
    }
    assert(invoke(6,true) == 0);
    mapped_layer = 5;
    assert(invoke(6,false) == 0 && !active[MANUAL_LAYER]);
    assert(invoke(6,true) == 0 && active[5]);
    assert(invoke(6,false) == 0 && !active[5]);
    mapped_layer = MANUAL_LAYER;
    assert(invoke(6,false) == -EINVAL);
    failure = -EIO;
    assert(invoke(6,true) == -EIO && !active[MANUAL_LAYER]);
    failure = 0;
    assert(invoke(6,true) == 0);
    failure = -EIO;
    assert(invoke(6,false) == -EIO && active[MANUAL_LAYER]);
    failure = 0;
    assert(invoke(6,false) == 0 && !active[MANUAL_LAYER]);
    return 0;
}
'''


class MouseHoldTests(unittest.TestCase):
    def test_u_clicks_share_the_combo_owner_without_changing_tap_timing(self):
        body = re.search(r"(?s)u_mouse:\s*\w+\s*\{(.*?)\};", km.EXPANDED)[1]
        for setting in ('flavor = "tap-preferred";', 'tapping-term-ms = <200>;',
                        'quick-tap-ms = <0>;', 'bindings = <&mouse_hold>, <&kp>;'):
            self.assertIn(setting, body)
        self.assertEqual(km.LAYERS["BASE"][6], "&u_mouse 0 U")
        for layer in ("MOUSE", "MOUSE_HOLD", "SLOW", "SCROLL"):
            self.assertEqual([km.resolve({"BASE",layer}, p) for p in (6,7,8)],
                             ["&mouse_hold", "&mkp MB1", "&mkp MB2"])
        self.assertNotRegex(km.EXPANDED, r"&(?:mo|lt) 3\b")
        owner = re.search(r"(?s)mouse_hold:\s*\w+\s*\{(.*?)\};", km.EXPANDED)[1]
        self.assertIn('layer = <3>;', owner)
        self.assertIn('#binding-cells = <0>;', owner)

    def test_jk_entry_and_middle_click_have_disjoint_layer_domains(self):
        entry = re.search(r"(?s)\bmouse_entry\s*\{(.*?)\};", km.EXPANDED)[1]
        click = re.search(r"(?s)\bmiddle_click\s*\{(.*?)\};", km.EXPANDED)[1]
        for body in (entry, click):
            self.assertIn('timeout-ms = <50>;', body)
            self.assertIn('key-positions = <18 19>;', body)
        self.assertIn('bindings = <&mouse_hold>;', entry)
        self.assertIn('slow-release;', entry)
        self.assertNotIn('slow-release;', click)
        self.assertIn('bindings = <&mkp MB3>;', click)
        entry_layers = set(map(int, re.search(r"layers = <(.*?)>", entry)[1].split()))
        click_layers = set(map(int, re.search(r"layers = <(.*?)>", click)[1].split()))
        self.assertEqual(entry_layers, {0,1})
        self.assertEqual(click_layers, {2,3,4,8})
        for flags in itertools.product((False,True), repeat=9):
            highest = max([0]+[i for i,on in enumerate(flags,1) if on])
            self.assertLessEqual((highest in entry_layers)+(highest in click_layers), 1)
            if highest in (5,6,7,9):
                self.assertNotIn(highest, entry_layers | click_layers)

    def test_production_hold_preserves_remaining_owners(self):
        source = ROOT / "src/behavior_mouse_hold.c"
        owner = re.search(r"(?s)mouse_hold:\s*\w+\s*\{(.*?)\};", km.EXPANDED)[1]
        layer = int(re.search(r"layer = <(\d+)>", owner)[1])
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            (temp / "fake.h").write_text(FAKE)
            for name in re.findall(r"^#include <((?:drivers|zephyr|zmk)/[^>]+)>",
                                   source.read_text(), re.MULTILINE):
                header = temp / name
                header.parent.mkdir(parents=True, exist_ok=True)
                header.write_text('#include "fake.h"\n')
            (temp / "replay.c").write_text(REPLAY)
            subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra",
                            "-Werror", "-pthread", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                            "-I", str(temp), f"-DMANUAL_LAYER={layer}",
                            f'-DPRODUCTION_SOURCE="{source}"', str(temp / "replay.c"),
                            "-o", str(temp / "replay")], check=True)
            subprocess.run([str(temp / "replay")], check=True)


if __name__ == "__main__":
    unittest.main()
