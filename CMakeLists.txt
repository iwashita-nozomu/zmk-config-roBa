# Register the position listener before ZMK's hold-tap/combo capture and keymap.
# Zephyr creates app before loading this module; ZMK appends its sources later.
target_sources_ifdef(CONFIG_PMW3610 app PRIVATE
  ${CMAKE_CURRENT_LIST_DIR}/src/motion_dwell.c)

# Match ZMK's keymap/behavior boundary; peripherals only forward positions.
if ((NOT CONFIG_ZMK_SPLIT) OR CONFIG_ZMK_SPLIT_ROLE_CENTRAL)
  target_sources(app PRIVATE ${CMAKE_CURRENT_LIST_DIR}/src/behavior_mouse_hold.c)
endif()
