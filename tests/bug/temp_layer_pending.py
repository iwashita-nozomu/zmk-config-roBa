"""Replay Issue #226 against the production automatic-MOUSE owner.

Run directly or via the repository's unittest entrypoint. Only Zephyr/HID
plumbing is modelled; the state transitions and time predicate are compiled
from src/motion_dwell.c and .h, without source rewriting. Queued work deliberately
survives rescheduling, as in Zephyr. This is not a real Zephyr scheduler or HID
integration test. The retired dependency-only reproduction remains in Git history.
"""

import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

FAKE_HEADERS = r'''
#pragma once
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include "config.h"

struct device { const void *api; };
extern const struct device mouse_device;
struct k_mutex { pthread_mutex_t mutex; };
static inline int k_mutex_lock(struct k_mutex *m, int wait) {
    (void)wait; int ret = pthread_mutex_lock(&m->mutex); assert(ret == 0); return ret;
}
static inline int k_mutex_unlock(struct k_mutex *m) {
    int ret = pthread_mutex_unlock(&m->mutex); assert(ret == 0); return ret;
}
struct k_work { void (*handler)(struct k_work *); bool queued; };
struct k_work_delayable { struct k_work work; int64_t due; };
static int64_t now_ms;
static inline int64_t k_uptime_get(void) { return now_ms; }
static inline int k_work_reschedule(struct k_work_delayable *w, int64_t delay) {
    if (!delay) { w->work.queued = true; w->due = -1; }
    else { w->due = now_ms + delay; } /* Never unsubmit queued work. */
    return 1;
}
#define K_FOREVER -1
#define K_NO_WAIT 0
#define K_MSEC(x) (x)
#define K_MUTEX_DEFINE(name) struct k_mutex name
#define K_WORK_DELAYABLE_DEFINE(name, cb) \
    struct k_work_delayable name = {.work = {.handler = cb}, .due = -1}
#define BUILD_ASSERT(x) _Static_assert(x, #x)
#define ARG_UNUSED(x) (void)(x)
#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
#define MAX(a,b) ((a) > (b) ? (a) : (b))
#define ZMK_KEYMAP_LAYERS_LEN 10
#define ZMK_EV_EVENT_BUBBLE 0
#define ZMK_INPUT_PROC_CONTINUE 0
#define INPUT_EV_REL 2
#define INPUT_REL_X 0
#define INPUT_REL_Y 1
#define INPUT_REL_WHEEL 8
#define DT_NUM_INST_STATUS_OKAY(c) 1
#define DT_INST_PROP(i, p) PROP_##p
#define DEVICE_DT_INST_DEFINE(i, init, pm, data, cfg, level, priority, a) \
    const struct device mouse_device = {.api = a}
struct input_event { int type, code, value; bool sync; };
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
struct zmk_listener { int (*callback)(const zmk_event_t *); };
extern const struct zmk_listener zmk_listener_mouse_motion_dwell;
#define ZMK_LISTENER(name, cb) const struct zmk_listener zmk_listener_##name = {.callback = cb}
#define ZMK_SUBSCRIPTION(...)
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
static uint8_t layer_order[10];
static unsigned activations;
static inline uint8_t zmk_keymap_layer_index_to_id(uint8_t i) { return layer_order[i]; }
static inline bool zmk_keymap_layer_active(uint8_t i) { assert(i < 10); return i == 0 || active_layers[i]; }
static inline int change_layer(uint8_t id, bool on) {
    assert(id < 10); if (active_layers[id] == on) return 0;
    active_layers[id] = on;
    if (on && id == layer_order[AUTO_LAYER]) ++activations;
    zmk_event_t e = {.kind=LAYER, .data.layer={id,on,now_ms}};
    return zmk_listener_mouse_motion_dwell.callback(&e); /* Synchronous recursive event. */
}
static inline int zmk_keymap_layer_activate(uint8_t i) { return change_layer(i,true); }
static inline int zmk_keymap_layer_deactivate(uint8_t i) { return change_layer(i,false); }
'''

