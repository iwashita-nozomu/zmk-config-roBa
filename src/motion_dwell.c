/* SPDX-License-Identifier: MIT */
#define DT_DRV_COMPAT zmk_input_processor_motion_dwell

#include <drivers/input_processor.h>
#include <zephyr/kernel.h>
#include <zmk/event_manager.h>
#include <zmk/events/keycode_state_changed.h>
#include <zmk/events/layer_state_changed.h>
#include <zmk/events/position_state_changed.h>
#include <zmk/keymap.h>

#include "motion_dwell.h"

/* One trackball, one automatic owner. Work reconciles current state, never a
 * queued ON/OFF command. MOUSE_HOLD remains owned by the U hold. */
BUILD_ASSERT(DT_NUM_INST_STATUS_OKAY(DT_DRV_COMPAT) == 1);
BUILD_ASSERT(DT_INST_PROP(0, dwell_ms) > 0);
BUILD_ASSERT(DT_INST_PROP(0, max_gap_ms) > 0);

static struct {
    struct motion_dwell run;
    int64_t last_key_ms;
    int64_t expires_ms;
    uint8_t layer;
    bool requested;
} mouse = {.layer = UINT8_MAX};

/* Layer changes synchronously raise events that re-enter this listener. Zephyr
 * mutexes are recursive; do not use a spinlock across those callbacks. */
K_MUTEX_DEFINE(mouse_lock);
static void reconcile(struct k_work *work);
static K_WORK_DELAYABLE_DEFINE(mouse_work, reconcile);
static const uint16_t excluded_positions[] = DT_INST_PROP(0, excluded_positions);

static bool mouse_active(void) {
    return mouse.layer < ZMK_KEYMAP_LAYERS_LEN && zmk_keymap_layer_active(mouse.layer);
}

static bool manual_active(void) {
    return zmk_keymap_layer_active(
        zmk_keymap_layer_index_to_id(DT_INST_PROP(0, manual_layer)));
}

static bool position_excluded(uint32_t position) {
    for (size_t i = 0; i < ARRAY_SIZE(excluded_positions); i++) {
        if (excluded_positions[i] == position) {
            return true;
        }
    }
    return false;
}

/* Cancellation is authoritative even if a worker has already been dispatched.
 * Caller holds mouse_lock. A stale wakeup is harmless and needs no cancellation. */
static void cancel_request(void) {
    mouse.requested = false;
    motion_dwell_reset(&mouse.run);
}

static int handle_activity(const zmk_event_t *event) {
    const struct zmk_position_state_changed *position = as_zmk_position_state_changed(event);
    const struct zmk_keycode_state_changed *key = as_zmk_keycode_state_changed(event);
    const struct zmk_layer_state_changed *layer = as_zmk_layer_state_changed(event);

    k_mutex_lock(&mouse_lock, K_FOREVER);
    if (position && position->state && !position_excluded(position->position)) {
        cancel_request();
        if (mouse_active()) {
            zmk_keymap_layer_deactivate(mouse.layer);
        }
    } else if (key && key->state) {
        mouse.last_key_ms = MAX(mouse.last_key_ms, key->timestamp);
        motion_dwell_reset(&mouse.run);
        /* Excluded modifier/copy keys preserve an active mouse layer, but may
         * not leave a pending activation alive across a new keystroke. */
        if (!mouse_active()) {
            cancel_request();
        }
    } else if (layer) {
        motion_dwell_reset(&mouse.run);
        /* Includes explicit exit and manual entry before queued ON executes. */
        if (!mouse_active()) {
            cancel_request();
        }
    }
    k_mutex_unlock(&mouse_lock);
    return ZMK_EV_EVENT_BUBBLE;
}

ZMK_LISTENER(mouse_motion_dwell, handle_activity);
ZMK_SUBSCRIPTION(mouse_motion_dwell, zmk_position_state_changed);
ZMK_SUBSCRIPTION(mouse_motion_dwell, zmk_keycode_state_changed);
ZMK_SUBSCRIPTION(mouse_motion_dwell, zmk_layer_state_changed);

static void reconcile(struct k_work *work) {
    ARG_UNUSED(work);
    k_mutex_lock(&mouse_lock, K_FOREVER);
    int64_t now = k_uptime_get();
    if (!mouse.requested) {
        goto out;
    }
    if (now >= mouse.expires_ms) {
        cancel_request();
        if (mouse_active()) {
            zmk_keymap_layer_deactivate(mouse.layer);
        }
        goto out;
    }
    if (!mouse_active()) {
        if (manual_active() ||
            now - mouse.last_key_ms < DT_INST_PROP(0, require_prior_idle_ms)) {
            cancel_request();
            goto out;
        }
        zmk_keymap_layer_activate(mouse.layer);
    }
    /* Rescheduling does not unsubmit old work. An old timeout reaching this
     * point merely rearms against the latest deadline; it cannot turn us off. */
    if (mouse.requested) {
        int64_t remaining = mouse.expires_ms - k_uptime_get();
        k_work_reschedule(&mouse_work, remaining > 0 ? K_MSEC(remaining) : K_NO_WAIT);
    }
out:
    k_mutex_unlock(&mouse_lock);
}

static int handle_motion(const struct device *dev, struct input_event *event,
                         uint32_t layer, uint32_t timeout_ms,
                         struct zmk_input_processor_state *state) {
    ARG_UNUSED(dev);
    ARG_UNUSED(state);
    if (layer >= ZMK_KEYMAP_LAYERS_LEN || timeout_ms == 0) {
        return -EINVAL;
    }
    if (event->type != INPUT_EV_REL || event->value == 0 ||
        (event->code != INPUT_REL_X && event->code != INPUT_REL_Y)) {
        return ZMK_INPUT_PROC_CONTINUE;
    }

    k_mutex_lock(&mouse_lock, K_FOREVER);
    mouse.layer = zmk_keymap_layer_index_to_id(layer);
    if (!manual_active()) {
        int64_t now = k_uptime_get();
        bool active = mouse_active();
        bool ready = active || motion_dwell_update(&mouse.run, now,
                                                   DT_INST_PROP(0, dwell_ms),
                                                   DT_INST_PROP(0, max_gap_ms));
        if (ready && (active ||
                      now - mouse.last_key_ms >= DT_INST_PROP(0, require_prior_idle_ms))) {
            mouse.requested = true;
            mouse.expires_ms = now + timeout_ms;
            k_work_reschedule(&mouse_work, active ? K_MSEC(timeout_ms) : K_NO_WAIT);
        }
    }
    k_mutex_unlock(&mouse_lock);
    /* Qualifying the layer must never consume or alter pointer motion. */
    return ZMK_INPUT_PROC_CONTINUE;
}

static const struct zmk_input_processor_driver_api api = {
    .handle_event = handle_motion,
};

DEVICE_DT_INST_DEFINE(0, NULL, NULL, NULL, NULL, POST_KERNEL,
                      CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &api);
