SHELL := /bin/bash
CLUSTER := kubeedgeinfer
KIND := kind
GOBIN := $(shell go env GOPATH)/bin

.PHONY: all proto build test images cluster-up cluster-down deploy undeploy bench clean

all: proto build

# ---- Code generation ------------------------------------------------------

proto: gen/pipelinepb/pipeline.pb.go worker/gen/pipeline_pb2.py

gen/pipelinepb/pipeline.pb.go: proto/pipeline.proto
	mkdir -p gen
	PATH=$(GOBIN):$$PATH protoc -I proto \
		--go_out=gen --go_opt=module=kubeedgeinfer/gen \
		--go-grpc_out=gen --go-grpc_opt=module=kubeedgeinfer/gen \
		proto/pipeline.proto

worker/gen/pipeline_pb2.py: proto/pipeline.proto
	mkdir -p worker/gen
	python3 -m grpc_tools.protoc -I proto \
		--python_out=worker/gen --grpc_python_out=worker/gen \
		proto/pipeline.proto
	touch worker/gen/__init__.py

# ---- Build ----------------------------------------------------------------

bpfgen:
	go generate ./internal/ebpf/

build: proto
	go build ./...

bin: proto
	mkdir -p bin
	CGO_ENABLED=0 go build -o bin/nodeagent ./cmd/nodeagent
	CGO_ENABLED=0 go build -o bin/controller ./cmd/controller

test: proto
	go test ./...

images: proto
	docker build -t kubeedgeinfer/worker:dev -f deploy/docker/worker.Dockerfile .
	docker build -t kubeedgeinfer/nodeagent:dev -f deploy/docker/nodeagent.Dockerfile .
	docker build -t kubeedgeinfer/controller:dev -f deploy/docker/controller.Dockerfile .

# ---- Cluster lifecycle ----------------------------------------------------

cluster-up:
	$(KIND) get clusters | grep -qx $(CLUSTER) || \
		$(KIND) create cluster --name $(CLUSTER) --config deploy/kind-config.yaml
	@control_plane="$(CLUSTER)-control-plane"; \
	if ! docker exec "$$control_plane" grep -q \
		"server: https://$$control_plane:6443" /etc/kubernetes/kubelet.conf; then \
		echo "repairing kind control-plane kubelet endpoint after container IP change"; \
		docker exec "$$control_plane" sh -c \
			'cp -n /etc/kubernetes/kubelet.conf /etc/kubernetes/kubelet.conf.original && \
			sed -i "s#server: https://[^:]*:6443#server: https://$(CLUSTER)-control-plane:6443#" /etc/kubernetes/kubelet.conf && \
			systemctl restart kubelet'; \
	fi
	kubectl cluster-info --context kind-$(CLUSTER)

cluster-down:
	$(KIND) delete cluster --name $(CLUSTER)

load-images:
	$(KIND) load docker-image --name $(CLUSTER) \
		kubeedgeinfer/worker:dev kubeedgeinfer/nodeagent:dev kubeedgeinfer/controller:dev

deploy: load-images
	kubectl apply -f deploy/manifests/namespace.yaml
	kubectl apply -f deploy/manifests/crd.yaml
	kubectl apply -f deploy/manifests/rbac.yaml
	kubectl apply -f deploy/manifests/workers.yaml
	kubectl apply -f deploy/manifests/nodeagent.yaml
	kubectl apply -f deploy/manifests/controller.yaml
	kubectl apply -f deploy/manifests/pipeline.yaml

undeploy:
	kubectl delete -f deploy/manifests/ --ignore-not-found

# ---- Evaluation -----------------------------------------------------------

bench:
	python3 bench/run.py --all

plot:
	python3 bench/plot.py

verify-gpt2:
	python3 bench/verify_gpt2.py

clean:
	rm -rf gen worker/gen bin
