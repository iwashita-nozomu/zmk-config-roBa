/* SPDX-License-Identifier: MIT */
#define DT_DRV_COMPAT zmk_behavior_mouse_hold

#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <drivers/behavior.h>
#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zmk/behavior.h>
#include <zmk/keymap.h>

#if DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT)
BUILD_ASSERT(DT_NUM_INST_STATUS_OKAY(DT_DRV_COMPAT) == 1);
BUILD_ASSERT(DT_INST_PROP(0, layer) < ZMK_KEYMAP_LAYERS_LEN);

/* U and BASE J+K have independent, paired press/release lifetimes. Standard mo
 * deactivates on either release. Share only this manual layer; AUTO and
 * SCROLL/SLOW retain their existing owners and timers. */
static uint32_t holds;
static uint8_t held_layer;
K_MUTEX_DEFINE(hold_lock);

static int change_hold(bool pressed) {
    int err = 0;
    k_mutex_lock(&hold_lock, K_FOREVER);
    if (pressed) {
        if (holds == UINT32_MAX) {
            err = -EOVERFLOW;
        } else {
            if (holds == 0) {
                held_layer = zmk_keymap_layer_index_to_id(DT_INST_PROP(0, layer));
                err = zmk_keymap_layer_activate(held_layer);
            }
            if (err == 0) {
                ++holds;
            }
        }
    } else if (holds == 0) {
        err = -EINVAL;
    } else {
        /* Keep the acquired stable ID even if Studio reorders layers. */
        if (holds == 1) {
            err = zmk_keymap_layer_deactivate(held_layer);
        }
        if (err == 0) {
            --holds;
        }
    }
    k_mutex_unlock(&hold_lock);
    return err;
}

static int hold_pressed(struct zmk_behavior_binding *binding,
                        struct zmk_behavior_binding_event event) {
    ARG_UNUSED(binding);
    ARG_UNUSED(event);
    return change_hold(true);
}

static int hold_released(struct zmk_behavior_binding *binding,
                         struct zmk_behavior_binding_event event) {
    ARG_UNUSED(binding);
    ARG_UNUSED(event);
    return change_hold(false);
}

static const struct behavior_driver_api api = {
    .binding_pressed = hold_pressed,
    .binding_released = hold_released,
#if IS_ENABLED(CONFIG_ZMK_BEHAVIOR_METADATA)
    .get_parameter_metadata = zmk_behavior_get_empty_param_metadata,
#endif
};

BEHAVIOR_DT_INST_DEFINE(0, NULL, NULL, NULL, NULL, POST_KERNEL,
                        CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &api);
#endif
