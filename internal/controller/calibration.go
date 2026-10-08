package controller

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"strings"
	"time"

	"kubeedgeinfer/internal/partition"
)

func validNumber(x float64) bool { return !math.IsNaN(x) && !math.IsInf(x, 0) }

type CalibrationIdentity struct {
	Model    string `json:"model"`
	Source   string `json:"source"`
	Hardware string `json:"hardware"`
	Runtime  string `json:"runtime"`
}

type CalibrationObservation struct {
	DurationMs            float64         `json:"duration_ms,omitempty"`
	AssignmentMs          float64         `json:"assignment_ms,omitempty"`
	ReplayMs              float64         `json:"replay_ms,omitempty"`
	MaximumInterruptionMs float64         `json:"maximum_request_interruption_ms,omitempty"`
	AffectedRequests      []string        `json:"affected_requests,omitempty"`
	Requests              json.RawMessage `json:"requests,omitempty"`
	TransitionID          string          `json:"transition_id"`
	Cause                 string          `json:"cause"`
	Status                string          `json:"status"`
	Eligible              bool            `json:"calibration_eligible"`
	Ratio                 float64         `json:"observed_to_predicted_ratio"`
}

type CalibrationArtifact struct {
	Identity     CalibrationIdentity      `json:"identity"`
	Observations []CalibrationObservation `json:"observations"`
}

func (i CalibrationIdentity) Validate() error {
	if i.Model == "" || i.Source == "" || i.Hardware == "" || i.Runtime == "" {
		return fmt.Errorf("all calibration fingerprints are required")
	}
	return nil
}

// LoadCalibration requires an independently generated deployment identity.
// The campaign preflight is responsible for verifying remote fingerprints.
func LoadCalibration(path string, expected CalibrationIdentity) (partition.CalibratedGate, error) {
	var out partition.CalibratedGate
	if err := expected.Validate(); err != nil {
		return out, err
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return out, err
	}
	var artifact CalibrationArtifact
	if err = json.Unmarshal(raw, &artifact); err != nil {
		return out, err
	}
	if artifact.Identity != expected {
		return out, fmt.Errorf("calibration fingerprint mismatch")
	}
	ids := map[string]bool{}
	for _, observation := range artifact.Observations {
		if observation.TransitionID == "" || ids[observation.TransitionID] {
			return out, fmt.Errorf("empty or duplicate calibration transition")
		}
		ids[observation.TransitionID] = true
		if observation.Cause != "voluntary" || observation.Status != "complete" || !observation.Eligible || observation.Ratio <= 0 || !validNumber(observation.Ratio) {
			return out, fmt.Errorf("invalid or unsuccessful calibration observation")
		}
		out.Ratios = append(out.Ratios, observation.Ratio)
	}
	if len(out.Ratios) > 128 {
		return out, fmt.Errorf("calibration exceeds 128 retained observations")
	}
	sum := sha256.Sum256(raw)
	out.ID = hex.EncodeToString(sum[:])
	return out, nil
}

func transitionHTTP(ctx context.Context, url string, body any, target any) error {
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	var payload io.Reader
	method := http.MethodGet
	if body != nil {
		raw, err := json.Marshal(body)
		if err != nil {
			return err
		}
		payload = bytes.NewReader(raw)
		method = http.MethodPost
	}
	req, err := http.NewRequestWithContext(ctx, method, url, payload)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	response, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("transition HTTP status %d", response.StatusCode)
	}
	if target != nil {
		return json.NewDecoder(io.LimitReader(response.Body, 4<<20)).Decode(target)
	}
	return nil
}

func (c *Controller) observeTransitions(ctx context.Context) {
	if c.cfg.TransitionURL == "" {
		return
	}
	var response struct {
		Migrations []CalibrationObservation `json:"migrations"`
	}
	err := transitionHTTP(ctx, c.cfg.TransitionURL, nil, &response)
	c.mu.Lock()
	c.transitionError = ""
	if err != nil {
		c.transitionError = err.Error()
	}
	c.migrations = response.Migrations
	c.mu.Unlock()
	if err != nil {
		if c.cfg.Policy == partition.PolicyGateCalibrated {
			c.decider.HoldVoluntary = true
		}
		return
	}
	for _, r := range response.Migrations {
		if r.Status == "pending" {
			c.decider.HoldVoluntary = true
			continue
		}
		if c.seenTransitions[r.TransitionID] {
			continue
		}
		c.seenTransitions[r.TransitionID] = true
		if c.cfg.CalibrationOnline && r.Cause == "voluntary" && r.Status == "complete" && r.Eligible && validNumber(r.Ratio) && r.Ratio > 0 {
			c.calibration.Ratios = append(c.calibration.Ratios, r.Ratio)
			if len(c.calibration.Ratios) > 128 {
				c.calibration.Ratios = c.calibration.Ratios[len(c.calibration.Ratios)-128:]
			}
			c.calibration.ID = "online:" + c.epoch
		}
	}
}

func (c *Controller) observeForecast(now time.Time, in partition.Input) {
	c.mu.Lock()
	fresh := c.workload != nil && c.workloadError == ""
	c.mu.Unlock()
	for _, w := range in.Workers {
		gpu, ok := c.store.Node(w.Node, c.cfg.HeartbeatTimeout)
		if !ok || !validNumber(gpu.GetSpeedFactor()) || gpu.GetSpeedFactor() <= 0 {
			fresh = false
		}
	}
	// Pricing missing link data with a default is permitted by old policies,
	// but cannot supply uncertainty scenarios for the calibrated policy.
	if c.cfg.LinkSource != LinkSourceNone {
		for i := 1; i < len(in.Workers); i++ {
			w := WorkerRef{Addr: in.Workers[i].Addr}
			if _, ok := c.store.LinkCost(c.cfg.LinkSource, w.ip(), w.port(), 5*time.Second); !ok {
				fresh = false
			}
		}
	}
	c.calibration.Observe(now, in, fresh)
	c.decider.Calibrated = c.calibration
	c.mu.Lock()
	c.calibrationState = map[string]any{"identity": c.calibration.ID, "transitions": len(c.calibration.Ratios), "telemetry_blocks": len(c.calibration.Blocks), "online": c.cfg.CalibrationOnline, "required_probability": c.calibration.RequiredProbability, "minimum_blocks": c.calibration.MinBlocks, "minimum_transitions": c.calibration.MinTransitions, "deployment_identity": c.cfg.CalibrationIdentity}
	c.mu.Unlock()
}

func (c *Controller) migrationBegin(ctx context.Context, generation int64, cause string) (string, error) {
	if c.cfg.TransitionURL == "" {
		return "", nil
	}
	id := fmt.Sprintf("%s:generation:%d", c.epoch, generation)
	prediction := 0.0
	if d := c.decider.LastDecision(); d != nil && cause == "voluntary" {
		prediction = d.BaseTransitionMs
		if prediction == 0 {
			prediction = c.decider.Gate.TransitionMs(c.migrationLayers)
		}
	}
	err := transitionHTTP(ctx, strings.TrimRight(c.cfg.TransitionURL, "/")+"/begin", map[string]any{"transition_id": id, "generation": generation, "cause": cause, "predicted_ms": prediction}, nil)
	if err != nil {
		return "", err
	}
	return id, nil
}
