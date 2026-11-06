/* Tests the production time/distance predicate, not a reimplementation of it. */
#include <assert.h>
#include "../src/motion_dwell.h"

int main(void) {
    struct motion_dwell run = {0};
    /* Boot timestamp zero is a valid first sample. Boundary is inclusive. */
    assert(!motion_dwell_update(&run, 0, 200, 80, 1, 1));
    assert(!motion_dwell_update(&run, 80, 200, 80, 1, 1));
    assert(!motion_dwell_update(&run, 160, 200, 80, 1, 1));
    assert(!motion_dwell_update(&run, 199, 200, 80, 1, 1));
    assert(motion_dwell_update(&run, 200, 200, 80, 1, 1));
    assert(motion_dwell_update(&run, 200, 200, 80, 1, 1)); /* XY in one packet */

    /* A touch followed by silence never matures on the next isolated touch. */
    motion_dwell_reset(&run);
    for (int64_t t = 1000; t < 10000; t += 500) {
        assert(!motion_dwell_update(&run, t, 200, 80, 1, 1));
    }
    /* 81ms exceeds the gap, even if the old run would have reached 200ms. */
    motion_dwell_reset(&run);
    assert(!motion_dwell_update(&run, 10000, 200, 80, 1, 1));
    assert(!motion_dwell_update(&run, 10080, 200, 80, 1, 1));
    assert(!motion_dwell_update(&run, 10160, 200, 80, 1, 1));
    assert(!motion_dwell_update(&run, 10241, 200, 80, 1, 1));
    assert(!motion_dwell_update(&run, 10321, 200, 80, 1, 1));
    assert(!motion_dwell_update(&run, 10401, 200, 80, 1, 1));
    assert(motion_dwell_update(&run, 10441, 200, 80, 1, 1));

    /* Typing or a layer transition discards all prior progress. */
    motion_dwell_reset(&run);
    assert(!motion_dwell_update(&run, 10442, 200, 80, 1, 1));
    for (int64_t t = 10450; t < 10642; t += 8) {
        assert(!motion_dwell_update(&run, t, 200, 80, 1, 1));
    }
    assert(motion_dwell_update(&run, 10642, 200, 80, 1, 1));
    /* Monotonic uptime beyond the 32-bit range remains valid. */
    motion_dwell_reset(&run);
    int64_t t = INT64_C(1) << 40;
    assert(!motion_dwell_update(&run, t, 200, 80, 1, 1));
    assert(!motion_dwell_update(&run, t + 80, 200, 80, 1, 1));
    assert(!motion_dwell_update(&run, t + 160, 200, 80, 1, 1));
    assert(motion_dwell_update(&run, t + 200, 200, 80, 1, 1));
    /* Time and distance are independent necessary conditions. */
    motion_dwell_reset(&run);
    for (int64_t now = 0; now <= 200; now += 40) {
        assert(!motion_dwell_update(&run, now, 200, 80, 1, 32));
    }
    assert(!motion_dwell_update(&run, 201, 200, 80, -25, 32));
    assert(run.distance == 31);
    assert(motion_dwell_update(&run, 202, 200, 80, 1, 32));
    assert(run.distance == 32);

    motion_dwell_reset(&run);
    assert(!motion_dwell_update(&run, 0, 200, 80, 32, 32));
    assert(!motion_dwell_update(&run, 80, 200, 80, 1, 32));
    assert(!motion_dwell_update(&run, 160, 200, 80, -1, 32));
    assert(!motion_dwell_update(&run, 199, 200, 80, 1, 32));
    assert(motion_dwell_update(&run, 200, 200, 80, -1, 32));

    /* A gap or explicit reset must discard distance as well as elapsed time. */
    motion_dwell_reset(&run);
    assert(!motion_dwell_update(&run, 0, 200, 80, 1000, 32));
    assert(!motion_dwell_update(&run, 81, 200, 80, 1, 32));
    assert(run.distance == 1 && run.first_ms == 81);
    for (int64_t now = 121; now <= 281; now += 40) {
        assert(!motion_dwell_update(&run, now, 200, 80, 1, 32));
    }
    motion_dwell_reset(&run);
    assert(run.distance == 0);

    /* Zero reports neither qualify a run nor bridge an otherwise broken gap. */
    assert(!motion_dwell_update(&run, 0, 200, 80, 0, 32));
    assert(!run.started);
    assert(!motion_dwell_update(&run, 1, 200, 80, 32, 32));
    assert(!motion_dwell_update(&run, 81, 200, 80, 0, 32));
    assert(!motion_dwell_update(&run, 82, 200, 80, 1, 32));
    assert(run.distance == 1 && run.first_ms == 82);

    /* Saturation is safe for the whole signed 32-bit input domain. */
    motion_dwell_reset(&run);
    assert(!motion_dwell_update(&run, 0, 200, 80, INT32_MIN, UINT32_MAX));
    assert(run.distance == UINT32_C(2147483648));
    assert(!motion_dwell_update(&run, 80, 200, 80, INT32_MAX, UINT32_MAX));
    assert(run.distance == UINT32_MAX);
    assert(!motion_dwell_update(&run, 160, 200, 80, INT32_MIN, UINT32_MAX));
    assert(motion_dwell_update(&run, 200, 200, 80, INT32_MAX, UINT32_MAX));
    assert(run.distance == UINT32_MAX);
    return 0;
}
