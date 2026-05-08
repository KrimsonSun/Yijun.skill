#!/usr/bin/env bash
# End-to-end Colab training: clone repo, prep data, train. Outputs stay
# on Colab session disk under /content; nothing is written to Drive.
#
# Usage (in a Colab cell, after mounting Drive for the *input* JSONL):
#     !bash /content/Yijun.skill/colab/run.sh 3b
#     !bash /content/Yijun.skill/colab/run.sh 7b
#
# Inputs:
#   - finetune_clean.jsonl at /content/drive/MyDrive/yijun_bot/finetune_clean.jsonl
#     (Drive is only used to read the dataset; nothing is written back.)
#
# Outputs (Colab session disk only):
#   /content/yijun-{size}/merged_16bit/   HF weights, ready for GGUF
#   /content/yijun-{size}/lora_adapter/   LoRA adapter only (~30 MB)
#
# Next step: build GGUF in Colab via colab/build_gguf.sh, then download
# the small Q4_K_M file directly.

set -euo pipefail

MODEL_SIZE="${1:-3b}"
DRIVE_DIR="${DRIVE_DIR:-/content/drive/MyDrive/yijun_bot}"
REPO_DIR="${REPO_DIR:-/content/Yijun.skill}"

case "$MODEL_SIZE" in
    3b)
        BASE="unsloth/Qwen2.5-3B-Instruct-bnb-4bit"
        TOKENIZER="Qwen/Qwen2.5-3B-Instruct"
        OUTNAME="yijun-3b"
        ;;
    7b)
        BASE="unsloth/Qwen2.5-7B-Instruct-bnb-4bit"
        TOKENIZER="Qwen/Qwen2.5-7B-Instruct"
        OUTNAME="yijun-7b"
        ;;
    *)
        echo "ERROR: model size must be '3b' or '7b' (got '$MODEL_SIZE')" >&2
        exit 1
        ;;
esac

OUT_DIR="/content/$OUTNAME"

echo "=== Yijun training ==="
echo "Model:     $BASE"
echo "Repo:      $REPO_DIR"
echo "Out (Colab session): $OUT_DIR/{merged_16bit,lora_adapter}"
echo

# --- 1. Source data (read from Drive only) ---
mkdir -p "$REPO_DIR/source_data"
if [ ! -f "$REPO_DIR/source_data/finetune_clean.jsonl" ]; then
    if [ ! -f "$DRIVE_DIR/finetune_clean.jsonl" ]; then
        echo "ERROR: $DRIVE_DIR/finetune_clean.jsonl not found." >&2
        echo "Upload your JSONL to Google Drive at that path first." >&2
        exit 1
    fi
    cp "$DRIVE_DIR/finetune_clean.jsonl" "$REPO_DIR/source_data/finetune_clean.jsonl"
fi

# --- 2. Prep dataset (text-field render + 90/10 split) ---
echo "[1/2] Preparing dataset"
python "$REPO_DIR/training/prepare_dataset.py" \
    --jsonl "$REPO_DIR/source_data/finetune_clean.jsonl" \
    --out_dir /content/sft_dataset \
    --tokenizer "$TOKENIZER" \
    --max_seq_length 2048

# --- 3. Train ---
echo "[2/2] Training $MODEL_SIZE"
python "$REPO_DIR/training/train.py" \
    --dataset_dir /content/sft_dataset \
    --base_model "$BASE" \
    --output_dir "$OUT_DIR" \
    --per_device_batch_size 4 \
    --grad_accum_steps 4 \
    --lora_r 16 \
    --lora_alpha 32 \
    --learning_rate 2e-4 \
    --epochs 3 \
    --save_merged_16bit

echo
echo "=== Done ==="
du -sh "$OUT_DIR/merged_16bit" "$OUT_DIR/lora_adapter"
echo
echo "Next:"
echo "  bash $REPO_DIR/colab/build_gguf.sh $MODEL_SIZE   # build Q4_K_M GGUF"
echo "  Then download /content/$OUTNAME-Q4_K_M.gguf from the Colab file browser"
echo "  or with: from google.colab import files; files.download('/content/$OUTNAME-Q4_K_M.gguf')"
