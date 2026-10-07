/* Tests the production time predicate, not a reimplementation of it. */
#include <assert.h>
#include "../src/motion_dwell.h"

int main(void) {
    struct motion_dwell run = {0};
    /* Boot timestamp zero is a valid first sample. Boundary is inclusive. */
    assert(!motion_dwell_update(&run, 0, 200, 80));
    assert(!motion_dwell_update(&run, 80, 200, 80));
    assert(!motion_dwell_update(&run, 160, 200, 80));
    assert(!motion_dwell_update(&run, 199, 200, 80));
    assert(motion_dwell_update(&run, 200, 200, 80));
    assert(motion_dwell_update(&run, 200, 200, 80)); /* XY in one packet */

    /* A touch followed by silence never matures on the next isolated touch. */
    motion_dwell_reset(&run);
    for (int64_t t = 1000; t < 10000; t += 500) {
        assert(!motion_dwell_update(&run, t, 200, 80));
    }
    /* 81ms exceeds the gap, even if the old run would have reached 200ms. */
    motion_dwell_reset(&run);
    assert(!motion_dwell_update(&run, 10000, 200, 80));
    assert(!motion_dwell_update(&run, 10080, 200, 80));
    assert(!motion_dwell_update(&run, 10160, 200, 80));
    assert(!motion_dwell_update(&run, 10241, 200, 80));
    assert(!motion_dwell_update(&run, 10321, 200, 80));
    assert(!motion_dwell_update(&run, 10401, 200, 80));
    assert(motion_dwell_update(&run, 10441, 200, 80));

    /* Typing or a layer transition discards all prior progress. */
    motion_dwell_reset(&run);
    assert(!motion_dwell_update(&run, 10442, 200, 80));
    for (int64_t t = 10450; t < 10642; t += 8) {
        assert(!motion_dwell_update(&run, t, 200, 80));
    }
    assert(motion_dwell_update(&run, 10642, 200, 80));
    /* Monotonic uptime beyond the 32-bit range remains valid. */
    motion_dwell_reset(&run);
    int64_t t = INT64_C(1) << 40;
    assert(!motion_dwell_update(&run, t, 200, 80));
    assert(!motion_dwell_update(&run, t + 80, 200, 80));
    assert(!motion_dwell_update(&run, t + 160, 200, 80));
    assert(motion_dwell_update(&run, t + 200, 200, 80));
    return 0;
}
