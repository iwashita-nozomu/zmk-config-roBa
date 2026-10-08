# Register the position listener before ZMK's hold-tap/combo capture and keymap.
# Zephyr creates app before loading this module; ZMK appends its sources later.
target_sources_ifdef(CONFIG_PMW3610 app PRIVATE
  ${CMAKE_CURRENT_LIST_DIR}/src/motion_dwell.c
  ${CMAKE_CURRENT_LIST_DIR}/src/behavior_shared_momentary_layer.c)
