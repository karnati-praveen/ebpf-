package controller

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"kubeedgeinfer/internal/partition"
)

func TestCalibrationFingerprintsAndDuplicateObservations(t *testing.T) {
	identity := CalibrationIdentity{Model: "m", Source: "s", Hardware: "h", Runtime: "r"}
	artifact := CalibrationArtifact{Identity: identity, Observations: []CalibrationObservation{{TransitionID: "one", Cause: "voluntary", Status: "complete", Eligible: true, Ratio: 2}}}
	path := filepath.Join(t.TempDir(), "calibration.json")
	write := func() { raw, _ := json.Marshal(artifact); os.WriteFile(path, raw, 0600) }
	write()
	g, err := LoadCalibration(path, identity)
	if err != nil || len(g.Ratios) != 1 || g.Ratios[0] != 2 || g.ID == "" {
		t.Fatal(g, err)
	}
	other := identity
	other.Hardware = "other"
	if _, err := LoadCalibration(path, other); err == nil {
		t.Fatal("hardware mismatch accepted")
	}
	artifact.Observations = append(artifact.Observations, artifact.Observations[0])
	write()
	if _, err := LoadCalibration(path, identity); err == nil {
		t.Fatal("duplicate transition accepted")
	}
	artifact.Observations = artifact.Observations[:1]
	artifact.Observations[0].Cause = "recovery"
	write()
	if _, err := LoadCalibration(path, identity); err == nil {
		t.Fatal("recovery used to calibrate")
	}
}

func TestOnlineObservationsDeduplicateAndFrozenRemainsFrozen(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		json.NewEncoder(w).Encode(map[string]any{"migrations": []CalibrationObservation{{TransitionID: "one", Cause: "voluntary", Status: "complete", Eligible: true, Ratio: 2}, {TransitionID: "two", Cause: "recovery", Status: "complete", Eligible: true, Ratio: 9}}})
	}))
	defer server.Close()
	for _, online := range []bool{false, true} {
		c := New(Config{TransitionURL: server.URL, CalibrationOnline: online, Policy: partition.PolicyGateCalibrated}, nil, NewTelemetryStore())
		c.observeTransitions(context.Background())
		c.observeTransitions(context.Background())
		expected := 0
		if online {
			expected = 1
		}
		if len(c.calibration.Ratios) != expected {
			t.Fatal(c.calibration)
		}
	}
}
