# Shard worker + router image. GPT-2 support is opt-in at build time because
# the torch wheel adds several hundred MB (build with --build-arg
# WITH_GPT2=1). WITH_CUDA=1 pulls the CUDA-enabled torch wheel instead of the
# CPU-only one, for worker pods scheduled onto real GPU nodes (see
# docs/gpu-hardware.md) -- the base image stays python:3.12-slim either way;
# the NVIDIA driver + nvidia-container-toolkit on the host is what actually
# exposes the GPU, the torch cuXXX wheel bundles the CUDA runtime it needs.
FROM python:3.12-slim

ARG WITH_GPT2=0
ARG WITH_CUDA=0
ARG TORCH_CUDA_INDEX=https://download.pytorch.org/whl/cu121

WORKDIR /app
COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ "$WITH_GPT2" = "1" ] && [ "$WITH_CUDA" = "1" ]; then \
      pip install --no-cache-dir --index-url ${TORCH_CUDA_INDEX} torch && \
      pip install --no-cache-dir transformers; \
    elif [ "$WITH_GPT2" = "1" ]; then \
      pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch && \
      pip install --no-cache-dir transformers; \
    fi

COPY worker/ /app/
CMD ["python3", "server.py"]
