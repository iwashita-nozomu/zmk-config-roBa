/* SPDX-License-Identifier: MIT */
#define DT_DRV_COMPAT zmk_behavior_shift_hold

#include <stdbool.h>
#include <drivers/behavior.h>
#include <zephyr/device.h>
#include <zephyr/kernel.h>
#include <zmk/behavior.h>

#if DT_HAS_COMPAT_STATUS_OKAY(DT_DRV_COMPAT)
BUILD_ASSERT(DT_NUM_INST_STATUS_OKAY(DT_DRV_COMPAT) == 1);
BUILD_ASSERT(DT_INST_PROP_LEN(0, bindings) == 1);

/* Hold-tap forwards its original press timestamp on release. Forward directly
 * so Shift precedes the interrupting key, and stamp now so an unused sticky
 * hold's grace starts at release. Sticky-key still owns all state and timing. */
static int forward(struct zmk_behavior_binding *binding,
                   struct zmk_behavior_binding_event event, bool pressed) {
    ARG_UNUSED(binding);
    struct zmk_behavior_binding child = {
        .behavior_dev = DEVICE_DT_NAME(DT_INST_PHANDLE_BY_IDX(0, bindings, 0)),
        .param1 = DT_INST_PHA_BY_IDX(0, bindings, 0, param1),
    };
    event.timestamp = k_uptime_get();
    return zmk_behavior_invoke_binding(&child, event, pressed);
}

static int pressed(struct zmk_behavior_binding *binding,
                   struct zmk_behavior_binding_event event) {
    return forward(binding, event, true);
}

static int released(struct zmk_behavior_binding *binding,
                    struct zmk_behavior_binding_event event) {
    return forward(binding, event, false);
}

static const struct behavior_driver_api api = {
    .binding_pressed = pressed,
    .binding_released = released,
#if IS_ENABLED(CONFIG_ZMK_BEHAVIOR_METADATA)
    .get_parameter_metadata = zmk_behavior_get_empty_param_metadata,
#endif
};

BEHAVIOR_DT_INST_DEFINE(0, NULL, NULL, NULL, NULL, POST_KERNEL,
                        CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &api);
#endif
