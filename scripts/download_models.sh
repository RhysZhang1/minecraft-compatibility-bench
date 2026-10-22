#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
hf download mradermacher/GameScaling-9B-S1-GGUF \
  --revision 24ab3de083e3e45140b5c43e704abb456f1af213 \
  GameScaling-9B-S1.Q4_K_M.gguf GameScaling-9B-S1.mmproj-f16.gguf README.md \
  --local-dir "$ROOT/models/GameScaling-9B-S1-GGUF"
hf download THUSI-Lab/GameScaling-9B-S1 --revision fe9d94cb5f48d645d5099b6856b7a871e803a22d \
  chat_template.jinja config.json tokenizer_config.json \
  --local-dir "$ROOT/models/GameScaling-9B-S1-GGUF"
