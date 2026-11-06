/* SPDX-License-Identifier: MIT */
#pragma once

#include <stdbool.h>
#include <stdint.h>

/* A run consists only of nonzero motion samples separated by at most max_gap_ms.
 * A new sample must satisfy both duration and accumulated L1 input distance. */
struct motion_dwell {
    bool started;
    int64_t first_ms;
    int64_t last_ms;
    uint32_t distance;
};

static inline void motion_dwell_reset(struct motion_dwell *run) {
    run->started = false;
    run->distance = 0;
}

static inline bool motion_dwell_update(struct motion_dwell *run, int64_t now_ms,
                                       uint32_t duration_ms, uint32_t max_gap_ms,
                                       int32_t delta, uint32_t min_distance) {
    if (delta == 0) {
        return false;
    }
    if (!run->started || now_ms - run->last_ms > max_gap_ms) {
        run->started = true;
        run->first_ms = now_ms;
        run->distance = 0;
    }
    run->last_ms = now_ms;
    /* Count each X/Y report before scaling. Widen before negating INT32_MIN;
     * saturation retains exactly the information needed by the threshold. */
    uint64_t magnitude = delta < 0 ? -(int64_t)delta : delta;
    uint64_t distance = run->distance + magnitude;
    run->distance = distance < min_distance ? (uint32_t)distance : min_distance;
    return now_ms - run->first_ms >= duration_ms && run->distance >= min_distance;
}
