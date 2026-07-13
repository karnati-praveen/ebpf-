package gpu

import (
	"bufio"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
)

// CPUTherm reads real thermal state from a laptop/edge box that has no
// discrete GPU: /sys/class/thermal for temperature, /proc/meminfo for free
// memory (standing in for VRAM headroom). It applies the same
// throttle/unthrottle/speed-derate hysteresis as Sim, but the temperature is
// genuine hardware state, not a model — this is what makes a run "real
// thermal validation" instead of simulated. Most consumer laptops throttle
// CPU clocks under sustained load exactly like a GPU throttles under
// sustained inference, so the same Stat/Reader abstraction applies unchanged.
type CPUTherm struct {
	mu sync.Mutex

	ThrottleTemp   float64
	UnthrottleTemp float64
	ThrottleSpeed  float64
	zonePaths      []string

	throttled bool
}

// NewCPUTherm scans /sys/class/thermal for zones (falling back gracefully if
// the platform exposes none, e.g. inside an unprivileged container) and
// returns a reader with the given throttle thresholds. Thresholds default to
// values typical of a thermally-constrained laptop chassis under sustained
// load if zero.
func NewCPUTherm(throttleTemp, unthrottleTemp, throttleSpeed float64) *CPUTherm {
	if throttleTemp == 0 {
		throttleTemp = envF("CPU_THROTTLE_C", 85)
	}
	if unthrottleTemp == 0 {
		unthrottleTemp = envF("CPU_UNTHROTTLE_C", 78)
	}
	if throttleSpeed == 0 {
		throttleSpeed = envF("CPU_THROTTLE_SPEED", 0.5)
	}
	zones, _ := filepath.Glob("/sys/class/thermal/thermal_zone*/temp")
	return &CPUTherm{
		ThrottleTemp:   throttleTemp,
		UnthrottleTemp: unthrottleTemp,
		ThrottleSpeed:  throttleSpeed,
		zonePaths:      zones,
	}
}

// ReportLoad is a no-op for CPUTherm: unlike the simulated model, real
// hardware temperature already reflects real load — there is nothing to
// feed. Kept to satisfy call sites shared with Sim.
func (c *CPUTherm) ReportLoad(float64) {}

func readTempC(path string) (float64, bool) {
	f, err := os.Open(path)
	if err != nil {
		return 0, false
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	if !sc.Scan() {
		return 0, false
	}
	milliC, err := strconv.ParseFloat(strings.TrimSpace(sc.Text()), 64)
	if err != nil {
		return 0, false
	}
	// Kernel reports millidegrees C; some platforms already report whole
	// degrees (rare, but guard against absurd values either way).
	if milliC > 1000 {
		return milliC / 1000, true
	}
	return milliC, true
}

func maxZoneTempC(paths []string) (float64, bool) {
	max, found := 0.0, false
	for _, p := range paths {
		if t, ok := readTempC(p); ok && (!found || t > max) {
			max, found = t, true
		}
	}
	return max, found
}

func freeMemMB() float64 {
	f, err := os.Open("/proc/meminfo")
	if err != nil {
		return 0
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := sc.Text()
		if strings.HasPrefix(line, "MemAvailable:") {
			fields := strings.Fields(line)
			if len(fields) >= 2 {
				if kb, err := strconv.ParseFloat(fields[1], 64); err == nil {
					return kb / 1024
				}
			}
		}
	}
	return 0
}

func (c *CPUTherm) Read() Stat {
	c.mu.Lock()
	defer c.mu.Unlock()

	temp, ok := maxZoneTempC(c.zonePaths)
	if !ok {
		// No thermal zone exposed (e.g. sandboxed/virtualized node): report a
		// clearly-synthetic-looking value rather than silently pretending to
		// be a healthy real reading.
		return Stat{TempC: -1, SpeedFactor: 1.0, VRAMFreeMB: freeMemMB()}
	}

	if temp >= c.ThrottleTemp {
		c.throttled = true
	} else if temp <= c.UnthrottleTemp {
		c.throttled = false
	}
	speed := 1.0
	if c.throttled {
		speed = c.ThrottleSpeed
	}
	return Stat{
		TempC:       temp,
		VRAMFreeMB:  freeMemMB(),
		Throttled:   c.throttled,
		SpeedFactor: speed,
	}
}
