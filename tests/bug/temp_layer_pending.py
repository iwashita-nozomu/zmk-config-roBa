"""Deterministic reproduction of pending temp-layer actions (Issue #226).

Usage: python3 tests/bug/temp_layer_pending.py PATH_TO_ZMK_SOURCE
PATH_TO_ZMK_SOURCE is app/src/pointing/input_processor_temp_layer.c from
ZMK acfd8e5ea76cf23ad1c9b6b99848f97a95224257 (v0.3-branch build dependency).

The real, hash-checked C source is compiled against a minimal, serial work-queue
model. This is NOT a Zephyr scheduler, firmware build, or real HID test. The two
interleavings are deliberately imposed; their frequency/reachability on roBa's
actual thread priorities must be checked separately. No upstream C is vendored.

Expected for the audited source: three controls pass, two contracts fail, exit 1.
No pass-only expectation changes and no firmware/configuration changes are made.
Requires Python 3 and a C compiler with UndefinedBehaviorSanitizer support.
"""

import argparse
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

AUDITED_BLOB = "999e93a35356a90a49e1906dd4923f2582fc42f5"

FAKE_HEADERS = r'''
/* Minimal deterministic work-queue model. Not a Zephyr scheduler emulator. */
#pragma once
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

struct device { void *data; const void *config; const void *api; };
extern const struct device temp_device;
struct k_mutex { int unused; };
struct k_work { void (*handler)(struct k_work *); bool queued; };
struct k_work_delayable { struct k_work work; int64_t due; };
struct k_msgq { size_t size; unsigned count; unsigned char items[4][64]; };
static int64_t now_ms;
static inline int64_t k_uptime_get(void) { return now_ms; }
static inline int k_mutex_lock(struct k_mutex *m, int t) { (void)m; (void)t; return 0; }
static inline int k_mutex_unlock(struct k_mutex *m) { (void)m; return 0; }
static inline void k_mutex_init(struct k_mutex *m) { (void)m; }
static inline int k_msgq_put(struct k_msgq *q, const void *item, int t) {
    (void)t; if (q->count == 4) return -ENOMSG;
    assert(q->size <= 64); memcpy(q->items[q->count++], item, q->size); return 0;
}
static inline int k_msgq_get(struct k_msgq *q, void *item, int t) {
    (void)t; if (!q->count) return -ENOMSG;
    memcpy(item, q->items[0], q->size); --q->count;
    memmove(q->items[0], q->items[1], q->count * sizeof(q->items[0])); return 0;
}
static inline int k_work_submit(struct k_work *w) { w->queued = true; return 0; }
static inline void k_work_init_delayable(struct k_work_delayable *w, void (*cb)(struct k_work *)) {
    w->work.handler = cb; w->due = -1;
}
static inline int k_work_reschedule(struct k_work_delayable *w, int delay) {
    w->due = now_ms + delay; return 0;
}
static inline int k_work_cancel_delayable(struct k_work_delayable *w) { w->due = -1; return 0; }
static inline struct k_work_delayable *k_work_delayable_from_work(struct k_work *w) {
    return (struct k_work_delayable *)w;
}
#define K_FOREVER -1
#define K_MSEC(x) (x)
#define K_WORK_DEFINE(name, cb) struct k_work name = {.handler = cb}
#define K_MSGQ_DEFINE(name, sz, count, align) struct k_msgq name = {.size = sz}
#define ARRAY_INDEX(array, ptr) ((ptr) - (array))
#define ZMK_KEYMAP_LAYERS_LEN 10
#define CONFIG_ZMK_INPUT_PROCESSOR_TEMP_LAYER_MAX_ACTION_EVENTS 4
#define LOG_MODULE_DECLARE(...)
#define LOG_DBG(...) ((void)0)
#define LOG_ERR(...) ((void)0)
#define ZMK_EV_EVENT_BUBBLE 0
#define ZMK_INPUT_PROC_CONTINUE 0
#define ZMK_LISTENER(...)
#define ZMK_SUBSCRIPTION(...)
#define DT_INST_FOREACH_STATUS_OKAY(fn) fn(0)
#define DT_INST_FOREACH_STATUS_OKAY_VARGS(...) 1
#define DT_INST_PROP(inst, p) {5,6,7,8,9,21,29,30,34,35,36,37}
#define DT_INST_PROP_OR(inst, p, def) 300
#define DT_INST_PROP_LEN(inst, p) 12
#define DEVICE_DT_INST_GET(n) (&temp_device)
#define DEVICE_DT_INST_DEFINE(n, init, pm, d, cfg, level, priority, a) \
    const struct device temp_device = {.data = d, .config = cfg, .api = a}
#define POST_KERNEL 0
#define CONFIG_KERNEL_INIT_PRIORITY_DEFAULT 0
struct input_event { int type, code, value; };
struct zmk_input_processor_state { int unused; };
struct zmk_input_processor_driver_api {
    int (*handle_event)(const struct device *, struct input_event *, uint32_t, uint32_t,
                        struct zmk_input_processor_state *);
};
struct zmk_position_state_changed { uint32_t position; bool state; int64_t timestamp; };
struct zmk_keycode_state_changed { bool state; int64_t timestamp; };
struct zmk_layer_state_changed { uint8_t layer; bool state; int64_t timestamp; };
typedef struct {
    enum { POSITION, KEYCODE, LAYER } kind;
    union { struct zmk_position_state_changed pos; struct zmk_keycode_state_changed key;
            struct zmk_layer_state_changed layer; } data;
} zmk_event_t;
static inline const struct zmk_position_state_changed *as_zmk_position_state_changed(const zmk_event_t *e) {
    return e->kind == POSITION ? &e->data.pos : NULL;
}
static inline const struct zmk_keycode_state_changed *as_zmk_keycode_state_changed(const zmk_event_t *e) {
    return e->kind == KEYCODE ? &e->data.key : NULL;
}
static inline const struct zmk_layer_state_changed *as_zmk_layer_state_changed(const zmk_event_t *e) {
    return e->kind == LAYER ? &e->data.layer : NULL;
}
static bool active_layers[10];
static inline uint8_t zmk_keymap_layer_index_to_id(uint8_t i) { return i; }
static inline bool zmk_keymap_layer_active(uint8_t i) { return i == 0 || active_layers[i]; }
static int handle_event_dispatcher(const zmk_event_t *event);
static inline int change_layer(uint8_t layer, bool on) {
    if (active_layers[layer] == on) return 0;
    active_layers[layer] = on;
    zmk_event_t e = {.kind=LAYER, .data.layer={layer,on,now_ms}};
    return handle_event_dispatcher(&e);
}
static inline int zmk_keymap_layer_activate(uint8_t i) { return change_layer(i,true); }
static inline int zmk_keymap_layer_deactivate(uint8_t i) { return change_layer(i,false); }
'''

