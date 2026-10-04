"""Static binding regressions, not firmware or HID event tests.

Run with Python 3 and cpp: python3 -m unittest discover -s tests -v
Only this file's local preprocessor macros are expanded. ZMK includes are omitted;
validation against ZMK/Zephyr headers and bindings belongs to the firmware build.
"""

import itertools
from pathlib import Path
import re
import subprocess
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / "config/roBa.keymap").read_text()
EXPANDED = subprocess.check_output(
    ["cpp", "-P", "-x", "assembler-with-cpp", "-"],
    input=re.sub(r"^#include .*\n", "", SOURCE, flags=re.MULTILINE),
    text=True,
)
LAYER_NAMES = ("BASE", "MOUSE", "NUM", "NAV", "FUNCTION", "SCROLL", "SYSTEM")
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
MOUSE_KEYS = ["&kp LC(C)", "&mkp MB1", "&mkp MB3", "&mkp MB2", "&kp LC(V)"]
LETTERS = ["&kp " + key for key in "YUIOP"]
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
        for index, suffix in enumerate(("BASE", "MOUSE", "NUM", "NAV", "FN", "SCROLL", "SYSTEM")):
            self.assertRegex(SOURCE, rf"#define L_{suffix}\s+{index}\b")
        self.assertIn("automouse-layer = <1>", EXPANDED)
        self.assertIn("scroll-layers = <5>", EXPANDED)

    def test_base_entrypoints(self):
        expected = {
            7: "&kp I", 16: "&lt 5 MINUS", 17: "&kp H",
            37: "&lt_mouse_exit 6 INT_HENKAN", 38: "&lt 2 SPACE",
            39: "&lt_mouse_exit 3 INT_MUHENKAN", 40: "&kp ESCAPE",
            41: "&lt 4 ENTER", 42: "&kp BACKSPACE",
        }
        for position, binding in expected.items():
            with self.subTest(position=position):
                self.assertEqual(LAYERS["BASE"][position], binding)

    def test_modifiers_are_preserved(self):
        self.assertEqual(LAYERS["BASE"][34:37], ["&kp LCTRL", "&kp LEFT_WIN", "&kp LEFT_ALT"])
        self.assertEqual(LAYERS["BASE"][22], "&mt LEFT_SHIFT Z")
        self.assertEqual(LAYERS["NUM"][22], "&mt LEFT_SHIFT KP_NUMBER_0")
        self.assertIn('flavor = "balanced";', SOURCE)
        self.assertIn("quick-tap-ms = <0>;", SOURCE)

    def test_no_global_layer_reset_or_flip(self):
        self.assertNotRegex(EXPANDED, r"&(?:to|tog)\b")
        self.assertNotIn("to_layer_0", SOURCE)

    def test_mouse_and_scroll_do_not_depend_on_each_other(self):
        for layer in ("MOUSE", "SCROLL"):
            with self.subTest(layer=layer):
                self.assertEqual(LAYERS[layer][5:10], MOUSE_KEYS)
                self.assertEqual([resolve({"BASE", layer}, p) for p in range(5, 10)], MOUSE_KEYS)
        self.assertEqual(LAYERS["MOUSE"][17:21], ["&trans"] * 4)
        for layer in ("MOUSE", "NAV", "FUNCTION"):
            self.assertEqual(LAYERS[layer][16], "&mo 5")

    def test_nav_uses_hjkl_and_masks_automouse(self):
        self.assertEqual(LAYERS["NAV"][17:21], ARROWS)
        for mouse in (False, True):
            active = {"BASE", "NAV"} | ({"MOUSE"} if mouse else set())
            self.assertEqual([resolve(active, p) for p in range(5, 10)], LETTERS)
            self.assertEqual([resolve(active, p) for p in range(17, 21)], ARROWS)
        for position in (2, 11, 12, 13):
            self.assertEqual(LAYERS["NAV"][position], "&trans")

    def test_function_keys_and_retired_positions(self):
        positions = (*range(5, 10), *range(17, 22), 29, 30, 31)
        for number, position in enumerate(positions, 1):
            self.assertEqual(LAYERS["FUNCTION"][position], f"&kp F{number}")
        fkeys = [key for key in LAYERS["FUNCTION"] if re.fullmatch(r"&kp F\d+", key)]
        self.assertEqual(len(fkeys), 13)
        self.assertEqual(LAYERS["FUNCTION"][16], "&mo 5")
        self.assertEqual(LAYERS["FUNCTION"][33], "&trans")
        self.assertEqual(LAYERS["FUNCTION"][42], "&kp DEL")

    def test_all_layer_combinations_for_new_presses(self):
        for flags in itertools.product((False, True), repeat=6):
            active = {"BASE"} | {name for name, flag in zip(LAYER_NAMES[1:], flags) if flag}
            with self.subTest(active=sorted(active)):
                self.assertEqual(resolve(active, 40), "&kp ESCAPE")
                expected_delete = "&kp DEL" if "FUNCTION" in active else "&kp BACKSPACE"
                self.assertEqual(resolve(active, 42), expected_delete)
                if "SYSTEM" in active:
                    expected_top = [f"&bt BT_SEL {i}" for i in range(5)]
                elif "SCROLL" in active:
                    expected_top = MOUSE_KEYS
                elif "FUNCTION" in active:
                    expected_top = [f"&kp F{i}" for i in range(1, 6)]
                elif "NAV" in active:
                    expected_top = LETTERS
                elif "NUM" in active:
                    expected_top = ["&kp " + key for key in (
                        "CARET", "AMPERSAND", "TILDE", "LEFT_PARENTHESIS", "RIGHT_PARENTHESIS")]
                else:
                    expected_top = MOUSE_KEYS if "MOUSE" in active else LETTERS
                self.assertEqual([resolve(active, p) for p in range(5, 10)], expected_top)

    def test_release_removes_only_the_requested_layer_in_lookup_model(self):
        for mouse in (False, True):
            underlying = {"BASE"} | ({"MOUSE"} if mouse else set())
            self.assertEqual(resolve(underlying | {"FUNCTION"}, 42), "&kp DEL")
            self.assertEqual(resolve(underlying, 42), "&kp BACKSPACE")
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
            r"(?s)exit_mouse_key:\s*\w+\s*\{[^}]*"
            r"wait-ms = <0>;[^}]*bindings = <&macro_press &mouse_off 1\s+"
            r"&macro_tap &macro_param_1to1 &kp MACRO_PLACEHOLDER>;"
        ))
        self.assertRegex(EXPANDED, (
            r'(?s)lt_mouse_exit:\s*\w+\s*\{[^}]*'
            r'flavor = "tap-preferred";[^}]*tapping-term-ms = <200>;[^}]*'
            r'bindings = <&mo>, <&exit_mouse_key>;'
        ))
        self.assertRegex(EXPANDED, (
            r"(?s)muhennkann\s*\{\s*bindings = <&exit_mouse_key INT_MUHENKAN>;"
        ))
        # Only the former IME taps / combo gain mouse exit, not clicks or all keys.
        for position, layer, code in ((37, 6, "INT_HENKAN"), (39, 3, "INT_MUHENKAN")):
            self.assertEqual(
                resolve({"BASE", "MOUSE"}, position),
                f"&lt_mouse_exit {layer} {code}",
            )
        self.assertEqual(resolve({"BASE", "MOUSE"}, 40), "&kp ESCAPE")

    def test_mouse_exit_keeps_manual_layers_in_lookup_model(self):
        # Read the target from the macro; behavior semantics are checked above.
        target = LAYER_NAMES[int(re.search(r"&mouse_off (\d+)", EXPANDED)[1])]
        for flags in itertools.product((False, True), repeat=6):
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
        base = {21: "SQT", 27: "COLON", 28: "SEMICOLON", 31: "COMMA", 32: "DOT", 33: "SLASH"}
        symbols = {
            8: "LEFT_PARENTHESIS", 9: "RIGHT_PARENTHESIS", 16: "UNDERSCORE",
            27: "EQUAL", 28: "PIPE", 29: "LEFT_BRACKET", 30: "RIGHT_BRACKET",
            31: "LEFT_BRACE", 32: "RIGHT_BRACE", 33: "BACKSLASH",
        }
        for mouse in (set(), {"MOUSE"}):
            for position, code in base.items():
                self.assertEqual(resolve({"BASE"} | mouse, position), f"&kp {code}")
            for position, code in symbols.items():
                self.assertEqual(resolve({"BASE", "NUM"} | mouse, position), f"&kp {code}")
        # Returning from Fn must uncover NUM's brackets, not discard NUM itself.
        for position in (29, 30, 31):
            self.assertRegex(resolve({"BASE", "NUM", "FUNCTION"}, position), r"&kp F1[123]")
            self.assertEqual(resolve({"BASE", "NUM"}, position), f"&kp {symbols[position]}")

    def test_punctuation_combos_keep_literal_outputs(self):
        for name, code in (("double_quotation", "DOUBLE_QUOTES"), ("eq", "EQUAL")):
            self.assertRegex(EXPANDED, rf"(?s){name}\s*\{{\s*bindings = <&kp {code}>;")

    def test_combos_do_not_capture_manual_layer_keys(self):
        combos = re.findall(
            r"\b(tab|shift_tab|muhennkann|double_quotation|eq)\s*\{(.*?)\};",
            EXPANDED, re.DOTALL,
        )
        expected = {
            "tab": (11, 12), "shift_tab": (12, 13), "muhennkann": (11, 10),
            "double_quotation": (20, 21), "eq": (24, 25),
        }
        self.assertEqual(len(combos), len(expected))
        self.assertEqual(len(re.findall(r"key-positions\s*=", EXPANDED)), len(expected))
        for name, body in combos:
            self.assertIn("layers = <0 1>", body)
            positions = tuple(map(int, re.search(r"key-positions\s*=\s*<(.*?)>", body)[1].split()))
            self.assertEqual(positions, expected[name])
        self.assertEqual(LAYERS["NUM"][28], "&kp PIPE")
        self.assertEqual(LAYERS["SYSTEM"][32], "&bt BT_CLR_ALL")
        self.assertEqual(LAYERS["SYSTEM"][33], "&bt BT_CLR")


if __name__ == "__main__":
    unittest.main()
