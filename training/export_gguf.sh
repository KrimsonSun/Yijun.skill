#!/usr/bin/env bash
# Convert merged HF weights to GGUF Q4_K_M for llama.cpp serving.
# Run on macOS or Linux with llama.cpp built.
#
# Prereq:
#   git clone https://github.com/ggerganov/llama.cpp ~/llama.cpp
#   cd ~/llama.cpp && make -j
#   pip install -r requirements.txt    (in llama.cpp dir)
#
# Usage:
#   ./training/export_gguf.sh <merged_hf_dir> <output_gguf_dir>
# Example:
#   ./training/export_gguf.sh output/yijun-qwen2.5-3b-lora/merged_16bit output/yijun-gguf

set -euo pipefail

MERGED_DIR="${1:?usage: export_gguf.sh <merged_hf_dir> <output_gguf_dir>}"
OUT_DIR="${2:?usage: export_gguf.sh <merged_hf_dir> <output_gguf_dir>}"
LLAMA_CPP="${LLAMA_CPP_DIR:-$HOME/llama.cpp}"

if [ ! -d "$LLAMA_CPP" ]; then
    echo "llama.cpp not found at $LLAMA_CPP — set LLAMA_CPP_DIR or clone it there" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"

echo "[1/2] Converting HF -> fp16 GGUF"
python "$LLAMA_CPP/convert_hf_to_gguf.py" \
    "$MERGED_DIR" \
    --outfile "$OUT_DIR/yijun-f16.gguf" \
    --outtype f16

echo "[2/2] Quantizing fp16 -> Q4_K_M"
"$LLAMA_CPP/llama-quantize" \
    "$OUT_DIR/yijun-f16.gguf" \
    "$OUT_DIR/yijun-Q4_K_M.gguf" \
    Q4_K_M

# Cleanup the large fp16 unless KEEP_FP16=1
if [ "${KEEP_FP16:-0}" != "1" ]; then
    rm -f "$OUT_DIR/yijun-f16.gguf"
fi

echo "Done. Quantized model at $OUT_DIR/yijun-Q4_K_M.gguf"
ls -lh "$OUT_DIR"
