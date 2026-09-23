package gpu

import (
	"sync"
	"time"
)

// Measured reports compute speed derived from the co-located worker's OWN
// execution timing, not from temperature. The worker times each cached decode
// step, divides the time a reference profile predicts for that context by the
// time it actually took, and pushes the smoothed ratio here.
//
// This is how the controller learns about compute slowdown on machines with no
// thermal sensors (cloud VMs) or when the cause is not thermal at all (CPU
// contention, a CPU quota, a co-tenant). Temperature, where available, is
// supporting evidence; measured execution slowdown is what capacity is
// estimated from.
//
// Until the worker has reported anything, speed is 1 (the reference profile).
// A report older than staleAfter is ignored and speed falls back to 1, so a
// worker that stops decoding does not pin a stale slowdown forever.
type Measured struct {
	mu         sync.Mutex
	speed      float64
	reportedAt time.Time
	staleAfter time.Duration
}

func NewMeasured(staleAfter time.Duration) *Measured {
	return &Measured{speed: 1, staleAfter: staleAfter}
}

// Report records a smoothed speed ratio from the worker. Values are clamped to
// a plausible range so one pathological sample cannot drive the partitioner.
func (m *Measured) Report(speed float64) {
	if speed <= 0 {
		return
	}
	if speed < 0.05 {
		speed = 0.05
	}
	if speed > 4 {
		speed = 4
	}
	m.mu.Lock()
	m.speed = speed
	m.reportedAt = time.Now()
	m.mu.Unlock()
}

func (m *Measured) Read() Stat {
	m.mu.Lock()
	defer m.mu.Unlock()
	speed := m.speed
	if m.reportedAt.IsZero() || time.Since(m.reportedAt) > m.staleAfter {
		speed = 1
	}
	return Stat{TempC: -1, VRAMFreeMB: -1, Throttled: speed < 0.9, SpeedFactor: speed}
}
