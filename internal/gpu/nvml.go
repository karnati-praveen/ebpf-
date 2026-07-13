//go:build gpu

package gpu

import (
	"fmt"

	"github.com/NVIDIA/go-nvml/pkg/nvml"
)

// NVML reads real GPU telemetry from device 0. Built only with -tags gpu on
// machines with the NVIDIA driver present.
type NVML struct {
	dev nvml.Device
}

func NewNVML() (*NVML, error) {
	if ret := nvml.Init(); ret != nvml.SUCCESS {
		return nil, fmt.Errorf("nvml init: %s", nvml.ErrorString(ret))
	}
	dev, ret := nvml.DeviceGetHandleByIndex(0)
	if ret != nvml.SUCCESS {
		return nil, fmt.Errorf("nvml device 0: %s", nvml.ErrorString(ret))
	}
	return &NVML{dev: dev}, nil
}

func (n *NVML) Read() Stat {
	st := Stat{SpeedFactor: 1.0}
	if t, ret := n.dev.GetTemperature(nvml.TEMPERATURE_GPU); ret == nvml.SUCCESS {
		st.TempC = float64(t)
	}
	if mem, ret := n.dev.GetMemoryInfo(); ret == nvml.SUCCESS {
		st.VRAMFreeMB = float64(mem.Free) / (1 << 20)
	}
	if reasons, ret := n.dev.GetCurrentClocksThrottleReasons(); ret == nvml.SUCCESS {
		const throttleMask = nvml.ClocksThrottleReasonSwThermalSlowdown |
			nvml.ClocksThrottleReasonHwThermalSlowdown |
			nvml.ClocksThrottleReasonHwPowerBrakeSlowdown
		st.Throttled = reasons&throttleMask != 0
	}
	if st.Throttled {
		// Approximate effective slowdown from current vs. max SM clock.
		cur, r1 := n.dev.GetClockInfo(nvml.CLOCK_SM)
		max, r2 := n.dev.GetMaxClockInfo(nvml.CLOCK_SM)
		if r1 == nvml.SUCCESS && r2 == nvml.SUCCESS && max > 0 {
			st.SpeedFactor = float64(cur) / float64(max)
		}
	}
	return st
}

func (n *NVML) Close() {
	nvml.Shutdown()
}
