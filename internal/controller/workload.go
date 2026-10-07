package controller

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"kubeedgeinfer/internal/partition"
	"math"
	"net/http"
	"time"
)

type WorkloadSnapshot struct {
	ActiveRequests      int      `json:"active_requests"`
	RemainingTokens     float64  `json:"remaining_tokens"`
	ObservedAt          float64  `json:"observed_at"`
	ReplayContextTokens *float64 `json:"replay_context_tokens,omitempty"`
}

func readWorkload(ctx context.Context, url string) (WorkloadSnapshot, error) {
	var w WorkloadSnapshot
	ctx, cancel := context.WithTimeout(ctx, 300*time.Millisecond)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return w, err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return w, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return w, fmt.Errorf("workload HTTP status %d", resp.StatusCode)
	}
	if err = json.NewDecoder(io.LimitReader(resp.Body, 4096)).Decode(&w); err != nil {
		return w, err
	}
	age := float64(time.Now().UnixNano())/1e9 - w.ObservedAt
	if w.ActiveRequests < 0 || w.RemainingTokens < 0 || math.IsNaN(w.RemainingTokens) || math.IsInf(w.RemainingTokens, 0) ||
		math.IsNaN(w.ObservedAt) || math.IsInf(w.ObservedAt, 0) || age > 5 || age < -2 || (w.ActiveRequests == 0 && w.RemainingTokens != 0) {
		return w, fmt.Errorf("invalid or stale workload snapshot")
	}
	if w.ReplayContextTokens != nil && (*w.ReplayContextTokens < 0 || math.IsNaN(*w.ReplayContextTokens) || math.IsInf(*w.ReplayContextTokens, 0) || (w.ActiveRequests == 0 && *w.ReplayContextTokens != 0)) {
		return w, fmt.Errorf("invalid replay context budget")
	}
	return w, nil
}

func (c *Controller) observeWorkload(ctx context.Context) {
	if c.cfg.WorkloadURL == "" {
		return
	}
	w, err := readWorkload(ctx, c.cfg.WorkloadURL)
	c.mu.Lock()
	if err != nil {
		c.workloadError = err.Error()
		c.workload = nil
	} else {
		c.workloadError = ""
		c.workload = &w
	}
	c.mu.Unlock()
	c.decider.HoldVoluntary = err != nil || w.ActiveRequests == 0
	if err == nil && c.cfg.Objective == partition.Objective("auto") {
		c.decider.Objective = partition.ObjectiveCapacity
	}
	if c.cfg.LiveReplayContext {
		c.decider.Gate.ReplayContextTokens = nil
		if err == nil && w.ReplayContextTokens != nil {
			c.decider.Gate.ReplayContextTokens = w.ReplayContextTokens
		} else {
			c.decider.HoldVoluntary = true
		}
	}
	if c.cfg.RemainingWorkAware {
		remaining := 0.0
		if err == nil {
			remaining = w.RemainingTokens
		}
		c.decider.Gate.RemainingTokens = &remaining
	}
}
