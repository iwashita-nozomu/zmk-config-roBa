"""Static binding regressions, not firmware or HID event tests.

Run with Python 3 and cpp: python3 -m unittest discover -s tests -v
Only this file's local preprocessor macros are expanded. ZMK includes are omitted;
validation against ZMK/Zephyr headers and bindings belongs to the firmware build.
"""

import itertools
import os
import tempfile
from pathlib import Path
import re
import subprocess
import sys
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / "config/roBa.keymap").read_text()
EXPANDED = subprocess.check_output(
    ["cpp", "-P", "-x", "assembler-with-cpp", "-"],
    input=re.sub(r"^#include .*\n", "", SOURCE, flags=re.MULTILINE),
    text=True,
)
LAYER_NAMES = ("BASE", "IME_ALT", "MOUSE", "MOUSE_HOLD", "SLOW", "NUM", "NAV", "FUNCTION", "SCROLL", "SYSTEM")
BLOCKS = re.findall(
    r"\b(" + "|".join(LAYER_NAMES) + r")\s*\{(.*?)\n\s*\};",
    EXPANDED,
    re.DOTALL,
)
LAYERS = {
    name: ["&" + " ".join(item.split()) for item in
           re.search(r"bindings\s*=\s*<(.*?)>;", body, re.DOTALL)[1].split("&")[1:]]
    for name, body in BLOCKS
}
MOUSE_KEYS = ["&kp LC(C)", "&mo 3", "&mkp MB1", "&mkp MB2", "&kp LC(V)"]
LETTERS = ["&lt 3 U" if key == "U" else "&kp " + key for key in "YUIOP"]
ARROWS = ["&kp " + key + "_ARROW" for key in ("LEFT", "DOWN", "UP", "RIGHT")]


def resolve(active, position):
    """Model highest-active-layer lookup for a new press, not held-key events."""
    for layer in reversed(LAYER_NAMES):
        if layer in active and LAYERS[layer][position] != "&trans":
            return LAYERS[layer][position]
    raise AssertionError(f"No binding for position {position} in {active}")


