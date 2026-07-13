// Package gpu abstracts GPU telemetry. The simulated implementation models
// thermal behavior for GPU-less environments; a real NVML implementation is
// available behind the `gpu` build tag.
package gpu

// Stat is one GPU telemetry sample.
type Stat struct {
	TempC       float64 `json:"temp_c"`
	VRAMFreeMB  float64 `json:"vram_free_mb"`
	Throttled   bool    `json:"throttled"`
	SpeedFactor float64 `json:"speed_factor"` // effective compute multiplier (0, 1]
}

// Reader yields GPU telemetry samples.
type Reader interface {
	Read() Stat
}
