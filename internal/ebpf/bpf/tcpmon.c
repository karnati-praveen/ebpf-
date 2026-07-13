// KubeEdgeInfer TCP link monitor (CO-RE).
//
// Two hooks observe inter-stage pipeline traffic:
//   tp_btf/tcp_probe   -> per-flow smoothed RTT (client-side sockets)
//   fentry/tcp_sendmsg -> per-flow byte counts (send throughput)
//
// Flows are filtered to the worker gRPC port range. Tracepoints are
// kernel-global (kind nodes share one kernel), so the flow key carries the
// source address and the controller attributes flows to pipeline links by
// pod IP.

#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_tracing.h>
#include <bpf/bpf_endian.h>

char LICENSE[] SEC("license") = "GPL";

#define AF_INET 2
#define AF_INET6 10

struct flow_key {
	__u32 saddr;
	__u32 daddr;
	__u16 dport;
	__u16 pad;
};

struct flow_val {
	__u64 bytes;         // cumulative payload bytes via tcp_sendmsg
	__u64 srtt_us;       // most recent smoothed RTT (microseconds)
	__u64 srtt_samples;  // cumulative tcp_probe hits
	__u64 last_seen_ns;
};

struct {
	__uint(type, BPF_MAP_TYPE_LRU_HASH);
	__uint(max_entries, 4096);
	__type(key, struct flow_key);
	__type(value, struct flow_val);
} flows SEC(".maps");

// Worker gRPC port window; set by userspace before load.
volatile const __u16 port_min = 50051;
volatile const __u16 port_max = 50052;

static __always_inline int flow_from_sock(struct sock *sk, struct flow_key *key)
{
	__u16 family = BPF_CORE_READ(sk, __sk_common.skc_family);
	__u16 dport = bpf_ntohs(BPF_CORE_READ(sk, __sk_common.skc_dport));
	if (dport < port_min || dport > port_max)
		return -1;
	if (family == AF_INET) {
		key->saddr = BPF_CORE_READ(sk, __sk_common.skc_rcv_saddr);
		key->daddr = BPF_CORE_READ(sk, __sk_common.skc_daddr);
	} else if (family == AF_INET6) {
		// Dual-stack sockets carry IPv4 as v4-mapped IPv6 (::ffff:a.b.c.d);
		// unwrap those, skip native IPv6.
		__u32 s[4], d[4];
		BPF_CORE_READ_INTO(&s, sk, __sk_common.skc_v6_rcv_saddr.in6_u.u6_addr32);
		BPF_CORE_READ_INTO(&d, sk, __sk_common.skc_v6_daddr.in6_u.u6_addr32);
		if (d[0] || d[1] || d[2] != bpf_htonl(0x0000ffff))
			return -1;
		key->saddr = s[3];
		key->daddr = d[3];
	} else {
		return -1;
	}
	key->dport = dport;
	key->pad = 0;
	return 0;
}

static __always_inline struct flow_val *flow_lookup_or_init(struct flow_key *key)
{
	struct flow_val *val = bpf_map_lookup_elem(&flows, key);
	if (val)
		return val;
	struct flow_val zero = {};
	bpf_map_update_elem(&flows, key, &zero, BPF_NOEXIST);
	return bpf_map_lookup_elem(&flows, key);
}

SEC("tp_btf/tcp_probe")
int BPF_PROG(tcp_probe_hook, struct sock *sk, struct sk_buff *skb)
{
	struct flow_key key = {};
	if (flow_from_sock(sk, &key))
		return 0;

	struct tcp_sock *tp = (struct tcp_sock *)sk;
	__u32 srtt = BPF_CORE_READ(tp, srtt_us) >> 3;  // stored <<3 with fraction

	struct flow_val *val = flow_lookup_or_init(&key);
	if (!val)
		return 0;
	val->srtt_us = srtt;
	__sync_fetch_and_add(&val->srtt_samples, 1);
	val->last_seen_ns = bpf_ktime_get_ns();
	return 0;
}

SEC("fentry/tcp_sendmsg")
int BPF_PROG(tcp_sendmsg_hook, struct sock *sk, struct msghdr *msg, size_t size)
{
	struct flow_key key = {};
	if (flow_from_sock(sk, &key))
		return 0;

	struct flow_val *val = flow_lookup_or_init(&key);
	if (!val)
		return 0;
	__sync_fetch_and_add(&val->bytes, size);
	val->last_seen_ns = bpf_ktime_get_ns();
	return 0;
}
