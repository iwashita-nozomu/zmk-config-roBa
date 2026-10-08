/* SPDX-License-Identifier: MIT */
#define DT_DRV_COMPAT zmk_behavior_shared_momentary_layer

#include <drivers/behavior.h>
#include <zephyr/kernel.h>
#include <zmk/behavior.h>
#include <zmk/keymap.h>

/* All U/M/combo entries use this owner, never a mix with &mo for the same layer.
 * Standard hold-tap and combo behaviors deliver balanced presses/releases. */
static unsigned int references[ZMK_KEYMAP_LAYERS_LEN];
K_MUTEX_DEFINE(shared_layer_lock);

static int update_layer(struct zmk_behavior_binding *binding, bool down) {
    uint32_t layer = binding->param1;
    if (layer >= ZMK_KEYMAP_LAYERS_LEN) {
        return -EINVAL;
    }
    k_mutex_lock(&shared_layer_lock, K_FOREVER);
    int ret = 0;
    if (down) {
        if (references[layer]++ == 0) {
            ret = zmk_keymap_layer_activate(layer);
        }
    } else if (references[layer] && --references[layer] == 0) {
        ret = zmk_keymap_layer_deactivate(layer);
    }
    k_mutex_unlock(&shared_layer_lock);
    return ret;
}

static int pressed(struct zmk_behavior_binding *binding, struct zmk_behavior_binding_event event) {
    ARG_UNUSED(event);
    return update_layer(binding, true);
}

static int released(struct zmk_behavior_binding *binding, struct zmk_behavior_binding_event event) {
    ARG_UNUSED(event);
    return update_layer(binding, false);
}

#if IS_ENABLED(CONFIG_ZMK_BEHAVIOR_METADATA)
static const struct behavior_parameter_value_metadata layer_values[] = {
    {.display_name = "Layer", .type = BEHAVIOR_PARAMETER_VALUE_TYPE_LAYER_ID},
};
static const struct behavior_parameter_metadata_set parameter_sets[] = {
    {.param1_values = layer_values, .param1_values_len = ARRAY_SIZE(layer_values)},
};
static const struct behavior_parameter_metadata metadata = {
    .sets = parameter_sets,
    .sets_len = ARRAY_SIZE(parameter_sets),
};
#endif

static const struct behavior_driver_api shared_layer_api = {
    .binding_pressed = pressed,
    .binding_released = released,
#if IS_ENABLED(CONFIG_ZMK_BEHAVIOR_METADATA)
    .parameter_metadata = &metadata,
#endif
};

BEHAVIOR_DT_INST_DEFINE(0, NULL, NULL, NULL, NULL, POST_KERNEL,
                        CONFIG_KERNEL_INIT_PRIORITY_DEFAULT, &shared_layer_api);