REPLAY = r'''
#include PRODUCTION_SOURCE

static void reset_test(void) {
    memset(&mouse, 0, sizeof(mouse)); mouse.layer = UINT8_MAX;
    memset(active_layers, 0, sizeof(active_layers));
    for (unsigned i = 0; i < 10; i++) layer_order[i] = i;
    mouse_work.work.queued = false; mouse_work.due = -1;
    now_ms = 1000; activations = 0;
}
static void advance(int64_t now) {
    assert(now >= now_ms); now_ms = now;
    if (mouse_work.due >= 0 && now_ms >= mouse_work.due) {
        mouse_work.due = -1; mouse_work.work.queued = true;
    }
}
static void input(int code, int value) {
    struct input_event e = {.type=INPUT_EV_REL,.code=code,.value=value,.sync=true};
    struct input_event before = e;
    struct zmk_input_processor_state state = {0};
    const struct zmk_input_processor_driver_api *driver = mouse_device.api;
    assert(driver->handle_event(&mouse_device, &e, AUTO_LAYER, TIMEOUT_MS, &state) == 0);
    assert(e.type == before.type && e.code == before.code && e.value == before.value && e.sync == before.sync);
}
static void motion(void) { input(INPUT_REL_X, 1); }
static void position(uint32_t p, bool down) {
    zmk_event_t e = {.kind=POSITION,.data.pos={p,down,now_ms}};
    assert(zmk_listener_mouse_motion_dwell.callback(&e) == ZMK_EV_EVENT_BUBBLE);
}
static void keycode(int64_t timestamp) {
    zmk_event_t e = {.kind=KEYCODE,.data.key={true,timestamp}};
    assert(zmk_listener_mouse_motion_dwell.callback(&e) == ZMK_EV_EVENT_BUBBLE);
}
static void press_a(void) { position(10, true); keycode(now_ms); }
static void drain(void) {
    if (mouse_work.work.queued) {
        mouse_work.work.queued = false;
        mouse_work.work.handler(&mouse_work.work);
    }
}
static void qualify(void) {
    int64_t start = now_ms;
    for (int t = 0; t <= PROP_dwell_ms; t += 40) { advance(start+t); motion(); }
}
static bool active(void) { return active_layers[layer_order[AUTO_LAYER]]; }

int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    pthread_mutexattr_t attr;
    assert(pthread_mutexattr_init(&attr) == 0);
    assert(pthread_mutexattr_settype(&attr, PTHREAD_MUTEX_RECURSIVE) == 0);
    assert(pthread_mutex_init(&mouse_lock.mutex, &attr) == 0);
    assert(pthread_mutexattr_destroy(&attr) == 0);

    reset_test(); qualify(); assert(!active()); drain(); assert(active());
    advance(2199); drain(); assert(active()); advance(2200); drain(); assert(!active());
    puts("PASS: normal activation and exact 1000ms expiry");

    reset_test(); qualify(); drain(); advance(1201); press_a(); assert(!active());
    puts("PASS: typing after activation exits without consuming key events");

    reset_test(); press_a(); qualify(); drain(); assert(!active());
    advance(1240); motion(); advance(1280); motion(); advance(1299); motion();
    drain(); assert(!active()); advance(1300); motion(); drain(); assert(active());
    puts("PASS: prior idle 299/300ms boundary, overlapping dwell not added delay");

    reset_test(); qualify(); advance(1201); press_a(); drain(); assert(!active());
    advance(1800); drain(); assert(!active()); assert(activations == 0);
    puts("PASS: queued ON cannot survive typing, even after idle elapses");

    reset_test(); qualify(); advance(1201); press_a(); advance(1600); drain();
    assert(!active()); assert(activations == 0);
    puts("PASS: cancelled ON stays cancelled when its first dispatch is after typing idle");

    reset_test(); qualify(); drain(); advance(2200); assert(mouse_work.work.queued);
    advance(2201); motion(); assert(mouse_work.work.queued); drain(); assert(active());
    advance(3200); drain(); assert(active()); advance(3201); drain(); assert(!active());
    puts("PASS: queued old timeout respects the refreshed deadline");

    reset_test(); qualify(); advance(1201); position(10,true); position(11,true);
    /* A+S is then captured by combos, so no keycode or OFF state-change follows. */
    drain(); assert(!active()); assert(activations == 0);
    puts("PASS: raw A+S positions cancel pending ON without a keycode event");

    reset_test(); qualify(); advance(1201); keycode(now_ms); drain(); assert(!active());
    puts("PASS: keycode activity alone cancels pending ON");

    reset_test(); qualify(); change_layer(PROP_manual_layer,true); drain(); assert(!active());
    qualify(); drain(); assert(!active()); assert(active_layers[PROP_manual_layer]);
    change_layer(PROP_manual_layer,false); motion(); drain(); assert(!active());
    puts("PASS: manual entry invalidates pending automatic entry and inhibits renewal");

    reset_test(); qualify(); drain(); change_layer(PROP_manual_layer,true);
    advance(2200); drain(); assert(!active()); assert(active_layers[PROP_manual_layer]);
    puts("PASS: automatic expiry never releases manual MOUSE_HOLD");

    for (unsigned p = 0; p < 43; p++) {
        reset_test(); qualify(); drain(); position(p,true);
        assert(active() == position_excluded(p));
    }
    reset_test(); qualify(); drain(); position(34,true); keycode(now_ms); assert(active());
    puts("PASS: all 43 typing/excluded positions and active modifier keycode");

    reset_test(); qualify(); drain(); change_layer(5,true); change_layer(8,true);
    press_a(); assert(!active()); assert(active_layers[5] && active_layers[8]);
    puts("PASS: typing exit preserves NUM and held SCROLL");

    reset_test(); qualify(); drain(); change_layer(AUTO_LAYER,false);
    drain(); assert(!active()); motion(); drain(); assert(!active());
    puts("PASS: explicit exit resets qualification and stale work cannot resurrect it");

    reset_test(); qualify(); advance(2201); drain(); assert(!active()); assert(activations == 0);
    puts("PASS: ON delayed beyond its motion deadline never flashes active");

    reset_test(); qualify(); drain(); advance(2200); press_a(); qualify();
    advance(2440); motion(); advance(2480); motion(); advance(2500); motion();
    assert(mouse_work.work.queued); drain(); assert(active());
    advance(3499); drain(); assert(active()); advance(3500); drain(); assert(!active());
    puts("PASS: cancelled old lifecycle cannot disable a freshly qualified lifecycle");

    reset_test(); motion(); advance(1080); input(INPUT_REL_Y,1);
    advance(1160); motion(); advance(1241); motion(); drain(); assert(!active());
    for (int64_t t=1281; t<=1441; t+=40) { advance(t); motion(); }
    drain(); assert(active());
    puts("PASS: 80/81ms gaps and mixed X/Y motion retain the production dwell predicate");

    reset_test(); input(INPUT_REL_X,0); input(INPUT_REL_WHEEL,1);
    advance(2000); input(INPUT_REL_WHEEL,-1); drain(); assert(!active());
    qualify(); drain(); assert(active()); advance(2500); input(INPUT_REL_WHEEL,1);
    advance(3200); drain(); assert(!active());
    puts("PASS: zero samples and scroll never qualify or renew automatic XY ownership");

    reset_test(); advance(1100); keycode(1100); keycode(900); qualify(); drain(); assert(!active());
    advance(1340); motion(); advance(1380); motion(); advance(1399); motion();
    advance(1400); motion(); drain(); assert(active());
    puts("PASS: delayed timestamps cannot move last typing time backwards");

    reset_test(); layer_order[AUTO_LAYER]=4; layer_order[4]=AUTO_LAYER;
    qualify(); drain(); assert(active_layers[4]); assert(!active_layers[AUTO_LAYER]);
    advance(2200); drain(); assert(!active_layers[4]);
    puts("PASS: activation, external events and expiry use the same stable layer ID");

    assert(pthread_mutex_destroy(&mouse_lock.mutex) == 0);
    puts("RESULT: 19 lifecycle checks passed");
    return 0;
}
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[2]
    parser.add_argument("--source", type=Path, default=root / "src/motion_dwell.c")
    args = parser.parse_args()
    source = args.source.resolve()
    expanded = subprocess.check_output(
        ["cpp", "-P", "-x", "assembler-with-cpp", "-"],
        input=re.sub(r"^#include .*\n", "", (root / "config/roBa.keymap").read_text(), flags=re.MULTILINE),
        text=True,
    )
    node = re.search(r"(?s)mouse_dwell:\s*\w+\s*\{(.*?)\};", expanded)[1]
    props = {}
    for name in ("manual-layer", "dwell-ms", "max-gap-ms", "require-prior-idle-ms"):
        props[name.replace("-", "_")] = int(re.search(rf"{name}\s*=\s*<(\d+)>", node)[1])
    excluded = re.search(r"excluded-positions\s*=\s*<(.*?)>", node)[1].split()
    config = "\n".join(f"#define PROP_{key} {value}" for key, value in props.items())
    config += "\n#define PROP_excluded_positions {" + ",".join(excluded) + "}\n"
    layer, timeout = re.search(r"&mouse_dwell\s+(\d+)\s+(\d+)", expanded).groups()
    config += f"#define AUTO_LAYER {layer}\n#define TIMEOUT_MS {timeout}\n"
    with tempfile.TemporaryDirectory(prefix="roba-mouse-lifecycle-") as directory:
        temp = Path(directory)
        include = temp / "include"
        include.mkdir()
        (include / "config.h").write_text(config)
        (include / "fake.h").write_text(FAKE_HEADERS)
        for name in re.findall(r"^#include <([^>]+)>", source.read_text(), re.MULTILINE):
            header = include / name
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text("#include <fake.h>\n")
        (temp / "replay.c").write_text(REPLAY)
        command = [
            os.environ.get("CC", "cc"), "-std=c11", "-O1", "-g", "-D_XOPEN_SOURCE=700", "-pthread",
            "-fsanitize=undefined", "-fno-sanitize-recover=all", "-Wall", "-Wextra", "-Werror",
            "-I", str(include), "-I", str(root / "src"), f'-DPRODUCTION_SOURCE="{source}"',
            str(temp / "replay.c"), "-o", str(temp / "replay"),
        ]
        subprocess.run(command, check=True)
        return subprocess.run([str(temp / "replay")], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
