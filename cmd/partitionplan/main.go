// partitionplan exposes the restricted cost-model planner as a JSON diagnostic.
package main

import (
	"encoding/json"
	"flag"
	"log"
	"os"

	"kubeedgeinfer/internal/partition"
)

func main() {
	objective := flag.String("objective", "capacity", "latency | throughput | capacity")
	flag.Parse()
	var input partition.Input
	decoder := json.NewDecoder(os.Stdin)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&input); err != nil {
		log.Fatal(err)
	}
	result, err := partition.OptimalForObjective(input, partition.Objective(*objective))
	if err != nil {
		log.Fatal(err)
	}
	if err := json.NewEncoder(os.Stdout).Encode(map[string]any{
		"splits": result.Splits(), "pipeline_ms": result.PipelineMs,
		"bottleneck_ms": result.BottleneckMs,
		"objective_ms":  partition.ObjectiveCost(input, result.Splits(), partition.Objective(*objective)),
		"scope":         "ideal cost model; not measured runtime throughput",
	}); err != nil {
		log.Fatal(err)
	}
}
