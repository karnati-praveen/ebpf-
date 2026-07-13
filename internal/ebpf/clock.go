package ebpf

import (
	"golang.org/x/sys/unix"
)

// readUptime returns seconds since boot on the monotonic clock, the same
// clock bpf_ktime_get_ns uses.
func readUptime() (float64, error) {
	var ts unix.Timespec
	if err := unix.ClockGettime(unix.CLOCK_MONOTONIC, &ts); err != nil {
		return 0, err
	}
	return float64(ts.Sec) + float64(ts.Nsec)/1e9, nil
}
