//go:build !gpu

package main

import (
	"fmt"

	"kubeedgeinfer/internal/gpu"
)

func newNVML() (gpu.Reader, error) {
	return nil, fmt.Errorf("built without -tags gpu")
}
