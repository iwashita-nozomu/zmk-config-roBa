/* SPDX-License-Identifier: MIT */
#pragma once

#include <stdbool.h>
#include <stdint.h>

/* A run consists only of nonzero motion samples separated by at most max_gap_ms.
 * No timer can complete a run: a new sample must reach the duration boundary. */
struct motion_dwell {
    bool started;
    int64_t first_ms;
    int64_t last_ms;
};

static inline void motion_dwell_reset(struct motion_dwell *run) {
    run->started = false;
}

static inline bool motion_dwell_update(struct motion_dwell *run, int64_t now_ms,
                                       uint32_t duration_ms, uint32_t max_gap_ms) {
    if (!run->started || now_ms - run->last_ms > max_gap_ms) {
        run->started = true;
        run->first_ms = now_ms;
    }
    run->last_ms = now_ms;
    return now_ms - run->first_ms >= duration_ms;
}
