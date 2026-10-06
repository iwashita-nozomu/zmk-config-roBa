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
LAYER_NAMES = ("BASE", "IME_ALT", "MOUSE", "SLOW", "NUM", "NAV", "FUNCTION", "SCROLL", "SYSTEM")
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
        for index, suffix in enumerate(("BASE", "IME_ALT", "MOUSE", "SLOW", "NUM", "NAV", "FN", "SCROLL", "SYSTEM")):
            self.assertRegex(SOURCE, rf"#define L_{suffix}\s+{index}\b")
        self.assertIn("automouse-layer = <2>", EXPANDED)
        self.assertIn("scroll-layers = <7>", EXPANDED)

    def test_base_entrypoints(self):
        expected = {
            7: "&kp I", 16: "&kp MINUS", 17: "&kp H",
            29: "&lt 7 N", 30: "&kp M",
            37: "&ime_shift LEFT_SHIFT LANG1", 38: "&lt 4 SPACE",
            39: "&lt 5 TAB", 40: "&lt 8 ESCAPE",
            41: "&lt 6 ENTER", 42: "&kp BACKSPACE",
        }
        for position, binding in expected.items():
            with self.subTest(position=position):
                self.assertEqual(LAYERS["BASE"][position], binding)

    def test_single_ime_toggle_replaces_both_legacy_ime_keys(self):
        self.assertNotRegex(EXPANDED, r"INT_(?:HENKAN|MUHENKAN)|LC\(SPACE\)|LANG5\b")
        ime_positions = [
            (name, pos) for name, keys in LAYERS.items()
            for pos, binding in enumerate(keys) if "&ime_shift" in binding
        ]
        self.assertEqual(ime_positions, [("BASE", 37), ("IME_ALT", 37)])
        self.assertEqual(LAYERS["IME_ALT"][37], "&ime_shift LEFT_SHIFT LANG2")
        self.assertEqual(LAYERS["BASE"][37], "&ime_shift LEFT_SHIFT LANG1")
        self.assertEqual(LAYERS["BASE"][38], "&lt 4 SPACE")
        self.assertEqual(LAYERS["BASE"][39], "&lt 5 TAB")
        # NAV now has a Tab tap; the retired SYSTEM/IME layer-tap stays absent.
        self.assertNotIn("lt_ime", EXPANDED)

    def test_thumb_ime_and_nav_survive_all_layer_combinations(self):
        for flags in itertools.product((False, True), repeat=len(LAYER_NAMES) - 1):
            active = {"BASE"} | {name for name, flag in zip(LAYER_NAMES[1:], flags) if flag}
            with self.subTest(active=sorted(active)):
                code = "LANG2" if "IME_ALT" in active else "LANG1"
                self.assertEqual(resolve(active, 37), f"&ime_shift LEFT_SHIFT {code}")
                self.assertEqual(resolve(active, 39), "&lt 5 TAB")

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

    def test_thumb_shift_and_other_modifiers(self):
        self.assertEqual(LAYERS["BASE"][34:37], ["&kp LCTRL", "&kp LEFT_WIN", "&kp LEFT_ALT"])
        self.assertEqual(LAYERS["BASE"][22], "&kp Z")
        self.assertEqual(LAYERS["NAV"][22], "&kp LEFT_SHIFT")
        self.assertEqual(LAYERS["NUM"][22], "&mt LEFT_SHIFT NUMBER_0")
        self.assertIn('flavor = "balanced";', SOURCE)
        self.assertIn("quick-tap-ms = <0>;", SOURCE)

    def test_ime_shift_separates_hold_from_ime_tap(self):
        behavior = re.search(r"(?s)ime_shift:\s*\w+\s*\{(.*?)\};", EXPANDED)[1]
        self.assertIn('compatible = "zmk,behavior-hold-tap";', behavior)
        self.assertIn('#binding-cells = <2>;', behavior)
        self.assertIn('flavor = "hold-preferred";', behavior)
        self.assertIn('tapping-term-ms = <200>;', behavior)
        self.assertIn('quick-tap-ms = <0>;', behavior)
        self.assertEqual(re.findall(r"&([a-z_]+)", behavior), ["kp", "ime_toggle"])
        # These are distinct physical positions: Shift hold and an ordinary Z press.
        # This checks configuration, not ZMK's hold-tap timer or real HID reports.
        for flags in itertools.product((False, True), repeat=len(LAYER_NAMES) - 1):
            active = {"BASE"} | {name for name, flag in zip(LAYER_NAMES[1:], flags) if flag}
            code = "LANG2" if "IME_ALT" in active else "LANG1"
            self.assertEqual(resolve(active, 37), f"&ime_shift LEFT_SHIFT {code}")
            expected = "&kp LEFT_SHIFT" if "NAV" in active else (
                "&mt LEFT_SHIFT NUMBER_0" if "NUM" in active else "&kp Z")
            self.assertEqual(resolve(active, 22), expected)
        self.assertNotIn("&mt LEFT_SHIFT Z", EXPANDED)

    def test_nav_tab_keeps_space_num_and_momentary_hold(self):
        self.assertIn("&lt L_NAV TAB", SOURCE)
        self.assertNotIn("&mo L_NAV", SOURCE)
        # Use the existing standard layer-tap; do not change other layer-tap timing.
        self.assertNotRegex(SOURCE, r"&lt\s*\{")
        for flags in itertools.product((False, True), repeat=len(LAYER_NAMES) - 1):
            active = {"BASE"} | {name for name, flag in zip(LAYER_NAMES[1:], flags) if flag}
            self.assertEqual(resolve(active, 38), "&lt 4 SPACE")
            self.assertEqual(resolve(active, 39), "&lt 5 TAB")

    def test_num_digits_use_shiftable_number_row_codes(self):
        positions = (22, 23, 24, 25, 11, 12, 13, 1, 2, 3)  # 0..9
        for flags in itertools.product((False, True), repeat=3):
            active = {"BASE", "NUM"} | {
                name for name, flag in zip(("IME_ALT", "MOUSE", "SLOW"), flags) if flag
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
        for layer in ("MOUSE", "SLOW", "SCROLL"):
            with self.subTest(layer=layer):
                self.assertEqual(LAYERS[layer][5:10], MOUSE_KEYS)
                self.assertEqual([resolve({"BASE", layer}, p) for p in range(5, 10)], MOUSE_KEYS)
        self.assertEqual(LAYERS["MOUSE"][17:21], ["&trans"] * 4)
        for layer in ("MOUSE", "NAV", "FUNCTION"):
            self.assertEqual(LAYERS[layer][16], "&trans")

    def test_nav_uses_hjkl_and_disables_top_row(self):
        self.assertEqual(LAYERS["NAV"][5:10], ["&none"] * 5)
        self.assertEqual(LAYERS["NAV"][17:21], ARROWS)
        for flags in itertools.product((False, True), repeat=4):
            underlying = {"BASE"} | {
                name for name, flag in zip(("IME_ALT", "MOUSE", "SLOW", "NUM"), flags) if flag
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
                    expected = MOUSE_KEYS if underlying & {"MOUSE", "SLOW"} else LETTERS
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
        self.assertEqual(LAYERS["FUNCTION"][42], "&kp DEL")

    def test_all_layer_combinations_for_new_presses(self):
        for flags in itertools.product((False, True), repeat=len(LAYER_NAMES) - 1):
            active = {"BASE"} | {name for name, flag in zip(LAYER_NAMES[1:], flags) if flag}
            with self.subTest(active=sorted(active)):
                self.assertEqual(resolve(active, 40), "&lt 8 ESCAPE")
                expected_delete = "&kp DEL" if "FUNCTION" in active else "&kp BACKSPACE"
                self.assertEqual(resolve(active, 42), expected_delete)
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
                    expected_top = MOUSE_KEYS if active & {"MOUSE", "SLOW"} else LETTERS
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
            resolve({"BASE", "MOUSE"}, 37), "&ime_shift LEFT_SHIFT LANG1"
        )
        self.assertEqual(resolve({"BASE", "MOUSE"}, 39), "&lt 5 TAB")
        self.assertEqual(resolve({"BASE", "MOUSE"}, 40), "&lt 8 ESCAPE")

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
        for mouse in (set(), {"MOUSE"}, {"SLOW"}, {"MOUSE", "SLOW"}):
            for position, code in base.items():
                self.assertEqual(resolve({"BASE"} | mouse, position), f"&kp {code}")
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
            r"\b(tab|shift_tab|exit_mouse|double_quotation|eq)\s*\{(.*?)\};",
            EXPANDED, re.DOTALL,
        )
        expected = {
            "tab": (11, 12), "shift_tab": (12, 13), "exit_mouse": (11, 10),
            "double_quotation": (20, 21), "eq": (24, 25),
        }
        self.assertEqual(len(combos), len(expected))
        self.assertEqual(len(re.findall(r"key-positions\s*=", EXPANDED)), len(expected))
        for name, body in combos:
            self.assertIn("layers = <0 1 2 3>", body)
            positions = tuple(map(int, re.search(r"key-positions\s*=\s*<(.*?)>", body)[1].split()))
            self.assertEqual(positions, expected[name])
        self.assertEqual(LAYERS["NUM"][28], "&kp LS(INT_YEN)")
        self.assertEqual(LAYERS["SYSTEM"][32], "&bt BT_CLR_ALL")
        self.assertEqual(LAYERS["SYSTEM"][33], "&bt BT_CLR")


    def test_nm_pointing_pair_preserves_letters_symbols_and_function_keys(self):
        self.assertEqual(LAYERS["BASE"][29:31], ["&lt 7 N", "&kp M"])
        for layer in ("MOUSE", "SLOW", "SCROLL"):
            self.assertEqual(LAYERS[layer][29:31], ["&mo 7", "&mo 3"])
            self.assertEqual(LAYERS[layer], LAYERS["MOUSE"])
        for pointer in ({"MOUSE"}, {"SLOW"}, {"MOUSE", "SLOW"}):
            self.assertEqual(
                [resolve({"BASE", "NUM"} | pointer, p) for p in (29, 30)],
                ["&kp RIGHT_BRACKET", "&kp NON_US_HASH"],
            )
            self.assertEqual(
                [resolve({"BASE", "FUNCTION"} | pointer, p) for p in (29, 30)],
                ["&kp F11", "&kp F12"],
            )
        # The old inner key no longer enters SCROLL, in any layer combination.
        for flags in itertools.product((False, True), repeat=len(LAYER_NAMES) - 1):
            active = {"BASE"} | {name for name, flag in zip(LAYER_NAMES[1:], flags) if flag}
            expected = "&kp LS(INT_RO)" if "NUM" in active else "&kp MINUS"
            self.assertEqual(resolve(active, 16), expected)

    def test_nm_press_and_release_orders_with_automouse_timeout_in_lookup_model(self):
        # Keep the binding selected at press time, as in a momentary hold.
        # This models configuration semantics, not ZMK's event queue or timing.
        for press_order in itertools.permutations((29, 30)):
            for release_order in itertools.permutations((29, 30)):
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
                        self.assertEqual("SLOW" in active, 30 in held)
                        self.assertEqual("SCROLL" in active, 29 in held)
                        if held:
                            self.assertEqual([resolve(active, p) for p in range(5, 10)], MOUSE_KEYS)
                            other = next(iter(held))
                            expected = "&mo 7" if position == 29 else "&mo 3"
                            self.assertEqual(resolve(active, position), expected)
                            self.assertEqual(held[other], "SLOW" if other == 30 else "SCROLL")
                    self.assertEqual(active, {"BASE"} if timeout else {"BASE", "MOUSE"})

    def test_slow_is_independent_of_scroll_mode_and_uses_standard_scalers(self):
        self.assertIn("#include <input/processors.dtsi>", SOURCE)
        override = re.search(r"(?s)&trackball_listener\s*\{(.*?)\n\};", EXPANDED)[1]
        self.assertIn("layers = <3>;", override)
        self.assertEqual(
            re.findall(r"&zip_(\w+)_scaler\s+(\d+)\s+(\d+)", override),
            [("xy", "1", "4"), ("scroll", "1", "4")],
        )
        self.assertEqual(override.count("input-processors ="), 1)
        self.assertNotIn("snipe-layers", EXPANDED)
        self.assertNotIn("sensor-bindings", dict(BLOCKS)["SLOW"])
        scroll_layers = set(map(int, re.search(r"scroll-layers = <(.*?)>", EXPANDED)[1].split()))
        for flags in itertools.product((False, True), repeat=len(LAYER_NAMES) - 1):
            active = {"BASE"} | {name for name, flag in zip(LAYER_NAMES[1:], flags) if flag}
            # PMW3610 selects its mode from the highest active layer.
            highest = max(LAYER_NAMES.index(layer) for layer in active)
            self.assertEqual(highest in scroll_layers, "SCROLL" in active and "SYSTEM" not in active)

    def test_system_entry_and_dedicated_settings_are_right_handed(self):
        self.assertEqual(LAYERS["BASE"][40], "&lt 8 ESCAPE")
        entries = [(name, p) for name, keys in LAYERS.items() for p, key in enumerate(keys)
                   if re.match(r"&(?:mo|lt) 8(?: |$)", key)]
        self.assertEqual(entries, [("BASE", 40)])
        # Physical positions verified against boards/shields/roBa/roBa.dtsi.
        right = set(range(5, 10)) | set(range(16, 22)) | set(range(28, 34)) | {40, 41, 42}
        for position, binding in enumerate(LAYERS["SYSTEM"]):
            if position not in right:
                self.assertEqual(binding, "&trans")
        self.assertEqual(LAYERS["SYSTEM"][17:20], [f"&kp NUMBER_{n}" for n in (1, 2, 3)])
        self.assertEqual(LAYERS["SYSTEM"][28], "&bootloader")
        self.assertEqual(LAYERS["SYSTEM"][32:34], ["&bt BT_CLR_ALL", "&bt BT_CLR"])
        self.assertNotIn("lt_ime", EXPANDED)

if __name__ == "__main__":
    unittest.main()
