//go:build gpu

package main

import "shardwise/internal/gpu"

func newNVML() (gpu.Reader, error) {
	return gpu.NewNVML()
}
