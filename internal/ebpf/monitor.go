// Package ebpf loads the tcpmon CO-RE program and exposes per-link
// network telemetry (sRTT, send throughput) read from its BPF maps.
package ebpf

import (
	"encoding/binary"
	"fmt"
	"net"
	"time"

	"github.com/cilium/ebpf"
	"github.com/cilium/ebpf/link"
	"github.com/cilium/ebpf/rlimit"
)

// LinkSnapshot is one observed TCP flow toward a worker port.
type LinkSnapshot struct {
	SrcIP       string
	DstIP       string
	DstPort     uint16
	SRTTms      float64
	BytesPerSec float64
	Samples     uint64
}

type flowState struct {
	bytes uint64
	seen  time.Time
}

type Monitor struct {
	objs     tcpmonObjects
	links    []link.Link
	prev     map[tcpmonFlowKey]flowState
	prevScan time.Time
}

// NewMonitor loads and attaches the BPF programs. Requires CAP_BPF/CAP_SYS_ADMIN.
func NewMonitor(portMin, portMax uint16) (*Monitor, error) {
	if err := rlimit.RemoveMemlock(); err != nil {
		return nil, fmt.Errorf("remove memlock: %w", err)
	}
	spec, err := loadTcpmon()
	if err != nil {
		return nil, fmt.Errorf("load spec: %w", err)
	}
	for name, val := range map[string]uint16{"port_min": portMin, "port_max": portMax} {
		if v, ok := spec.Variables[name]; ok {
			if err := v.Set(val); err != nil {
				return nil, fmt.Errorf("set %s: %w", name, err)
			}
		}
	}

	m := &Monitor{prev: map[tcpmonFlowKey]flowState{}, prevScan: time.Now()}
	if err := spec.LoadAndAssign(&m.objs, nil); err != nil {
		return nil, fmt.Errorf("load objects: %w", err)
	}

	for _, prog := range []*ebpf.Program{m.objs.TcpProbeHook, m.objs.TcpSendmsgHook} {
		l, err := link.AttachTracing(link.TracingOptions{Program: prog})
		if err != nil {
			m.Close()
			return nil, fmt.Errorf("attach %s: %w", prog.String(), err)
		}
		m.links = append(m.links, l)
	}
	return m, nil
}

// Snapshot returns per-flow stats since the previous call. Flows idle for
// more than staleAfter are dropped from the result.
func (m *Monitor) Snapshot(staleAfter time.Duration) ([]LinkSnapshot, error) {
	now := time.Now()
	elapsed := now.Sub(m.prevScan).Seconds()
	if elapsed <= 0 {
		elapsed = 1
	}

	var (
		key  tcpmonFlowKey
		val  tcpmonFlowVal
		out  []LinkSnapshot
		iter = m.objs.Flows.Iterate()
	)
	bootToWall := now.Add(-monotonicSinceBoot())
	for iter.Next(&key, &val) {
		lastSeen := bootToWall.Add(time.Duration(val.LastSeenNs))
		if now.Sub(lastSeen) > staleAfter {
			delete(m.prev, key)
			continue
		}
		prev := m.prev[key]
		deltaBytes := val.Bytes - prev.bytes
		m.prev[key] = flowState{bytes: val.Bytes, seen: lastSeen}
		out = append(out, LinkSnapshot{
			SrcIP:       be32ToIP(key.Saddr),
			DstIP:       be32ToIP(key.Daddr),
			DstPort:     key.Dport,
			SRTTms:      float64(val.SrttUs) / 1000.0,
			BytesPerSec: float64(deltaBytes) / elapsed,
			Samples:     val.SrttSamples,
		})
	}
	m.prevScan = now
	if err := iter.Err(); err != nil {
		return out, fmt.Errorf("iterate flows: %w", err)
	}
	return out, nil
}

func (m *Monitor) Close() {
	for _, l := range m.links {
		l.Close()
	}
	m.objs.Close()
}

// be32ToIP converts a kernel __be32 address (network-order bytes read as a
// native little-endian u32) back to dotted-quad form.
func be32ToIP(v uint32) string {
	ip := make(net.IP, 4)
	binary.LittleEndian.PutUint32(ip, v)
	return ip.String()
}

// monotonicSinceBoot approximates CLOCK_BOOTTIME for translating
// bpf_ktime_get_ns timestamps; precision of a second is plenty here.
func monotonicSinceBoot() time.Duration {
	var uptime float64
	if data, err := readUptime(); err == nil {
		uptime = data
	}
	return time.Duration(uptime * float64(time.Second))
}
