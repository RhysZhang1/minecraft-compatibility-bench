#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
ENGINE="${LLAMA_SERVER_BIN:-/home/rhys/llama.cpp/build/bin/llama-server}"
PROFILE="${1:-balanced}"
MODEL="$ROOT/models/GameScaling-9B-S1-GGUF/GameScaling-9B-S1.Q4_K_M.gguf"
VISION="$ROOT/models/GameScaling-9B-S1-GGUF/GameScaling-9B-S1.mmproj-f16.gguf"
if [[ "$PROFILE" == "cpu" ]]; then
    DEVICE_ARGS=(--device none --gpu-layers 0 --no-mmproj-offload)
elif [[ "$PROFILE" == "balanced" ]]; then
    DEVICE_ARGS=(--gpu-layers "${MODEL_GPU_LAYERS:-8}" --no-mmproj-offload)
else
    echo "Usage: serve_model.sh [cpu|balanced]" >&2; exit 2
fi
exec "$ENGINE" -m "$MODEL" --mmproj "$VISION" "${DEVICE_ARGS[@]}" \
  --host 127.0.0.1 --port 8789 --alias gamescaling --ctx-size 8192 --parallel 1 \
  --threads 6 --threads-batch 6 --batch-size 128 --ubatch-size 64 \
  --special --jinja --chat-template-file "$ROOT/models/GameScaling-9B-S1-GGUF/chat_template.jinja" \
  --reasoning-format none --no-context-shift
