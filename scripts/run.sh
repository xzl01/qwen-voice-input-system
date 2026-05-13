#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_DIR=$(cd -- "$SCRIPT_DIR/.." && pwd)

: "${QWEN_ASR_PROJECT:?Set QWEN_ASR_PROJECT to the Qwen3-ASR-GGUF project directory}"
: "${QWEN_ASR_VENV:?Set QWEN_ASR_VENV to the Python virtualenv directory}"

export GGML_VK_DISABLE_F16=1
export LD_LIBRARY_PATH="$QWEN_ASR_PROJECT/qwen_asr_gguf/inference/bin:${LD_LIBRARY_PATH:-}"
exec "$QWEN_ASR_VENV/bin/python3" "$REPO_DIR/src/custom_key_daemon.py" "$@"
