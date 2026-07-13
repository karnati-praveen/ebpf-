package ebpf

// Regenerate the embedded BPF object with `make bpfgen` (or `go generate`).
// Requires clang and the libbpf headers; vmlinux.h is checked in.

//go:generate go run github.com/cilium/ebpf/cmd/bpf2go -cc clang -target bpfel tcpmon bpf/tcpmon.c -- -I bpf
