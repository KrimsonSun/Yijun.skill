#!/usr/bin/env bash
# Convert the merged HF weights to GGUF Q4_K_M directly inside Colab,
# so you can download a single ~1.9 GB file (3B) instead of the 5.8 GB
# multi-shard HF folder.
#
# Usage:
#     !bash /content/Yijun.skill/colab/build_gguf.sh 3b
#     !bash /content/Yijun.skill/colab/build_gguf.sh 7b
#
# Output:
#   /content/yijun-{size}-Q4_K_M.gguf   (3B ~1.9 GB, 7B ~4.5 GB)

set -euo pipefail

MODEL_SIZE="${1:-3b}"
LLAMA_DIR="${LLAMA_DIR:-/content/llama.cpp}"
OUTNAME="yijun-$MODEL_SIZE"
MERGED_DIR="/content/$OUTNAME/merged_16bit"
GGUF_DIR="/content"

if [ ! -d "$MERGED_DIR" ]; then
    echo "ERROR: $MERGED_DIR not found. Run colab/run.sh first." >&2
    exit 1
fi

echo "[1/4] Cloning + building llama.cpp"
if [ ! -d "$LLAMA_DIR" ]; then
    git clone --depth 1 https://github.com/ggerganov/llama.cpp "$LLAMA_DIR"
fi
cd "$LLAMA_DIR"
if [ ! -f build/bin/llama-quantize ]; then
    cmake -B build -DGGML_NATIVE=ON -DLLAMA_CURL=OFF >/dev/null
    cmake --build build --config Release -j"$(nproc)" --target llama-quantize llama-cli >/dev/null
fi

echo "[2/4] Installing llama.cpp Python deps for HF -> GGUF conversion"
pip install -q -r "$LLAMA_DIR/requirements/requirements-convert_hf_to_gguf.txt"

echo "[3/4] HF -> fp16 GGUF"
F16_PATH="$GGUF_DIR/$OUTNAME-f16.gguf"
python "$LLAMA_DIR/convert_hf_to_gguf.py" \
    "$MERGED_DIR" \
    --outfile "$F16_PATH" \
    --outtype f16

echo "[4/4] fp16 -> Q4_K_M"
Q4_PATH="$GGUF_DIR/$OUTNAME-Q4_K_M.gguf"
"$LLAMA_DIR/build/bin/llama-quantize" \
    "$F16_PATH" \
    "$Q4_PATH" \
    Q4_K_M

# Drop the big fp16; keep only the quantized version
rm -f "$F16_PATH"

echo
echo "=== Done ==="
ls -lh "$Q4_PATH"
echo
echo "Download via Colab cell:"
echo "  from google.colab import files"
echo "  files.download('$Q4_PATH')"
