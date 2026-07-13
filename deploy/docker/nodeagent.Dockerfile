# Requires `make proto` (and bpfgen output committed) before building.
# Build with --build-arg GO_BUILD_TAGS=gpu on a machine with the NVIDIA
# driver present to enable real NVML telemetry (go-nvml uses cgo + dlopen'd
# libnvidia-ml.so, hence CGO_ENABLED=1 and a glibc-based final image below
# instead of the static one used for the default build).
FROM golang:1.26 AS build
WORKDIR /src
ARG GO_BUILD_TAGS=""
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN if [ -n "$GO_BUILD_TAGS" ]; then \
      CGO_ENABLED=1 go build -tags "$GO_BUILD_TAGS" -o /nodeagent ./cmd/nodeagent; \
    else \
      CGO_ENABLED=0 go build -o /nodeagent ./cmd/nodeagent; \
    fi

# base (not static) so the glibc the cgo/nvml build needs is present; the
# plain CGO_ENABLED=0 binary runs fine on this image too.
FROM gcr.io/distroless/base-debian12
COPY --from=build /nodeagent /nodeagent
ENTRYPOINT ["/nodeagent"]
