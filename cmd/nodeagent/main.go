// The node agent is KubeEdgeInfer's WATCH stage: it attaches the tcpmon eBPF
// programs for inter-stage network telemetry, runs the (simulated or NVML)
// GPU reader, serves both to the co-located worker over HTTP, and pushes a
// NodeTelemetry snapshot to the controller every second — which doubles as
// the node's liveness heartbeat.
package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"kubeedgeinfer/gen/pipelinepb"
	kebpf "kubeedgeinfer/internal/ebpf"
	"kubeedgeinfer/internal/gpu"
)

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

type agent struct {
	node   string
	reader gpu.Reader // active telemetry source: sim, cputherm, or nvml
	sim    *gpu.Sim   // non-nil only in sim mode (the only source that supports fault injection)
	mon    *kebpf.Monitor

	mu    sync.Mutex
	links []kebpf.LinkSnapshot
}

// newReader selects the GPU/thermal telemetry source. GPU_MODE=sim (default)
// preserves the existing simulated model for GPU-less CI/codespace
// environments; GPU_MODE=cputherm reads real /sys/class/thermal state, for
// running on laptops that have no discrete GPU but do thermally throttle
// under sustained load; GPU_MODE=nvml requires building with -tags gpu.
func newReader() (gpu.Reader, *gpu.Sim) {
	switch env("GPU_MODE", "sim") {
	case "cputherm":
		log.Printf("gpu telemetry: real CPU thermal (/sys/class/thermal)")
		return gpu.NewCPUTherm(0, 0, 0), nil
	case "nvml":
		if r, err := newNVML(); err == nil {
			log.Printf("gpu telemetry: real NVML")
			return r, nil
		} else {
			log.Printf("WARNING: GPU_MODE=nvml requested but unavailable (%v); falling back to sim", err)
		}
		fallthrough
	default:
		s := gpu.NewSim()
		return s, s
	}
}

func (a *agent) handleGPU(w http.ResponseWriter, r *http.Request) {
	if bf := r.URL.Query().Get("busy_frac"); bf != "" {
		if v, err := strconv.ParseFloat(bf, 64); err == nil && a.sim != nil {
			a.sim.ReportLoad(v)
		}
	}
	json.NewEncoder(w).Encode(a.reader.Read())
}

func (a *agent) handleOverride(w http.ResponseWriter, r *http.Request) {
	var body struct {
		TempC       *float64 `json:"temp_c"`
		SpeedFactor *float64 `json:"speed_factor"`
		Clear       bool     `json:"clear"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	if a.sim == nil {
		http.Error(w, "gpu override is only supported in GPU_MODE=sim (real hardware can't be told what temperature to be)", http.StatusConflict)
		return
	}
	if body.Clear {
		a.sim.Override(nil, nil)
	} else {
		a.sim.Override(body.TempC, body.SpeedFactor)
	}
	log.Printf("gpu override: temp=%v speed=%v clear=%v", body.TempC, body.SpeedFactor, body.Clear)
	json.NewEncoder(w).Encode(map[string]bool{"ok": true})
}

func (a *agent) handleLinks(w http.ResponseWriter, r *http.Request) {
	a.mu.Lock()
	defer a.mu.Unlock()
	json.NewEncoder(w).Encode(a.links)
}

func (a *agent) telemetry() *pipelinepb.NodeTelemetry {
	st := a.reader.Read()
	msg := &pipelinepb.NodeTelemetry{
		Node:        a.node,
		TimestampMs: time.Now().UnixMilli(),
		Gpu: &pipelinepb.GpuStat{
			TempC:       st.TempC,
			VramFreeMb:  st.VRAMFreeMB,
			Throttled:   st.Throttled,
			SpeedFactor: st.SpeedFactor,
		},
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	for _, l := range a.links {
		msg.Links = append(msg.Links, &pipelinepb.LinkStat{
			SrcIp:       l.SrcIP,
			DstIp:       l.DstIP,
			DstPort:     uint32(l.DstPort),
			SrttMs:      l.SRTTms,
			BytesPerSec: l.BytesPerSec,
			Samples:     l.Samples,
		})
	}
	return msg
}

func main() {
	nodeName := env("NODE_NAME", "unknown")
	httpAddr := env("HTTP_ADDR", ":9101")
	controllerAddr := os.Getenv("CONTROLLER_ADDR")
	portMin, _ := strconv.Atoi(env("PORT_MIN", "50051"))
	portMax, _ := strconv.Atoi(env("PORT_MAX", "50052"))

	reader, sim := newReader()
	a := &agent{node: nodeName, reader: reader, sim: sim}

	mon, err := kebpf.NewMonitor(uint16(portMin), uint16(portMax))
	if err != nil {
		log.Printf("WARNING: eBPF monitor unavailable (%v); running without network telemetry", err)
	} else {
		a.mon = mon
		defer mon.Close()
		log.Printf("eBPF tcpmon attached (ports %d-%d)", portMin, portMax)
	}

	// Poll BPF maps once per second.
	go func() {
		if a.mon == nil {
			return
		}
		for range time.Tick(time.Second) {
			snap, err := a.mon.Snapshot(10 * time.Second)
			if err != nil {
				log.Printf("snapshot error: %v", err)
				continue
			}
			a.mu.Lock()
			a.links = snap
			a.mu.Unlock()
		}
	}()

	// Push telemetry to the controller (retrying forever; the agent also
	// works standalone for local development).
	if controllerAddr != "" {
		go func() {
			for {
				conn, err := grpc.NewClient(controllerAddr,
					grpc.WithTransportCredentials(insecure.NewCredentials()))
				if err != nil {
					time.Sleep(2 * time.Second)
					continue
				}
				client := pipelinepb.NewTelemetryClient(conn)
				for range time.Tick(time.Second) {
					ctx, cancel := context.WithTimeout(context.Background(), 900*time.Millisecond)
					_, err := client.Report(ctx, a.telemetry())
					cancel()
					if err != nil {
						log.Printf("telemetry push failed: %v", err)
						break
					}
				}
				conn.Close()
				time.Sleep(2 * time.Second)
			}
		}()
		log.Printf("pushing telemetry to %s", controllerAddr)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /gpu", a.handleGPU)
	mux.HandleFunc("POST /gpu/override", a.handleOverride)
	mux.HandleFunc("GET /links", a.handleLinks)
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("ok"))
	})
	log.Printf("node agent %s listening on %s", nodeName, httpAddr)
	log.Fatal(http.ListenAndServe(httpAddr, mux))
}
