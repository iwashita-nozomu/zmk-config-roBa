"""Chord configuration and the production Shift adapter; not a Zephyr/HID test."""

import itertools
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import test_keymap as km

ROOT = Path(__file__).resolve().parents[1]


def node(name):
    return re.search(rf"(?s)\b{name}:\s*\w+\s*\{{(.*?)\}};", km.EXPANDED)[1]


def decision(name, elapsed, other=None, released=False):
    """Reference model of documented hold-preferred positional semantics.

    One deciding event only; this does not run ZMK capture, combos or its timer.
    A disallowed first overlap chooses tap, not merely a longer wait for hold.
    """
    body = node(name)
    term = int(re.search(r"tapping-term-ms = <(\d+)>;", body)[1])
    if elapsed >= term:
        return "hold"
    if other is not None:
        positions = re.search(r"hold-trigger-key-positions = <(.*?)>;", body)
        if positions and other not in set(map(int, positions[1].split())):
            return "tap"
        if 'flavor = "hold-preferred";' in body:
            return "hold"
    return "tap" if released else "undecided"


FAKE = r'''
#pragma once
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#define DT_HAS_COMPAT_STATUS_OKAY(c) 1
#define DT_NUM_INST_STATUS_OKAY(c) 1
#define DT_INST_PROP_LEN(i,p) 1
#define DT_INST_PHANDLE_BY_IDX(i,p,n) z_sticky
#define DEVICE_DT_NAME(n) "z_sticky"
#define DT_INST_PHA_BY_IDX(i,p,n,c) 0x700e1
#define BUILD_ASSERT(x) _Static_assert(x, #x)
#define ARG_UNUSED(x) (void)(x)
#define IS_ENABLED(x) 0
struct zmk_behavior_binding { const char *behavior_dev; uint32_t param1, param2; };
struct zmk_behavior_binding_event { uint32_t position; int64_t timestamp; uint8_t source, layer; };
struct behavior_driver_api {
    int (*binding_pressed)(struct zmk_behavior_binding *, struct zmk_behavior_binding_event);
    int (*binding_released)(struct zmk_behavior_binding *, struct zmk_behavior_binding_event);
};
struct device { const struct behavior_driver_api *api; };
#define BEHAVIOR_DT_INST_DEFINE(i,init,pm,data,cfg,lvl,prio,a) \
    static const struct device shift_device = {.api = a}
static int64_t now_ms;
static int64_t k_uptime_get(void) { return now_ms; }
static unsigned calls;
static int result;
static bool shift_down;
static struct zmk_behavior_binding_event forwarded;
static int zmk_behavior_invoke_binding(struct zmk_behavior_binding *b,
                                       struct zmk_behavior_binding_event event, bool down) {
    assert(strcmp(b->behavior_dev, "z_sticky") == 0);
    assert(b->param1 == 0x700e1 && b->param2 == 0);
    forwarded = event; shift_down = down; ++calls;
    return result;
}
'''

REPLAY = r'''
#include PRODUCTION_SOURCE
int main(void) {
    struct zmk_behavior_binding b = {.behavior_dev = "shift_hold"};
    /* Hold-tap supplies its old press timestamp even at a much later release. */
    struct zmk_behavior_binding_event e = {.position=22, .timestamp=1000, .source=1, .layer=3};
    const int64_t press_times[] = {1010, 1250, INT64_C(10000000000)};
    for (unsigned i=0; i<3; ++i) {
        now_ms = press_times[i]; result = 0;
        unsigned before = calls;
        assert(shift_device.api->binding_pressed(&b,e) == 0);
        /* An interrupting key handled next sees Shift without draining a queue. */
        assert(shift_down && calls == before+1);
        assert(forwarded.timestamp == now_ms);
        assert(forwarded.position == 22 && forwarded.source == 1 && forwarded.layer == 3);
        now_ms += 600;
        assert(shift_device.api->binding_released(&b,e) == 0);
        assert(!shift_down && calls == before+2);
        assert(forwarded.timestamp == now_ms && forwarded.timestamp+200 == now_ms+200);
        assert(e.timestamp == 1000); /* Do not mutate the caller's event. */
    }
    result = -12;
    assert(shift_device.api->binding_pressed(&b,e) == -12);
    assert(shift_device.api->binding_released(&b,e) == -12);
    return 0;
}
'''


