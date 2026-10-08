"""Compile the production shared-hold behavior; model only the surrounding API."""

import itertools
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SHIM = r'''
#pragma once
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#include <pthread.h>
#define ZMK_KEYMAP_LAYERS_LEN 10
#define IS_ENABLED(x) 0
#define ARG_UNUSED(x) (void)(x)
#define K_FOREVER -1
struct k_mutex { pthread_mutex_t mutex; };
#define K_MUTEX_DEFINE(name) struct k_mutex name
static int k_mutex_lock(struct k_mutex *m, int wait) {
    (void)wait; int r = pthread_mutex_lock(&m->mutex); assert(r == 0); return r;
}
static int k_mutex_unlock(struct k_mutex *m) {
    int r = pthread_mutex_unlock(&m->mutex); assert(r == 0); return r;
}
struct zmk_behavior_binding { uint32_t param1; };
struct zmk_behavior_binding_event { uint32_t position; };
struct behavior_driver_api {
    int (*binding_pressed)(struct zmk_behavior_binding *, struct zmk_behavior_binding_event);
    int (*binding_released)(struct zmk_behavior_binding *, struct zmk_behavior_binding_event);
};
#define BEHAVIOR_DT_INST_DEFINE(i, init, pm, data, cfg, level, priority, api) \
    const struct behavior_driver_api *driver = api
static bool active[ZMK_KEYMAP_LAYERS_LEN];
static int zmk_keymap_layer_activate(uint8_t id) { active[id] = true; return 0; }
static int zmk_keymap_layer_deactivate(uint8_t id) { active[id] = false; return 0; }
'''

REPLAY = r'''
#include SOURCE
static void key(unsigned position, bool down, unsigned layer) {
    struct zmk_behavior_binding binding = {.param1 = layer};
    struct zmk_behavior_binding_event event = {.position = position};
    assert((down ? driver->binding_pressed(&binding, event) :
                   driver->binding_released(&binding, event)) == 0);
}
int main(void) {
    assert(pthread_mutex_init(&shared_layer_lock.mutex, NULL) == 0);
    const unsigned owners[] = {6, 30, UINT32_MAX}; /* U, M, virtual combo position */
    const unsigned orders[][3] = {ORDERS};
    for (unsigned i = 0; i < 6; i++) {
        for (unsigned j = 0; j < 6; j++) {
            for (unsigned p = 0; p < 3; p++) key(owners[orders[i][p]], true, 3);
            active[2] = true; zmk_keymap_layer_deactivate(2); /* Automatic expiry. */
            assert(active[3]);
            for (unsigned p = 0; p < 3; p++) {
                key(owners[orders[j][p]], false, 3);
                assert(active[3] == (p != 2));
            }
        }
    }
    for (unsigned p = 0; p < 3; p++) {
        key(owners[p], true, 3); assert(active[3]);
        key(owners[p], false, 3); assert(!active[3]);
    }
    key(6, true, 3); key(30, true, 3); key(21, true, 4);
    active[5] = true; active[8] = true; /* NUM / SCROLL belong to other owners. */
    key(6, false, 3); assert(active[3]);
    key(30, false, 3); assert(!active[3]);
    assert(active[4] && active[5] && active[8]);
    key(21, false, 4); assert(!active[4] && active[5] && active[8]);
    key(6, false, 3); /* Unmatched release must not underflow. */
    key(6, true, 3); key(6, false, 3); assert(!active[3]);
    struct zmk_behavior_binding invalid = {.param1 = 10};
    struct zmk_behavior_binding_event event = {.position = 6};
    assert(driver->binding_pressed(&invalid, event) == -EINVAL);
    assert(driver->binding_released(&invalid, event) == -EINVAL);
    assert(pthread_mutex_destroy(&shared_layer_lock.mutex) == 0);
    return 0;
}
'''


class SharedLayerTests(unittest.TestCase):
    def test_production_shared_holds(self):
        root = Path(__file__).resolve().parents[1]
        source = root / "src/behavior_shared_momentary_layer.c"
        orders = ",".join("{" + ",".join(map(str, order)) + "}"
                          for order in itertools.permutations(range(3)))
        with tempfile.TemporaryDirectory(prefix="roba-shared-hold-") as directory:
            temp = Path(directory)
            (temp / "shim.h").write_text(SHIM)
            for name in ("drivers/behavior.h", "zephyr/kernel.h", "zmk/behavior.h", "zmk/keymap.h"):
                header = temp / name
                header.parent.mkdir(parents=True, exist_ok=True)
                header.write_text('#include "shim.h"\n')
            (temp / "replay.c").write_text(REPLAY.replace("ORDERS", orders))
            subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-pthread", "-O1",
                            "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
                            "-fno-sanitize-recover=all", "-I", str(temp),
                            f'-DSOURCE="{source}"', str(temp / "replay.c"),
                            "-o", str(temp / "replay")], check=True)
            subprocess.run([str(temp / "replay")], check=True)
