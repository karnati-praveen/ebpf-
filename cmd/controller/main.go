// KubeEdgeInfer controller: receives node-agent telemetry over gRPC, runs
// the partitioning decider, and applies splits to workers and router.
// --static turns it into the never-repartitioning ablation baseline.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"log"
	"net"
	"net/http"
	"os"
	"strconv"
	"time"

	"google.golang.org/grpc"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/rest"
	"k8s.io/client-go/tools/clientcmd"

	"kubeedgeinfer/gen/pipelinepb"
	"kubeedgeinfer/internal/controller"
)

func kubeConfig() (*rest.Config, error) {
	if cfg, err := rest.InClusterConfig(); err == nil {
		return cfg, nil
	}
	return clientcmd.BuildConfigFromFlags("", os.Getenv("KUBECONFIG"))
}

func main() {
	var (
		namespace   = flag.String("namespace", envOr("NAMESPACE", "kubeedgeinfer"), "namespace to operate in")
		selector    = flag.String("worker-selector", "app=keinfer-worker", "label selector for shard workers")
		workerPort  = flag.Int("worker-port", 50051, "worker gRPC port")
		static      = flag.Bool("static", os.Getenv("STATIC_MODE") == "1", "apply one equal split and never repartition (baseline)")
		grpcAddr    = flag.String("grpc-addr", ":50053", "telemetry gRPC listen address")
		httpAddr    = flag.String("http-addr", ":8081", "debug/state HTTP listen address")
		interval    = flag.Duration("interval", 2*time.Second, "reconcile interval")
		cooldown    = flag.Duration("cooldown", envDurationOr("COOLDOWN_S", 30*time.Second), "repartition cooldown")
		improvement = flag.Float64("improvement", envFloatOr("IMPROVEMENT_FRAC", 0.15), "min fractional bottleneck improvement to repartition")
		heartbeat   = flag.Duration("heartbeat-timeout", 3*time.Second, "node agent staleness before a node is dead")
		reassert    = flag.Duration("reassert-interval", 10*time.Second, "how often to re-push the current layout so a restarted worker/router recovers (0 disables)")
		defLink     = flag.Float64("default-link-ms", 0.5, "assumed hop cost before eBPF data arrives")
		profileOnce = flag.Bool("profile-once", os.Getenv("PROFILE_ONCE") == "1", "freeze link/GPU telemetry after the first reading instead of tracking it live (ablation: offline-profiling baseline vs. continuous eBPF)")
	)
	flag.Parse()

	cfg, err := kubeConfig()
	if err != nil {
		log.Fatalf("kube config: %v", err)
	}
	kube, err := kubernetes.NewForConfig(cfg)
	if err != nil {
		log.Fatalf("clientset: %v", err)
	}
	dyn, err := dynamic.NewForConfig(cfg)
	if err != nil {
		log.Fatalf("dynamic client: %v", err)
	}

	store := controller.NewTelemetryStore()
	ctrl := controller.New(controller.Config{
		Namespace:        *namespace,
		WorkerSelector:   *selector,
		WorkerPort:       *workerPort,
		Static:           *static,
		HeartbeatTimeout: *heartbeat,
		DefaultLinkMs:    *defLink,
		ImprovementFrac:  *improvement,
		Cooldown:         *cooldown,
		Interval:         *interval,
		ReassertInterval: *reassert,
		ProfileOnce:      *profileOnce,
	}, kube, dyn, store)

	lis, err := net.Listen("tcp", *grpcAddr)
	if err != nil {
		log.Fatalf("listen %s: %v", *grpcAddr, err)
	}
	grpcServer := grpc.NewServer()
	pipelinepb.RegisterTelemetryServer(grpcServer, store)
	go func() { log.Fatal(grpcServer.Serve(lis)) }()

	mux := http.NewServeMux()
	mux.HandleFunc("GET /state", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(ctrl.State())
	})
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("ok"))
	})
	go func() { log.Fatal(http.ListenAndServe(*httpAddr, mux)) }()

	log.Printf("controller: ns=%s static=%v profile-once=%v improvement=%.2f cooldown=%s grpc=%s http=%s",
		*namespace, *static, *profileOnce, *improvement, *cooldown, *grpcAddr, *httpAddr)
	ctrl.Run(context.Background())
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envFloatOr(key string, def float64) float64 {
	if v := os.Getenv(key); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	return def
}

func envDurationOr(key string, def time.Duration) time.Duration {
	if v := os.Getenv(key); v != "" {
		if secs, err := strconv.ParseFloat(v, 64); err == nil {
			return time.Duration(secs * float64(time.Second))
		}
	}
	return def
}
