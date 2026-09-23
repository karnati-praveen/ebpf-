// Package peerconn dials the other components of this system: workers,
// router, controller.
//
// gRPC's default reconnect backoff grows to 120 s, which suits distant
// services but not a handful of known peers that are expected to restart. When
// a worker dies and comes back, a cached connection to it keeps waiting out its
// backoff, and fail-fast RPCs return the STALE dial error ("connection refused")
// the whole time. In a device-loss experiment that made recovery time measure
// gRPC's backoff schedule instead of the system -- about 14 s of it in the
// local rehearsal. Capping the backoff at 2 s, and having control-plane RPCs
// wait for readiness within their deadline, removes that confound.
package peerconn

import (
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/backoff"
	"google.golang.org/grpc/credentials/insecure"
)

// MaxBackoff bounds how long a connection to a restarted peer can stay down
// after the peer is listening again.
const MaxBackoff = 2 * time.Second

// Dial returns a client connection to a peer with short reconnect backoff.
func Dial(addr string) (*grpc.ClientConn, error) {
	return grpc.NewClient(addr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithConnectParams(grpc.ConnectParams{
			Backoff: backoff.Config{
				BaseDelay:  200 * time.Millisecond,
				Multiplier: 1.6,
				Jitter:     0.2,
				MaxDelay:   MaxBackoff,
			},
			MinConnectTimeout: 2 * time.Second,
		}))
}
