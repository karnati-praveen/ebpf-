//go:build gpu

package main

import "kubeedgeinfer/internal/gpu"

func newNVML() (gpu.Reader, error) {
	return gpu.NewNVML()
}
