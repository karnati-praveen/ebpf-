package gpu

import (
	"os"
	"strconv"
	"sync"
	"time"
)

// Sim models a consumer GPU's thermal behavior: temperature relaxes toward
// ambient + K·load with time constant Tau; above ThrottleTemp the card
// throttles to ThrottleSpeed until it cools below UnthrottleTemp. Load is
// reported by the co-located shard worker (its busy fraction), so sustained
// inference genuinely heats the simulated card and the control loop can be
// observed reacting. Bench scenarios may override temperature or speed.
type Sim struct {
	mu sync.Mutex

	AmbientC       float64
	K              float64 // temp rise above ambient at 100% load
	TauS           float64
	ThrottleTemp   float64
	UnthrottleTemp float64
	ThrottleSpeed  float64
	VRAMTotalMB    float64
	VRAMUsedMB     float64

	temp      float64
	load      float64 // EWMA of reported busy fraction
	throttled bool
	lastStep  time.Time

	ovTemp  *float64
	ovSpeed *float64
}

func envF(key string, def float64) float64 {
	if s := os.Getenv(key); s != "" {
		if v, err := strconv.ParseFloat(s, 64); err == nil {
			return v
		}
	}
	return def
}

func NewSim() *Sim {
	ambient := envF("SIM_GPU_AMBIENT_C", 45)
	return &Sim{
		AmbientC: ambient,
		// Full sustained load peaks at ambient+K = 70C, below the 80C
		// throttle point: healthy load never self-throttles; only injected
		// faults (or genuinely broken cooling) do.
		K: envF("SIM_GPU_K", 25),
		TauS:           envF("SIM_GPU_TAU_S", 20),
		ThrottleTemp:   envF("SIM_GPU_THROTTLE_C", 80),
		UnthrottleTemp: envF("SIM_GPU_UNTHROTTLE_C", 75),
		ThrottleSpeed:  envF("SIM_GPU_THROTTLE_SPEED", 0.4),
		VRAMTotalMB:    envF("SIM_GPU_VRAM_MB", 8192),
		VRAMUsedMB:     envF("SIM_GPU_VRAM_USED_MB", 2048),
		temp:           ambient,
		lastStep:       time.Now(),
	}
}

// ReportLoad feeds the worker's busy fraction (0..1) into the thermal model.
func (s *Sim) ReportLoad(frac float64) {
	if frac < 0 {
		frac = 0
	} else if frac > 1 {
		frac = 1
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.step()
	const alpha = 0.3
	s.load = alpha*frac + (1-alpha)*s.load
}

// Override pins temperature and/or speed factor; nil arguments clear that pin.
func (s *Sim) Override(tempC, speedFactor *float64) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.ovTemp, s.ovSpeed = tempC, speedFactor
}

// step advances the thermal state; callers hold s.mu.
func (s *Sim) step() {
	now := time.Now()
	dt := now.Sub(s.lastStep).Seconds()
	s.lastStep = now
	if dt <= 0 {
		return
	}
	if s.ovTemp != nil {
		s.temp = *s.ovTemp
	} else {
		target := s.AmbientC + s.K*s.load
		s.temp += (target - s.temp) * min(dt/s.TauS, 1)
	}
	if s.temp >= s.ThrottleTemp {
		s.throttled = true
	} else if s.temp <= s.UnthrottleTemp {
		s.throttled = false
	}
}

func (s *Sim) Read() Stat {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.step()
	speed := 1.0
	if s.throttled {
		speed = s.ThrottleSpeed
	}
	if s.ovSpeed != nil {
		speed = *s.ovSpeed
	}
	return Stat{
		TempC:       s.temp,
		VRAMFreeMB:  s.VRAMTotalMB - s.VRAMUsedMB,
		Throttled:   s.throttled,
		SpeedFactor: speed,
	}
}
