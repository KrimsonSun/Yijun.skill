#!/usr/bin/env bash
# One-shot helper: download a small base model GGUF to act as the reasoner.
# We use bartowski's GGUFs because they're well-maintained and have all the
# common quants. Default is Qwen2.5-3B-Instruct Q4_K_M (~1.9 GB).

set -euo pipefail

MODELS_DIR="${MODELS_DIR:-$(dirname "$0")/models}"
mkdir -p "$MODELS_DIR"

# Default: 3B base instruct. Override REASONER_REPO/REASONER_FILE if you want
# a different (smaller / larger) reasoner.
REASONER_REPO="${REASONER_REPO:-bartowski/Qwen2.5-3B-Instruct-GGUF}"
REASONER_FILE="${REASONER_FILE:-Qwen2.5-3B-Instruct-Q4_K_M.gguf}"
TARGET="$MODELS_DIR/qwen2.5-3b-instruct-q4_k_m.gguf"

if [ -f "$TARGET" ]; then
    echo "Reasoner already at $TARGET — skipping download."
    exit 0
fi

echo "Downloading $REASONER_FILE from $REASONER_REPO ..."
URL="https://huggingface.co/${REASONER_REPO}/resolve/main/${REASONER_FILE}?download=true"

if command -v curl >/dev/null 2>&1; then
    curl -L --fail "$URL" -o "$TARGET.part"
elif command -v wget >/dev/null 2>&1; then
    wget -O "$TARGET.part" "$URL"
else
    echo "ERROR: need curl or wget installed." >&2
    exit 1
fi

mv "$TARGET.part" "$TARGET"
echo "Done: $TARGET"
ls -lh "$TARGET"