REPLAY = r'''
/* Compile the unmodified dependency; ZMK_TEMP_LAYER_SOURCE must be a full path. */
#include ZMK_TEMP_LAYER_SOURCE

static void reset_test(void) {
    memset(&processor_temp_layer_data_0, 0, sizeof(processor_temp_layer_data_0));
    memset(active_layers, 0, sizeof(active_layers));
    temp_layer_action_msgq.count = 0;
    layer_action_work.queued = false;
    now_ms = 1000;
    temp_layer_init(&temp_device);
}
static void motion(void) {
    struct input_event event = {.type=2,.code=0,.value=1};
    struct zmk_input_processor_state state = {0};
    assert(temp_layer_handle_event(&temp_device, &event, 2, 1000, &state) == 0);
}
static void press_a(void) {
    zmk_event_t position = {.kind=POSITION, .data.pos={10,true,now_ms}};
    zmk_event_t keycode = {.kind=KEYCODE, .data.key={true,now_ms}};
    assert(handle_event_dispatcher(&position) == ZMK_EV_EVENT_BUBBLE);
    assert(handle_event_dispatcher(&keycode) == ZMK_EV_EVENT_BUBBLE);
}
static void drain(void) { layer_action_work.queued=false; layer_action_work.handler(&layer_action_work); }

int main(void) {
    unsigned failures = 0;
    reset_test(); motion(); drain();
    assert(active_layers[2]);
    now_ms = 2000; layer_disable_callback(&layer_disable_works[2].work); drain();
    assert(!active_layers[2]);
    puts("PASS: normal activation and 1000ms expiry");

    reset_test(); motion(); drain(); ++now_ms; press_a();
    assert(!active_layers[2]);
    puts("PASS: typing after activation deactivates MOUSE");

    reset_test(); press_a(); ++now_ms; motion(); drain();
    assert(!active_layers[2]);
    puts("PASS: motion after a key cannot activate before 300ms idle");

    reset_test(); motion(); ++now_ms; press_a(); drain();
    if (active_layers[2]) {
        ++failures;
        printf("FAIL: queued activation survives typing: MOUSE=on, idle=%lldms (requires 300ms)\n",
               (long long)(now_ms-processor_temp_layer_data_0.state.last_tapped_timestamp));
    }

    reset_test(); motion(); drain(); now_ms=2000;
    layer_disable_callback(&layer_disable_works[2].work);
    ++now_ms; motion(); /* Refresh deadline while the old disable action is queued. */
    int64_t due = layer_disable_works[2].due; drain();
    if (!active_layers[2] && now_ms < due) {
        ++failures;
        printf("FAIL: stale timeout cancels refreshed layer: now=%lld, new_deadline=%lld\n",
               (long long)now_ms,(long long)due);
    }
    printf("RESULT: 3 controls passed; %u contract violations\n", failures);
    return failures ? 1 : 0;
}
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    try:
        source = args.source.read_bytes()
    except OSError as error:
        parser.error(str(error))
    blob = hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest()
    if blob != AUDITED_BLOB:
        parser.error(f"Expected audited blob {AUDITED_BLOB}, got {blob}; review source first")
    compiler = shutil.which("cc")
    if compiler is None:
        parser.error("A C compiler named cc is required")
    with tempfile.TemporaryDirectory(prefix="roba-temp-layer-") as directory:
        root = Path(directory)
        include = root / "include"
        include.mkdir()
        (root / "upstream.c").write_bytes(source)
        (include / "fake.h").write_text(FAKE_HEADERS)
        for name in re.findall(rb"^#include <([^>]+)>", source, re.MULTILINE):
            header = include / name.decode()
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text("#include <fake.h>\n")
        (root / "replay.c").write_text(REPLAY)
        command = [
            compiler, "-std=c11", "-O1", "-g", "-fsanitize=undefined",
            "-fno-sanitize-recover=all", "-Wall", "-Wextra",
            "-Wno-unused-parameter", "-Wno-unused-variable",
            "-I", str(include), '-DZMK_TEMP_LAYER_SOURCE="upstream.c"',
            str(root / "replay.c"), "-o", str(root / "replay"),
        ]
        result = subprocess.run(command, check=False)
        if result.returncode:
            return result.returncode
        print(f"Audited source blob: {blob}", flush=True)
        return subprocess.run([str(root / "replay")], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
