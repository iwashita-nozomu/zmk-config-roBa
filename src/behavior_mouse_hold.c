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
/* Each configured pointing layer has independent paired holds: F/U/J+K for
 * MOUSE_HOLD and G/right SLOW. Standard mo drops the layer on either release.
 * AUTO and SCROLL keep their existing owners; no timer is added here. */
struct hold_config {
    uint8_t layer;
};

struct hold_data {
    uint32_t holds;
    uint8_t held_layer;
};

K_MUTEX_DEFINE(hold_lock);

static int change_hold(const struct device *dev, bool pressed) {
    const struct hold_config *config = dev->config;
    struct hold_data *data = dev->data;
    int err = 0;
    k_mutex_lock(&hold_lock, K_FOREVER);
    if (pressed) {
        if (data->holds == UINT32_MAX) {
            err = -EOVERFLOW;
        } else {
            if (data->holds == 0) {
                data->held_layer = zmk_keymap_layer_index_to_id(config->layer);
                err = zmk_keymap_layer_activate(data->held_layer);
            }
            if (err == 0) {
                ++data->holds;
            }
        }
    } else if (data->holds == 0) {
        err = -EINVAL;
    } else {
        /* Keep the acquired stable ID even if Studio reorders layers. */
        if (data->holds == 1) {
            err = zmk_keymap_layer_deactivate(data->held_layer);
        }
        if (err == 0) {
            --data->holds;
        }
    }
    k_mutex_unlock(&hold_lock);
    return err;
}

static int hold_pressed(struct zmk_behavior_binding *binding,
                        struct zmk_behavior_binding_event event) {
    ARG_UNUSED(event);
    return change_hold(zmk_behavior_get_binding(binding->behavior_dev), true);
}

static int hold_released(struct zmk_behavior_binding *binding,
                         struct zmk_behavior_binding_event event) {
    ARG_UNUSED(event);
    return change_hold(zmk_behavior_get_binding(binding->behavior_dev), false);
}

static const struct behavior_driver_api api = {
    .binding_pressed = hold_pressed,
    .binding_released = hold_released,
#if IS_ENABLED(CONFIG_ZMK_BEHAVIOR_METADATA)
    .get_parameter_metadata = zmk_behavior_get_empty_param_metadata,
#endif
};

#define HOLD_INST(n)                                                                                \
    BUILD_ASSERT(DT_INST_PROP(n, layer) < ZMK_KEYMAP_LAYERS_LEN);                                     \
    static const struct hold_config config_##n = {.layer = DT_INST_PROP(n, layer)};                   \
    static struct hold_data data_##n;                                                               \
    BEHAVIOR_DT_INST_DEFINE(n, NULL, NULL, &data_##n, &config_##n, POST_KERNEL,                        \
                            CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &api);

DT_INST_FOREACH_STATUS_OKAY(HOLD_INST)
#endif
