/* SPDX-License-Identifier: MIT */
#define DT_DRV_COMPAT zmk_input_processor_motion_dwell

#include <drivers/input_processor.h>
#include <zephyr/kernel.h>
#include <zmk/event_manager.h>
#include <zmk/events/keycode_state_changed.h>
#include <zmk/events/layer_state_changed.h>
#include <zmk/keymap.h>

#include "motion_dwell.h"

/* roBa has one trackball. The standard delegate alone owns its automatic layer
 * and timeout; the separate MOUSE_HOLD layer is owned by ZMK's momentary key. */
BUILD_ASSERT(DT_NUM_INST_STATUS_OKAY(DT_DRV_COMPAT) == 1);
BUILD_ASSERT(DT_INST_PROP(0, dwell_ms) > 0);
BUILD_ASSERT(DT_INST_PROP(0, max_gap_ms) > 0);

static struct motion_dwell run;
static struct k_spinlock run_lock;

static int reset_on_activity(const zmk_event_t *event) {
    const struct zmk_keycode_state_changed *key = as_zmk_keycode_state_changed(event);
    if ((key && key->state) || as_zmk_layer_state_changed(event)) {
        k_spinlock_key_t lock = k_spin_lock(&run_lock);
        motion_dwell_reset(&run);
        k_spin_unlock(&run_lock, lock);
    }
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(mouse_motion_dwell, reset_on_activity);
ZMK_SUBSCRIPTION(mouse_motion_dwell, zmk_keycode_state_changed);
ZMK_SUBSCRIPTION(mouse_motion_dwell, zmk_layer_state_changed);

static int handle_motion(const struct device *dev, struct input_event *event,
                         uint32_t layer, uint32_t timeout_ms,
                         struct zmk_input_processor_state *state) {
    ARG_UNUSED(dev);
    if (layer >= ZMK_KEYMAP_LAYERS_LEN) {
        return -EINVAL;
    }
    if (event->type != INPUT_EV_REL || event->value == 0 ||
        (event->code != INPUT_REL_X && event->code != INPUT_REL_Y)) {
        return ZMK_INPUT_PROC_CONTINUE;
    }

    uint8_t manual = zmk_keymap_layer_index_to_id(DT_INST_PROP(0, manual_layer));
    if (zmk_keymap_layer_active(manual)) {
        return ZMK_INPUT_PROC_CONTINUE;
    }

    bool active = zmk_keymap_layer_active(zmk_keymap_layer_index_to_id(layer));
    k_spinlock_key_t lock = k_spin_lock(&run_lock);
    bool ready = active || motion_dwell_update(&run, k_uptime_get(),
                                              DT_INST_PROP(0, dwell_ms),
                                              DT_INST_PROP(0, max_gap_ms));
    k_spin_unlock(&run_lock, lock);
    if (!ready) {
        /* Do not suppress cursor motion, only the automatic layer request. */
        return ZMK_INPUT_PROC_CONTINUE;
    }

    /* Never hold the spinlock across the delegate, which may wait on its mutex. */
    return zmk_input_processor_handle_event(DEVICE_DT_GET(DT_INST_PHANDLE(0, delegate)),
                                            event, layer, timeout_ms, state);
}

static const struct zmk_input_processor_driver_api api = {
    .handle_event = handle_motion,
};

DEVICE_DT_INST_DEFINE(0, NULL, NULL, NULL, NULL, POST_KERNEL,
                      CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &api);