class ChordTests(unittest.TestCase):
    def test_chords_keep_single_hold_terms_and_system_time_only(self):
        terms = {"z_hold": 250, "layer_chord": 200, "nav_hold": 200,
                 "ime_ctrl": 200, "u_mouse": 200, "slow_tap": 200, "scroll_tap": 200}
        for name, term in terms.items():
            with self.subTest(name=name):
                self.assertIn('flavor = "hold-preferred";', node(name))
                self.assertIn('quick-tap-ms = <0>;', node(name))
                self.assertEqual(decision(name, term-1), "undecided")
                self.assertEqual(decision(name, term), "hold")
                self.assertEqual(decision(name, 10, released=True), "tap")
                self.assertNotIn('hold-while-undecided', node(name))
        self.assertEqual(km.LAYERS["BASE"][40], "&lt 9 ESCAPE")
        self.assertNotRegex(km.SOURCE, r"&lt\s*\{")  # Retain ZMK's timer-only default.
        self.assertRegex(km.SOURCE, r'(?s)&mt\s*\{\s*flavor = "hold-preferred";')
        self.assertIn('release-after-ms = <200>;', node("z_sticky"))
        self.assertIn('quick-release;', node("z_sticky"))
        self.assertIn('ignore-modifiers;', node("z_sticky"))

    def test_pointer_chords_are_limited_and_do_not_redefine_combos(self):
        allowed = {6, 7, 8, 13, 14, 21, 30}
        for name in ("u_mouse", "slow_tap", "scroll_tap"):
            actual = re.search(r"hold-trigger-key-positions = <(.*?)>;", node(name))[1]
            self.assertEqual(set(map(int, actual.split())), allowed)
            for p in range(43):
                self.assertEqual(decision(name, 10, other=p), "hold" if p in allowed else "tap")
        for name in ("z_hold", "layer_chord", "nav_hold", "ime_ctrl"):
            self.assertNotIn('hold-trigger-key-positions', node(name))
            for p in range(43):
                self.assertEqual(decision(name, 10, other=p), "hold")
        # Native combo priority/recognition is not simulated by this model.
        self.assertEqual(len(re.findall(r"(?m)^\s*key-positions\s*=", km.EXPANDED)), 7)

    def test_requested_first_key_layer_lookups(self):
        examples = ((38, "layer_chord", 11, "NUM", "&kp NUMBER_4"),
                    (41, "layer_chord", 42, "FUNCTION", "&kp DEL"),
                    (39, "nav_hold", 17, "NAV", "&kp LEFT_ARROW"),
                    (13, "u_mouse", 7, "MOUSE_HOLD", "&mkp MB1"),
                    (6, "u_mouse", 7, "MOUSE_HOLD", "&mkp MB1"),
                    (7, "u_mouse", 8, "MOUSE_HOLD", "&mkp MB2"),
                    (14, "slow_tap", 30, "SLOW", "&mo 8"),
                    (30, "scroll_tap", 14, "SCROLL", "&slow_hold"))
        for source, behavior, target, layer, expected in examples:
            with self.subTest(source=source, target=target):
                self.assertTrue(km.resolve({"BASE"}, source).startswith("&"+behavior+" "))
                self.assertEqual(decision(behavior, 10, other=target), "hold")
                self.assertEqual(km.resolve({"BASE", layer}, target), expected)
        self.assertEqual(decision("u_mouse", 10, other=10), "tap")  # F->A types.

    def test_ime_ctrl_is_separate_from_lang_toggle_and_preserves_mouse(self):
        body = node("ime_ctrl")
        self.assertIn('bindings = <&kp>, <&ime_toggle>;', body)
        self.assertNotIn('sticky', body)
        for flags in itertools.product((False, True), repeat=9):
            active = {"BASE"} | {name for name, flag in zip(km.LAYER_NAMES[1:], flags) if flag}
            lang = "LANG2" if "IME_ALT" in active else "LANG1"
            self.assertEqual(km.resolve(active, 37), "&ime_ctrl LEFT_CONTROL " + lang)
        excluded = re.search(r"excluded-positions = <(.*?)>;", km.EXPANDED)[1]
        self.assertIn(37, map(int, excluded.split()))
        activity = re.search(r"activity-positions = <(.*?)>;", km.EXPANDED)[1]
        self.assertNotIn(37, map(int, activity.split()))  # Ctrl alone is not mouse activity.
        self.assertEqual(re.findall(r"&tog (\d+)", node("ime_toggle")), ["1"])
        self.assertIn('&mouse_off 2', node("ime_toggle"))
        self.assertEqual(km.LAYERS["BASE"][34], "&kp LCTRL")

    def test_production_shift_precedes_next_key_and_refreshes_release_time(self):
        source = ROOT / "src/behavior_shift_hold.c"
        self.assertIn('bindings = <&z_sticky LEFT_SHIFT>;', node("shift_hold"))
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
                            "-Werror", "-fsanitize=undefined", "-fno-sanitize-recover=all",
                            "-I", str(temp), f'-DPRODUCTION_SOURCE="{source}"',
                            str(temp / "replay.c"), "-o", str(temp / "replay")], check=True)
            subprocess.run([str(temp / "replay")], check=True)


if __name__ == "__main__":
    unittest.main()
