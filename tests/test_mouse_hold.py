"""Pointing-entry bindings and production shared holds; not a Zephyr/HID test."""

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
#include <string.h>
#include <stdio.h>
#define DT_HAS_COMPAT_STATUS_OKAY(c) 1
#define DT_NUM_INST_STATUS_OKAY(c) 2
#define PROP_0_layer MANUAL_LAYER
#define PROP_1_layer SLOW_LAYER
#define DT_INST_PROP(i,p) PROP_##i##_##p
#define DT_INST_FOREACH_STATUS_OKAY(fn) fn(0) fn(1)
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
struct device { const struct behavior_driver_api *api; void *data; const void *config; };
extern const struct device hold_device_0, hold_device_1;
#define BEHAVIOR_DT_INST_DEFINE(i,init,pm,d,cfg,lvl,prio,a) \
    const struct device hold_device_##i = {.api = a, .data = d, .config = cfg}
static const struct device *zmk_behavior_get_binding(const char *name) {
    if (strcmp(name, "mouse_hold") == 0) return &hold_device_0;
    assert(strcmp(name, "slow_hold") == 0); return &hold_device_1;
}
static bool active[10];
static uint8_t mapped_mouse = MANUAL_LAYER, mapped_slow = SLOW_LAYER;
static int failure;
static unsigned on_count[10], off_count[10];
static uint8_t zmk_keymap_layer_index_to_id(uint8_t n) {
    assert(n == MANUAL_LAYER || n == SLOW_LAYER);
    return n == MANUAL_LAYER ? mapped_mouse : mapped_slow;
}
static int zmk_keymap_layer_activate(uint8_t n) {
    assert(n < 10); if (failure) return failure; active[n] = true; ++on_count[n]; return 0;
}
static int zmk_keymap_layer_deactivate(uint8_t n) {
    assert(n < 10); if (failure) return failure; active[n] = false; ++off_count[n]; return 0;
}
'''

REPLAY = r'''
#include PRODUCTION_SOURCE
static const uint32_t sources[] = {13, 6, UINT32_MAX - 1, 14, 21};
static int invoke(unsigned source, bool pressed) {
    struct zmk_behavior_binding b = {.behavior_dev = source < 3 ? "mouse_hold" : "slow_hold"};
    struct zmk_behavior_binding_event e = {.position = sources[source]};
    const struct device *dev = zmk_behavior_get_binding(b.behavior_dev);
    return pressed ? dev->api->binding_pressed(&b,e) : dev->api->binding_released(&b,e);
}
static unsigned orders[120][5], order_count;
static void permute(unsigned *order, unsigned n, unsigned used) {
    if (n == 5) { memcpy(orders[order_count++], order, sizeof(orders[0])); return; }
    for (unsigned i = 0; i < 5; ++i) {
        if (!(used & (1u << i))) { order[n] = i; permute(order, n+1, used | (1u << i)); }
    }
}
static void check_held(unsigned held) {
    assert(active[MANUAL_LAYER] == !!(held & 7u));
    assert(active[SLOW_LAYER] == !!(held & 24u));
    assert(active[2] && active[5] && active[8]); /* AUTO/NUM/SCROLL are independent. */
}
int main(void) {
    for (unsigned i = 0; i < 5; ++i) {
        unsigned layer = i < 3 ? MANUAL_LAYER : SLOW_LAYER;
        assert(invoke(i,true) == 0 && active[layer]);
        assert(invoke(i,false) == 0 && !active[layer]);
    }
    unsigned order[5]; permute(order,0,0); assert(order_count == 120);
    for (unsigned p = 0; p < order_count; ++p) {
        for (unsigned r = 0; r < order_count; ++r) {
            unsigned held = 0;
            unsigned starts_mouse = on_count[MANUAL_LAYER], starts_slow = on_count[SLOW_LAYER];
            unsigned stops_mouse = off_count[MANUAL_LAYER], stops_slow = off_count[SLOW_LAYER];
            active[2] = true; active[5] = true; active[8] = true;
            for (unsigned n = 0; n < 5; ++n) {
                unsigned s = orders[p][n];
                assert(invoke(s,true) == 0); held |= 1u << s; check_held(held);
            }
            for (unsigned n = 0; n < 5; ++n) {
                unsigned s = orders[r][n];
                assert(invoke(s,false) == 0); held &= ~(1u << s); check_held(held);
            }
            assert(on_count[MANUAL_LAYER] == starts_mouse+1 && off_count[MANUAL_LAYER] == stops_mouse+1);
            assert(on_count[SLOW_LAYER] == starts_slow+1 && off_count[SLOW_LAYER] == stops_slow+1);
        }
    }
    puts("PASS: 120 press orders x 120 release orders; independent F/U/JK and G/right SLOW");
    memset(active,0,sizeof(active));
    for (unsigned i = 0; i < 1000; ++i) {
        assert(invoke(2,true) == 0); assert(invoke(0,true) == 0); assert(invoke(1,true) == 0);
        assert(invoke(2,false) == 0 && active[MANUAL_LAYER]);
        assert(invoke(0,false) == 0 && active[MANUAL_LAYER]);
        assert(invoke(1,false) == 0 && !active[MANUAL_LAYER]);
        assert(invoke(3,true) == 0); assert(invoke(4,true) == 0);
        assert(invoke(3,false) == 0 && active[SLOW_LAYER]);
        assert(invoke(4,false) == 0 && !active[SLOW_LAYER]);
    }
    puts("PASS: 1000 mouse and slow handoffs without stuck layers");
    assert(invoke(0,true) == 0 && invoke(3,true) == 0);
    mapped_mouse = 5; mapped_slow = 6;
    assert(invoke(0,false) == 0 && !active[MANUAL_LAYER]);
    assert(invoke(3,false) == 0 && !active[SLOW_LAYER]);
    assert(invoke(0,true) == 0 && active[5]); assert(invoke(3,true) == 0 && active[6]);
    assert(invoke(0,false) == 0 && !active[5] && active[6]);
    assert(invoke(3,false) == 0 && !active[6]);
    mapped_mouse = MANUAL_LAYER; mapped_slow = SLOW_LAYER;
    for (unsigned i = 0; i < 5; ++i) {
        unsigned layer = i < 3 ? MANUAL_LAYER : SLOW_LAYER;
        assert(invoke(i,false) == -EINVAL);
        failure = -EIO;
        assert(invoke(i,true) == -EIO && !active[layer]);
        failure = 0; assert(invoke(i,true) == 0);
        failure = -EIO; assert(invoke(i,false) == -EIO && active[layer]);
        failure = 0; assert(invoke(i,false) == 0 && !active[layer]);
    }
    puts("PASS: both instances retain acquired stable IDs and propagate layer failures");
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
        self.assertEqual(km.LAYERS["BASE"][13], "&u_mouse 0 F")
        for layer in ("MOUSE", "MOUSE_HOLD", "SLOW", "SCROLL"):
            self.assertEqual([km.resolve({"BASE", layer}, p) for p in (6, 7, 8, 13)],
                             ["&mouse_hold", "&mkp MB1", "&mkp MB2", "&mouse_hold"])
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
        self.assertEqual(entry_layers, {0, 1})
        self.assertEqual(click_layers, {2, 3, 4, 8})
        for flags in itertools.product((False, True), repeat=9):
            highest = max([0] + [i for i, on in enumerate(flags, 1) if on])
            self.assertLessEqual((highest in entry_layers) + (highest in click_layers), 1)
            if highest in (5, 6, 7, 9):
                self.assertNotIn(highest, entry_layers | click_layers)

    def test_production_hold_preserves_remaining_owners(self):
        source = ROOT / "src/behavior_mouse_hold.c"
        layers = []
        for owner in ("mouse_hold", "slow_hold"):
            body = re.search(rf"(?s){owner}:\s*\w+\s*\{{(.*?)\}};", km.EXPANDED)[1]
            layers.append(int(re.search(r"layer = <(\d+)>", body)[1]))
        self.assertEqual(layers, [3, 4])
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
                            "-I", str(temp), f"-DMANUAL_LAYER={layers[0]}", f"-DSLOW_LAYER={layers[1]}",
                            f'-DPRODUCTION_SOURCE="{source}"', str(temp / "replay.c"),
                            "-o", str(temp / "replay")], check=True)
            subprocess.run([str(temp / "replay")], check=True)


if __name__ == "__main__":
    unittest.main()