class KeymapTests(unittest.TestCase):
    def test_layer_order_and_size(self):
        self.assertEqual(tuple(name for name, _ in BLOCKS), LAYER_NAMES)
        self.assertTrue(all(len(keys) == 43 for keys in LAYERS.values()))
        for index, suffix in enumerate(("BASE", "IME_ALT", "MOUSE", "MOUSE_HOLD", "SLOW", "NUM", "NAV", "FN", "SCROLL", "SYSTEM")):
            self.assertRegex(SOURCE, rf"#define L_{suffix}\s+{index}\b")
        self.assertIn("automouse-layer = <0>", EXPANDED)
        self.assertIn("scroll-layers = <8>", EXPANDED)

    def test_base_entrypoints(self):
        expected = {
            6: "&lt 3 U", 21: "&lt 4 LS(NUMBER_7)", 7: "&kp I", 16: "&kp MINUS", 17: "&kp H",
            29: "&kp N", 30: "&lt 8 M",
            37: "&ime_toggle LANG1", 38: "&lt 5 SPACE",
            39: "&lt 6 INT_HENKAN", 40: "&kp BACKSPACE",
            41: "&lt 7 ENTER", 42: "&lt 9 ESCAPE",
        }
        for position, binding in expected.items():
            with self.subTest(position=position):
                self.assertEqual(LAYERS["BASE"][position], binding)

    def test_single_ime_toggle_replaces_both_legacy_ime_keys(self):
        self.assertNotRegex(EXPANDED, r"INT_MUHENKAN|LC\(SPACE\)|LANG5\b")
        ime_positions = [
            (name, pos) for name, keys in LAYERS.items()
            for pos, binding in enumerate(keys) if "&ime_toggle" in binding
        ]
        self.assertEqual(ime_positions, [("BASE", 37), ("IME_ALT", 37)])
        self.assertEqual(LAYERS["IME_ALT"][37], "&ime_toggle LANG2")
        self.assertEqual(LAYERS["BASE"][37], "&ime_toggle LANG1")
        self.assertEqual(LAYERS["BASE"][38], "&lt 5 SPACE")
        self.assertEqual(LAYERS["BASE"][39], "&lt 6 INT_HENKAN")
        # Dedicated HENKAN is separate from the LANG toggle and SYSTEM.
        self.assertNotIn("lt_ime", EXPANDED)

    def test_thumb_ime_and_nav_survive_all_layer_combinations(self):
        for flags in itertools.product((False, True), repeat=len(LAYER_NAMES) - 1):
            active = {"BASE"} | {name for name, flag in zip(LAYER_NAMES[1:], flags) if flag}
            with self.subTest(active=sorted(active)):
                code = "LANG2" if "IME_ALT" in active else "LANG1"
                self.assertEqual(resolve(active, 37), f"&ime_toggle {code}")
                self.assertEqual(resolve(active, 39), "&lt 6 INT_HENKAN")

    def test_ime_bit_is_transparent_to_other_keys_and_sensors(self):
        self.assertEqual(
            [pos for pos, key in enumerate(LAYERS["IME_ALT"]) if key != "&trans"], [37]
        )
        self.assertNotIn("sensor-bindings", dict(BLOCKS)["IME_ALT"])
        self.assertNotRegex(EXPANDED, r"&(?:mo|lt) 1\b")
        # Adding the bit cannot change punctuation, pointer actions, Fn or NAV.
        others = [name for name in LAYER_NAMES[1:] if name != "IME_ALT"]
        for flags in itertools.product((False, True), repeat=len(others)):
            active = {"BASE"} | {name for name, flag in zip(others, flags) if flag}
            for position in range(43):
                if position != 37:
                    self.assertEqual(resolve(active, position), resolve(active | {"IME_ALT"}, position))

    def test_ime_taps_alternate_and_preserve_manual_layers_in_lookup_model(self):
        # This models the macro's layer operations; not queue timing or HID delivery.
        macro = re.search(r"(?s)ime_toggle:\s*\w+\s*\{(.*?)\};", EXPANDED)[1]
        mouse = LAYER_NAMES[int(re.search(r"&mouse_off (\d+)", macro)[1])]
        bit = LAYER_NAMES[int(re.search(r"&tog (\d+)", macro)[1])]
        self.assertEqual((mouse, bit), ("MOUSE", "IME_ALT"))
        self.assertEqual(macro.count("&kp "), 1)
        for flags in itertools.product((False, True), repeat=len(LAYER_NAMES) - 1):
            active = {"BASE"} | {name for name, flag in zip(LAYER_NAMES[1:], flags) if flag}
            manual = active - {"MOUSE", "IME_ALT"}
            initial = "IME_ALT" in active
            for count in range(4):
                binding = resolve(active, 37)
                code = binding.split()[-1]
                self.assertEqual(code, "LANG2" if initial ^ bool(count % 2) else "LANG1")
                active = (active - {mouse}) ^ {bit}
                self.assertEqual(active - {"IME_ALT"}, manual)
                self.assertEqual("IME_ALT" in active, initial ^ bool((count + 1) % 2))

    def test_z_shift_and_other_modifiers(self):
        self.assertEqual(LAYERS["BASE"][34:37], ["&kp LCTRL", "&kp LEFT_WIN", "&kp LEFT_ALT"])
        self.assertEqual(LAYERS["BASE"][22], "&z_shift")
        self.assertEqual(LAYERS["NAV"][22], "&kp LEFT_SHIFT")
        self.assertEqual(LAYERS["NUM"][22], "&mt LEFT_SHIFT NUMBER_0")
        self.assertIn('flavor = "balanced";', SOURCE)
        self.assertIn("quick-tap-ms = <0>;", SOURCE)

    def test_z_hold_and_one_shot_grace_use_standard_behaviors(self):
        sticky = re.search(r"(?s)z_sticky:\s*\w+\s*\{(.*?)\};", EXPANDED)[1]
        hold = re.search(r"(?s)z_hold:\s*\w+\s*\{(.*?)\};", EXPANDED)[1]
        self.assertIn('compatible = "zmk,behavior-sticky-key";', sticky)
        self.assertIn('release-after-ms = <200>;', sticky)
        self.assertIn('quick-release;', sticky)
        self.assertIn('ignore-modifiers;', sticky)
        self.assertNotIn('lazy;', sticky)  # Shift must also be visible to mouse clicks.
        self.assertEqual(re.findall(r"&([a-z_]+)", sticky), ["kp"])
        self.assertIn('compatible = "zmk,behavior-hold-tap";', hold)
        self.assertIn('tapping-term-ms = <200>;', hold)
        self.assertIn('flavor = "tap-preferred";', hold)
        self.assertIn('quick-tap-ms = <0>;', hold)
        self.assertEqual(re.findall(r"&([a-z_]+)", hold), ["shift_hold", "z_tap"])
        self.assertNotIn('ime_shift', SOURCE)
        for flags in itertools.product((False, True), repeat=len(LAYER_NAMES) - 1):
            active = {"BASE"} | {name for name, flag in zip(LAYER_NAMES[1:], flags) if flag}
            code = "LANG2" if "IME_ALT" in active else "LANG1"
            self.assertEqual(resolve(active, 37), f"&ime_toggle {code}")
            expected = "&kp LEFT_SHIFT" if "NAV" in active else (
                "&mt LEFT_SHIFT NUMBER_0" if "NUM" in active else "&z_shift")
            self.assertEqual(resolve(active, 22), expected)

    def test_sticky_grace_is_timed_from_release_not_the_hold_tap_press(self):
        bridge = re.search(r"(?s)shift_hold:\s*\w+\s*\{(.*?)\};", EXPANDED)[1]
        self.assertIn('compatible = "zmk,behavior-macro";', bridge)
        self.assertIn('wait-ms = <0>;', bridge)
        self.assertRegex(bridge, r"bindings = <&macro_press &z_sticky LEFT_SHIFT\s+"
                                r"&macro_pause_for_release &macro_release &z_sticky LEFT_SHIFT>;")
        self.assertNotIn('&macro_tap', bridge)

    def test_shifted_z_bypasses_hold_tap_without_masking_shift(self):
        morph = re.search(r"(?s)z_shift:\s*\w+\s*\{(.*?)\};", EXPANDED)[1]
        self.assertIn('compatible = "zmk,behavior-mod-morph";', morph)
        self.assertIn('bindings = <&z_hold 0 0>, <&z_tap>;', morph)
        self.assertIn('mods = <(MOD_LSFT | MOD_RSFT)>;', morph)
        self.assertIn('keep-mods = <(MOD_LSFT | MOD_RSFT)>;', morph)
        drawer = (Path(__file__).resolve().parents[1] / "keymap_drawer.config.yaml").read_text()
        self.assertIn('"&z_shift": {"t": "Z", "h": "Shift + 200ms"}', drawer)

    def test_z_typing_exits_only_automatic_mouse_and_preserves_press_release(self):
        tap = re.search(r"(?s)z_tap:\s*\w+\s*\{(.*?)\};", EXPANDED)[1]
        self.assertIn('compatible = "zmk,behavior-macro";', tap)
        self.assertIn('wait-ms = <0>;', tap)
        self.assertRegex(tap, r"bindings = <&macro_press &mouse_off 2 &kp Z\s+"
                             r"&macro_pause_for_release &macro_release &kp Z>;")
        self.assertNotIn('&macro_tap', tap)
        self.assertNotIn('&tog', tap)
        excluded = set(map(int, re.search(r"excluded-positions\s*=\s*<(.*?)>", EXPANDED)[1].split()))
        self.assertIn(22, excluded)  # A Shift hold must not eject the pointing layer.
        self.assertNotIn(37, excluded)  # Thumb is no longer a modifier.
        for layer in ("MOUSE", "MOUSE_HOLD", "SLOW", "SCROLL"):
            self.assertEqual(resolve({"BASE", layer}, 22), "&z_shift")

    def test_nav_conversion_keeps_space_num_and_momentary_hold(self):
        self.assertIn("&lt L_NAV INT_HENKAN", SOURCE)
        self.assertNotIn("&lt L_NAV SPACE", SOURCE)
        self.assertNotIn("&lt L_NAV TAB", SOURCE)
        self.assertNotIn("&mo L_NAV", SOURCE)
        # Use the existing standard layer-tap; do not change other layer-tap timing.
        self.assertNotRegex(SOURCE, r"&lt\s*\{")
        for flags in itertools.product((False, True), repeat=len(LAYER_NAMES) - 1):
            active = {"BASE"} | {name for name, flag in zip(LAYER_NAMES[1:], flags) if flag}
            self.assertEqual(resolve(active, 38), "&lt 5 SPACE")
            self.assertEqual(resolve(active, 39), "&lt 6 INT_HENKAN")
        for name, code in (("tab", "TAB"), ("shift_tab", "LS(TAB)")):
            body = re.search(rf"(?s)\b{name}\s*\{{(.*?)\}};", EXPANDED)[1]
            self.assertIn(f"bindings = <&kp {code}>;", body)

    def test_henkan_is_a_dedicated_usage_not_space_or_ime_toggle(self):
        bindings = [(name, p, key) for name, keys in LAYERS.items()
                    for p, key in enumerate(keys) if "INT_HENKAN" in key]
        self.assertEqual(bindings, [("BASE", 39, "&lt 6 INT_HENKAN")])
        self.assertEqual(LAYERS["BASE"][38], "&lt 5 SPACE")
        macro = re.search(r"(?s)ime_toggle:\s*\w+\s*\{(.*?)\};", EXPANDED)[1]
        self.assertNotIn("INT_HENKAN", macro)
        self.assertNotIn("SPACE", macro)
        drawer = (Path(__file__).resolve().parents[1] / "keymap_drawer.config.yaml").read_text()
        self.assertIn('"&lt L_NAV INT_HENKAN": {"t": "HENKAN", "h": "NAV"}', drawer)

    def test_num_digits_use_shiftable_number_row_codes(self):
        positions = (22, 23, 24, 25, 11, 12, 13, 1, 2, 3)  # 0..9
        for flags in itertools.product((False, True), repeat=4):
            active = {"BASE", "NUM"} | {
                name for name, flag in zip(("IME_ALT", "MOUSE", "MOUSE_HOLD", "SLOW"), flags) if flag
            }
            for number, position in enumerate(positions):
                binding = ("&mt LEFT_SHIFT " if number == 0 else "&kp ") + f"NUMBER_{number}"
                with self.subTest(active=sorted(active), number=number):
                    self.assertEqual(resolve(active, position), binding)
        # This modified keypad shortcut is not a numeric-entry key.
        self.assertEqual(LAYERS["NUM"][15], "&kp LC(LA(KP_NUMBER_0))")

    def test_only_send_order_bit_is_toggled(self):
        self.assertNotRegex(EXPANDED, r"&to\b")
        self.assertEqual(re.findall(r"&tog\s+(\d+)", EXPANDED), ["1"])
        self.assertNotIn("to_layer_0", SOURCE)

    def test_mouse_and_scroll_do_not_depend_on_each_other(self):
        for layer in ("MOUSE", "MOUSE_HOLD", "SLOW", "SCROLL"):
            with self.subTest(layer=layer):
                self.assertEqual(LAYERS[layer][5:10], MOUSE_KEYS)
                self.assertEqual([resolve({"BASE", layer}, p) for p in range(5, 10)], MOUSE_KEYS)
        self.assertEqual(LAYERS["MOUSE"][17:21], ["&trans", "&none", "&none", "&trans"])
        for layer in ("MOUSE", "NAV", "FUNCTION"):
            self.assertEqual(LAYERS[layer][16], "&trans")

    def test_nav_uses_hjkl_and_disables_top_row(self):
        self.assertEqual(LAYERS["NAV"][5:10], ["&none"] * 5)
        self.assertEqual(LAYERS["NAV"][17:21], ARROWS)
        for flags in itertools.product((False, True), repeat=5):
            underlying = {"BASE"} | {
                name for name, flag in zip(("IME_ALT", "MOUSE", "MOUSE_HOLD", "SLOW", "NUM"), flags) if flag
            }
            active = underlying | {"NAV"}
            with self.subTest(active=sorted(active)):
                self.assertEqual([resolve(active, p) for p in range(5, 10)], ["&none"] * 5)
                self.assertEqual([resolve(active, p) for p in range(17, 21)], ARROWS)
                # Releasing NAV restores the still-active lower layer for new presses.
                if "NUM" in underlying:
                    expected = ["&kp " + key for key in (
                        "EQUAL", "LS(NUMBER_6)", "LS(EQUAL)", "LS(NUMBER_8)", "LS(NUMBER_9)")]
                else:
                    expected = MOUSE_KEYS if underlying & {"MOUSE", "MOUSE_HOLD", "SLOW"} else LETTERS
                self.assertEqual([resolve(active - {"NAV"}, p) for p in range(5, 10)], expected)
        for position in (2, 11, 12, 13):
            self.assertEqual(LAYERS["NAV"][position], "&trans")

    def test_function_keys_and_retired_positions(self):
        positions = (*range(5, 10), *range(17, 22), 29, 30, 31)
        for number, position in enumerate(positions, 1):
            self.assertEqual(LAYERS["FUNCTION"][position], f"&kp F{number}")
        fkeys = [key for key in LAYERS["FUNCTION"] if re.fullmatch(r"&kp F\d+", key)]
        self.assertEqual(len(fkeys), 13)
        self.assertEqual(LAYERS["FUNCTION"][16], "&trans")
        self.assertEqual(LAYERS["FUNCTION"][33], "&trans")
        self.assertEqual(LAYERS["FUNCTION"][40], "&kp DEL")

    def test_all_layer_combinations_for_new_presses(self):
        for flags in itertools.product((False, True), repeat=len(LAYER_NAMES) - 1):
            active = {"BASE"} | {name for name, flag in zip(LAYER_NAMES[1:], flags) if flag}
            with self.subTest(active=sorted(active)):
                self.assertEqual(resolve(active, 42), "&lt 9 ESCAPE")
                expected_delete = "&kp DEL" if "FUNCTION" in active else "&kp BACKSPACE"
                self.assertEqual(resolve(active, 40), expected_delete)
                self.assertEqual(resolve(active - {"FUNCTION"}, 40), "&kp BACKSPACE")
                self.assertEqual(resolve(active - {"SYSTEM"}, 42), "&lt 9 ESCAPE")
                if "SYSTEM" in active:
                    expected_top = [f"&bt BT_SEL {i}" for i in range(5)]
                elif "SCROLL" in active:
                    expected_top = MOUSE_KEYS
                elif "FUNCTION" in active:
                    expected_top = [f"&kp F{i}" for i in range(1, 6)]
                elif "NAV" in active:
                    expected_top = ["&none"] * 5
                elif "NUM" in active:
                    expected_top = ["&kp " + key for key in (
                        "EQUAL", "LS(NUMBER_6)", "LS(EQUAL)", "LS(NUMBER_8)", "LS(NUMBER_9)")]
                else:
                    expected_top = MOUSE_KEYS if active & {"MOUSE", "MOUSE_HOLD", "SLOW"} else LETTERS
                self.assertEqual([resolve(active, p) for p in range(5, 10)], expected_top)

    def test_release_removes_only_the_requested_layer_in_lookup_model(self):
        for mouse in (False, True):
            underlying = {"BASE"} | ({"MOUSE"} if mouse else set())
            self.assertEqual(resolve(underlying | {"FUNCTION"}, 40), "&kp DEL")
            self.assertEqual(resolve(underlying, 40), "&kp BACKSPACE")
            self.assertEqual(resolve(underlying | {"NAV"}, 17), "&kp LEFT_ARROW")
            self.assertEqual(resolve(underlying, 17), "&kp H")
            expected = MOUSE_KEYS if mouse else LETTERS
            self.assertEqual([resolve(underlying, p) for p in range(5, 10)], expected)

    def test_mouse_exit_is_off_only_and_preserves_key_output(self):
        self.assertRegex(EXPANDED, (
            r'(?s)mouse_off:\s*\w+\s*\{[^}]*'
            r'compatible = "zmk,behavior-toggle-layer";[^}]*'
            r'toggle-mode = "off";'
        ))
        self.assertRegex(EXPANDED, (
            r"(?s)ime_toggle:\s*\w+\s*\{[^}]*"
            r"wait-ms = <0>;[^}]*bindings = <&macro_press &mouse_off 2 &tog 1\s+"
            r"&macro_tap &macro_param_1to1 &kp MACRO_PLACEHOLDER>;"
        ))
        self.assertNotIn("lt_ime", EXPANDED)
        self.assertRegex(EXPANDED, (
            r"(?s)exit_mouse\s*\{\s*bindings = <&mouse_off 2>;"
        ))
        # One IME tap exits MOUSE; A+S exits without sending an IME key.
        self.assertEqual(
            resolve({"BASE", "MOUSE"}, 37), "&ime_toggle LANG1"
        )
        self.assertEqual(resolve({"BASE", "MOUSE"}, 39), "&lt 6 INT_HENKAN")
        self.assertEqual(resolve({"BASE", "MOUSE"}, 42), "&lt 9 ESCAPE")

    def test_mouse_exit_keeps_manual_layers_in_lookup_model(self):
        # Read the target from the macro; behavior semantics are checked above.
        target = LAYER_NAMES[int(re.search(r"&mouse_off (\d+)", EXPANDED)[1])]
        for flags in itertools.product((False, True), repeat=len(LAYER_NAMES) - 1):
            active = {"BASE"} | {name for name, flag in zip(LAYER_NAMES[1:], flags) if flag}
            after = active - {target}
            self.assertEqual(after, active - {"MOUSE"})
            self.assertEqual(after - {target}, after)  # Repeated taps cannot turn MOUSE on.
            for position in (27, 28, 39, 40, 41, 42):
                self.assertEqual(resolve(after, position), resolve(active, position))
        self.assertEqual(
            [resolve({"BASE", "MOUSE"} - {target}, p) for p in range(5, 10)], LETTERS
        )

    def test_punctuation_and_brackets_survive_automouse(self):
        base = {21: "LS(NUMBER_7)", 27: "SQT", 28: "SEMICOLON", 31: "COMMA", 32: "DOT", 33: "SLASH"}
        symbols = {
            0: "MINUS", 4: "LS(SEMICOLON)", 5: "EQUAL", 6: "LS(NUMBER_6)",
            7: "LS(EQUAL)", 8: "LS(NUMBER_8)", 9: "LS(NUMBER_9)", 10: "SLASH",
            14: "LS(SQT)", 16: "LS(INT_RO)", 17: "EXCLAMATION", 18: "LEFT_BRACKET",
            19: "HASH", 20: "DOLLAR", 21: "PERCENT", 26: "PERIOD",
            27: "LS(MINUS)", 28: "LS(INT_YEN)", 29: "RIGHT_BRACKET", 30: "NON_US_HASH",
            31: "LS(RIGHT_BRACKET)", 32: "LS(NON_US_HASH)", 33: "INT_RO",
        }
        for mouse in (set(), {"MOUSE"}, {"SLOW"}, {"MOUSE", "MOUSE_HOLD", "SLOW"}):
            for position, code in base.items():
                expected = ("&mo 4" if mouse else "&lt 4 LS(NUMBER_7)") if position == 21 else f"&kp {code}"
                self.assertEqual(resolve({"BASE"} | mouse, position), expected)
            for position, code in symbols.items():
                self.assertEqual(resolve({"BASE", "NUM"} | mouse, position), f"&kp {code}")
        # Returning from Fn must uncover NUM's brackets, not discard NUM itself.
        for position in (29, 30, 31):
            self.assertRegex(resolve({"BASE", "NUM", "FUNCTION"}, position), r"&kp F1[123]")
            self.assertEqual(resolve({"BASE", "NUM"}, position), f"&kp {symbols[position]}")

    def test_jis_native_shift_pairs_use_unshifted_usages(self):
        # JIS host pairs, independently checked against QMK's Japanese usage table.
        # These assertions inspect firmware bindings, not real host text output.
        pairs = (
            ("BASE", 16, "MINUS", "-", "="),
            ("BASE", 27, "SQT", ":", "*"),
            ("BASE", 28, "SEMICOLON", ";", "+"),
            ("NUM", 5, "EQUAL", "^", "~"),
            ("NUM", 18, "LEFT_BRACKET", "@", "`"),
            ("NUM", 29, "RIGHT_BRACKET", "[", "{"),
            ("NUM", 30, "NON_US_HASH", "]", "}"),
            ("NUM", 33, "INT_RO", "\\", "_"),
        )
        for layer, position, code, plain, shifted in pairs:
            with self.subTest(layer=layer, pair=(plain, shifted)):
                self.assertEqual(resolve({"BASE", layer}, position), f"&kp {code}")
        # JIS apostrophe already includes Shift+7; extra Shift does not turn it into quote.
        self.assertEqual(LAYERS["NAV"][21], "&kp LS(NUMBER_7)")

    def test_punctuation_combos_keep_literal_outputs(self):
        for name, code in (("double_quotation", "LS(NUMBER_2)"), ("eq", "LS(MINUS)")):
            self.assertRegex(EXPANDED, rf"(?s){name}\s*\{{\s*bindings = <&kp {re.escape(code)}>;")

    def test_combos_do_not_capture_manual_layer_keys(self):
        combos = re.findall(
            r"\b(tab|shift_tab|exit_mouse|double_quotation|eq|middle_click)\s*\{(.*?)\};",
            EXPANDED, re.DOTALL,
        )
        expected = {
            "tab": (11, 12), "shift_tab": (12, 13), "exit_mouse": (11, 10),
            "double_quotation": (20, 21), "eq": (24, 25), "middle_click": (18, 19),
        }
        self.assertEqual(len(combos), len(expected))
        self.assertEqual(len(re.findall(r"key-positions\s*=", EXPANDED)), len(expected))
        for name, body in combos:
            layers = tuple(map(int, re.search(r"layers\s*=\s*<(.*?)>", body)[1].split()))
            # Middle click belongs only to pointer layers; quote excludes SLOW.
            expected_layers = ((2, 3, 4, 8) if name == "middle_click" else
                               (0, 1) if name == "double_quotation" else (0, 1, 2, 3, 4))
            self.assertEqual(layers, expected_layers)
            positions = tuple(map(int, re.search(r"key-positions\s*=\s*<(.*?)>", body)[1].split()))
            self.assertEqual(positions, expected[name])
        self.assertEqual(LAYERS["NUM"][28], "&kp LS(INT_YEN)")
        self.assertEqual(LAYERS["SYSTEM"][32], "&bt BT_CLR_ALL")
        self.assertEqual(LAYERS["SYSTEM"][33], "&bt BT_CLR")

    def test_pointing_controls_preserve_letters_symbols_and_function_keys(self):
        self.assertEqual(LAYERS["BASE"][29:31], ["&kp N", "&lt 8 M"])
        for layer in ("MOUSE", "MOUSE_HOLD", "SLOW", "SCROLL"):
            self.assertEqual(LAYERS[layer][29], "&trans")
            self.assertEqual(LAYERS[layer][21], "&mo 4")
            self.assertEqual(LAYERS[layer][30], "&mo 8")
            self.assertEqual(resolve({"BASE", layer}, 29), "&kp N")
            self.assertEqual(resolve({"BASE", layer}, 30), "&mo 8")
            self.assertEqual(LAYERS[layer], LAYERS["MOUSE"])
        for pointer in ({"MOUSE"}, {"SLOW"}, {"MOUSE", "MOUSE_HOLD", "SLOW"}):
            self.assertEqual(
                [resolve({"BASE", "NUM"} | pointer, p) for p in (29, 30)],
                ["&kp RIGHT_BRACKET", "&kp NON_US_HASH"],
            )
            self.assertEqual(
                [resolve({"BASE", "FUNCTION"} | pointer, p) for p in (29, 30)],
                ["&kp F11", "&kp F12"],
            )
        # Old inner/N positions never enter SCROLL; M uses it only in pointer modes.
        for flags in itertools.product((False, True), repeat=len(LAYER_NAMES) - 1):
            active = {"BASE"} | {name for name, flag in zip(LAYER_NAMES[1:], flags) if flag}
            expected = "&kp LS(INT_RO)" if "NUM" in active else "&kp MINUS"
            self.assertEqual(resolve(active, 16), expected)
            if "SCROLL" in active:
                expected_quote = "&mo 4"
            elif "FUNCTION" in active:
                expected_quote = "&kp F10"
            elif "NAV" in active:
                expected_quote = "&kp LS(NUMBER_7)"
            elif "NUM" in active:
                expected_quote = "&kp PERCENT"
            else:
                expected_quote = "&mo 4" if active & {"MOUSE", "MOUSE_HOLD", "SLOW"} else "&lt 4 LS(NUMBER_7)"
            self.assertEqual(resolve(active, 21), expected_quote)
            expected_m = "&kp F12" if "FUNCTION" in active else (
                "&kp NON_US_HASH" if "NUM" in active else (
                    "&mo 8" if active & {"MOUSE", "MOUSE_HOLD", "SLOW"} else "&lt 8 M"))
            if "SCROLL" in active:
                expected_m = "&mo 8"
            self.assertEqual(resolve(active, 30), expected_m)
            expected_n = "&kp F11" if "FUNCTION" in active else (
                "&kp RIGHT_BRACKET" if "NUM" in active else "&kp N")
            self.assertEqual(resolve(active, 29), expected_n)

    def test_pointing_press_and_release_orders_with_automouse_timeout_in_lookup_model(self):
        # Keep the binding selected at press time, as in a momentary hold.
        # This models configuration semantics, not ZMK's event queue or timing.
        for press_order in itertools.permutations((30, 21)):
            for release_order in itertools.permutations((30, 21)):
                for timeout in (False, True):
                    active = {"BASE", "MOUSE"}
                    held = {}
                    for position in press_order:
                        binding = resolve(active, position).split()
                        self.assertEqual(binding[0], "&mo")
                        target = LAYER_NAMES[int(binding[1])]
                        held[position] = target
                        active.add(target)
                        if timeout:
                            active.discard("MOUSE")
                    self.assertTrue({"SLOW", "SCROLL"} <= active)
                    for position in release_order:
                        active.remove(held.pop(position))
                        self.assertEqual("SLOW" in active, 21 in held)
                        self.assertEqual("SCROLL" in active, 30 in held)
                        if held:
                            self.assertEqual([resolve(active, p) for p in range(5, 10)], MOUSE_KEYS)
                            other = next(iter(held))
                            expected = "&mo 8" if position == 30 else "&mo 4"
                            self.assertEqual(resolve(active, position), expected)
                            self.assertEqual(held[other], "SLOW" if other == 21 else "SCROLL")
                    self.assertEqual(active, {"BASE"} if timeout else {"BASE", "MOUSE"})

    def test_slow_is_independent_of_scroll_mode_and_uses_standard_scalers(self):
        self.assertIn("#include <input/processors.dtsi>", SOURCE)
        override = re.search(r"(?s)&trackball_listener\s*\{(.*?)\n\};", EXPANDED)[1]
        self.assertIn("layers = <4>;", override)
        self.assertEqual(
            re.findall(r"&zip_(\w+)_scaler\s+(\d+)\s+(\d+)", override),
            [("xy", "1", "4"), ("scroll", "1", "4")],
        )
        self.assertEqual(override.count("input-processors ="), 2)
        self.assertNotIn("snipe-layers", EXPANDED)
        self.assertNotIn("sensor-bindings", dict(BLOCKS)["SLOW"])
        scroll_layers = set(map(int, re.search(r"scroll-layers = <(.*?)>", EXPANDED)[1].split()))
        for flags in itertools.product((False, True), repeat=len(LAYER_NAMES) - 1):
            active = {"BASE"} | {name for name, flag in zip(LAYER_NAMES[1:], flags) if flag}
            # PMW3610 selects its mode from the highest active layer.
            highest = max(LAYER_NAMES.index(layer) for layer in active)
            self.assertEqual(highest in scroll_layers, "SCROLL" in active and "SYSTEM" not in active)

    def test_system_entry_and_dedicated_settings_are_right_handed(self):
        self.assertEqual(LAYERS["BASE"][42], "&lt 9 ESCAPE")
        entries = [(name, p) for name, keys in LAYERS.items() for p, key in enumerate(keys)
                   if re.match(r"&(?:mo|lt) 9(?: |$)", key)]
        self.assertEqual(entries, [("BASE", 42)])
        # Physical positions verified against boards/shields/roBa/roBa.dtsi.
        right = set(range(5, 10)) | set(range(16, 22)) | set(range(28, 34)) | {40, 41, 42}
        for position, binding in enumerate(LAYERS["SYSTEM"]):
            if position not in right:
                self.assertEqual(binding, "&trans")
        self.assertEqual(LAYERS["SYSTEM"][17:20], [f"&kp NUMBER_{n}" for n in (1, 2, 3)])
        self.assertEqual(LAYERS["SYSTEM"][28], "&bootloader")
        self.assertEqual(LAYERS["SYSTEM"][32:34], ["&bt BT_CLR_ALL", "&bt BT_CLR"])
        self.assertNotIn("lt_ime", EXPANDED)

    def test_automatic_entry_uses_one_owner_after_dwell(self):
        self.assertIn("automouse-layer = <0>;", EXPANDED)
        self.assertNotIn("zip_temp_layer", EXPANDED)
        self.assertNotIn("delegate =", EXPANDED)
        cmake = (Path(__file__).resolve().parents[1] / "CMakeLists.txt").read_text()
        self.assertIn("target_sources_ifdef(CONFIG_PMW3610 app PRIVATE", cmake)
        self.assertNotIn("zephyr_library", cmake)
        self.assertIn("manual-layer = <3>;", EXPANDED)
        self.assertIn("dwell-ms = <200>;", EXPANDED)
        self.assertIn("max-gap-ms = <80>;", EXPANDED)
        self.assertIn("require-prior-idle-ms = <300>;", EXPANDED)
        self.assertEqual(SOURCE.count("#define AUTOMOUSE_PROCESSOR "), 1)
        self.assertEqual(EXPANDED.count("&mouse_dwell 2 1000"), 2)
        # Both normal and SLOW paths qualify raw XY before scaling.
        self.assertRegex(EXPANDED, r"input-processors = <&mouse_dwell 2 1000>, <&zip_xy_scaler 1 4>, <&zip_scroll_scaler 1 4>;")
        conf = (Path(__file__).resolve().parents[1] / "boards/shields/roBa/roBa_R.conf").read_text()
        self.assertNotIn("CONFIG_PMW3610_AUTOMOUSE_TIMEOUT_MS", conf)
        self.assertNotIn("CONFIG_PMW3610_MOVEMENT_THRESHOLD", conf)

    def test_typing_exit_preserves_the_first_key_and_manual_layers(self):
        excluded = set(map(int, re.search(r"excluded-positions\s*=\s*<(.*?)>", EXPANDED)[1].split()))
        self.assertEqual(excluded, {5, 6, 7, 8, 9, 18, 19, 21, 22, 30, 34, 35, 36})
        for flags in itertools.product((False, True), repeat=len(LAYER_NAMES) - 1):
            active = {"BASE", "MOUSE"} | {name for name, flag in zip(LAYER_NAMES[1:], flags) if flag}
            for position in set(range(43)) - excluded:
                self.assertEqual(resolve(active, position), resolve(active - {"MOUSE"}, position))
        self.assertEqual(resolve({"BASE", "MOUSE"}, 10), "&kp A")
        self.assertEqual(resolve({"BASE", "MOUSE"}, 29), "&kp N")
        self.assertEqual(resolve({"BASE"}, 7), "&kp I")

    def test_manual_mouse_survives_automatic_expiry(self):
        self.assertEqual(LAYERS["BASE"][6], "&lt 3 U")
        for name in ("MOUSE", "MOUSE_HOLD", "SLOW", "SCROLL"):
            self.assertEqual(LAYERS[name], LAYERS["MOUSE"])
            self.assertEqual(LAYERS[name][6], "&mo 3")
        # The automatic owner controls layer 2, never the momentary layer 3.
        active = {"BASE", "MOUSE", "MOUSE_HOLD"}
        active.remove("MOUSE")
        self.assertEqual([resolve(active, p) for p in range(5, 10)], MOUSE_KEYS)
        active.remove("MOUSE_HOLD")
        self.assertEqual([resolve(active, p) for p in range(5, 10)], LETTERS)
        for layer in ("NUM", "NAV", "FUNCTION"):
            for position in range(43):
                # Only positions transparent in a manual operation layer inherit the pointer layer.
                if LAYERS[layer][position] != "&trans":
                    self.assertEqual(resolve({"BASE", layer, "MOUSE_HOLD"}, position), LAYERS[layer][position])

    def test_mouse_entry_and_slow_hold_keep_clicks_and_symbols(self):
        self.assertNotIn("shared_mo", SOURCE)
        self.assertNotIn("mouse_lt", SOURCE)
        entries = [(name, p) for name, keys in LAYERS.items() for p, key in enumerate(keys)
                   if re.match(r"&(?:mo|lt) 3(?: |$)", key)]
        self.assertEqual(entries, [(name, 6) for name in ("BASE", "MOUSE", "MOUSE_HOLD", "SLOW", "SCROLL")])
        for active in ({"BASE"}, {"BASE", "IME_ALT"}):
            self.assertEqual(resolve(active, 6), "&lt 3 U")
            self.assertEqual(resolve(active, 21), "&lt 4 LS(NUMBER_7)")
            self.assertEqual(resolve(active, 29), "&kp N")
            self.assertEqual(resolve(active, 30), "&lt 8 M")
        for layer in ("MOUSE", "MOUSE_HOLD", "SLOW", "SCROLL"):
            self.assertEqual(resolve({"BASE", layer}, 6), "&mo 3")
            self.assertEqual(resolve({"BASE", layer}, 7), "&mkp MB1")
            self.assertEqual(resolve({"BASE", layer}, 21), "&mo 4")
        self.assertEqual(resolve({"BASE", "NUM"}, 6), "&kp LS(NUMBER_6)")
        self.assertEqual(resolve({"BASE", "NUM"}, 21), "&kp PERCENT")
        self.assertEqual(resolve({"BASE", "NAV"}, 6), "&none")
        self.assertEqual(resolve({"BASE", "NAV"}, 21), "&kp LS(NUMBER_7)")
        self.assertEqual(resolve({"BASE", "FUNCTION"}, 6), "&kp F2")
        self.assertEqual(resolve({"BASE", "FUNCTION"}, 21), "&kp F10")
        # Starting with either M or the quote hold allows the same combination.
        for first, second in ((30, 21), (21, 30)):
            active = {"BASE"}
            first_binding = resolve(active, first).split()
            self.assertEqual(first_binding[0], "&lt")
            first_layer = LAYER_NAMES[int(first_binding[1])]
            active.add(first_layer)
            second_binding = resolve(active, second).split()
            self.assertEqual(second_binding[0], "&mo")
            second_layer = LAYER_NAMES[int(second_binding[1])]
            active.add(second_layer)
            self.assertTrue({"SLOW", "SCROLL"} <= active)
            for layer in (first_layer, second_layer):
                self.assertEqual([resolve(active - {layer}, p) for p in range(5, 10)], MOUSE_KEYS)

    def test_middle_click_is_pointer_only_and_not_a_layer_or_conversion_action(self):
        combo = re.search(r"(?s)middle_click\s*\{(.*?)\};", EXPANDED)[1]
        self.assertIn("timeout-ms = <50>;", combo)
        self.assertIn("key-positions = <18 19>;", combo)
        self.assertIn("layers = <2 3 4 8>;", combo)
        self.assertIn("bindings = <&mkp MB3>;", combo)
        self.assertNotIn("slow-release", combo)  # Release as soon as either key is up.
        self.assertEqual(re.findall(r"&[a-z_]+", combo), ["&mkp"])
        for layer in ("BASE", "IME_ALT"):
            self.assertEqual([resolve({"BASE", layer}, p) for p in (18, 19)], ["&kp J", "&kp K"])
        for layer in ("MOUSE", "MOUSE_HOLD", "SLOW", "SCROLL"):
            self.assertEqual([resolve({"BASE", layer}, p) for p in (18, 19)], ["&none", "&none"])
        # The raw cancellation listener must not discard the layer before the combo.
        excluded = set(map(int, re.search(r"excluded-positions\s*=\s*<(.*?)>", EXPANDED)[1].split()))
        self.assertTrue({18, 19} <= excluded)
        self.assertNotIn(29, excluded)
        root = Path(__file__).resolve().parents[1]
        self.assertNotIn("shared_momentary", (root / "CMakeLists.txt").read_text())
        for path in ("src/behavior_shared_momentary_layer.c",
                     "dts/bindings/behaviors/zmk,behavior-shared-momentary-layer.yaml",
                     "tests/test_shared_layer.py"):
            self.assertFalse((root / path).exists(), path)

    def test_production_motion_dwell_time_boundaries(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "motion-dwell"
            subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-pedantic", str(root / "tests/motion_dwell.c"), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True)

    def test_production_mouse_lifecycle_pending_requests(self):
        root = Path(__file__).resolve().parents[1]
        subprocess.run([sys.executable, "-B", str(root / "tests/bug/temp_layer_pending.py")],
                       check=True)

if __name__ == "__main__":
    unittest.main()
