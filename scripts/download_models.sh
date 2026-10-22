#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
HF="${HF_CLI:-$ROOT/.venv/bin/hf}"
if [[ ! -x "$HF" ]]; then HF="$(command -v hf)"; fi
case "${1:-2b}" in
  2b)
    "$HF" download THUSI-Lab/GameScaling-2B-S1 \
      --revision 8036a8f05659f3ce79c4b98f0ccbee4142a0b53d \
      --local-dir "$ROOT/models/GameScaling-2B-S1"
    ;;
  9b)
    "$HF" download mradermacher/GameScaling-9B-S1-GGUF \
      --revision 24ab3de083e3e45140b5c43e704abb456f1af213 \
      GameScaling-9B-S1.Q4_K_M.gguf GameScaling-9B-S1.mmproj-f16.gguf README.md \
      --local-dir "$ROOT/models/GameScaling-9B-S1-GGUF"
    "$HF" download THUSI-Lab/GameScaling-9B-S1 --revision fe9d94cb5f48d645d5099b6856b7a871e803a22d \
      chat_template.jinja config.json tokenizer_config.json \
      --local-dir "$ROOT/models/GameScaling-9B-S1-GGUF"
    ;;
  *) echo 'Usage: download_models.sh [2b|9b]' >&2; exit 2 ;;
esac
