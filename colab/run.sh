#!/usr/bin/env bash
# End-to-end Colab training: clone repo, prep data, train, save to Drive.
#
# Usage (in a Colab cell, after mounting Drive):
#     !bash /content/Yijun.skill/colab/run.sh 3b
#     !bash /content/Yijun.skill/colab/run.sh 7b
#
# Expects:
#   - Google Drive mounted at /content/drive
#   - finetune_clean.jsonl at /content/drive/MyDrive/yijun_bot/finetune_clean.jsonl
#
# Outputs (saved back to Drive):
#   /content/drive/MyDrive/yijun_bot/output/yijun-{size}-merged/   (HF, ready for GGUF conversion)
#   /content/drive/MyDrive/yijun_bot/output/yijun-{size}-lora/     (LoRA adapter only, ~30 MB)

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

echo "=== Yijun training ==="
echo "Model:     $BASE"
echo "Repo:      $REPO_DIR"
echo "Drive:     $DRIVE_DIR"
echo "Out:       $DRIVE_DIR/output/$OUTNAME-{merged,lora}"
echo

# --- 1. Source data ---
mkdir -p "$REPO_DIR/source_data"
if [ ! -f "$REPO_DIR/source_data/finetune_clean.jsonl" ]; then
    if [ ! -f "$DRIVE_DIR/finetune_clean.jsonl" ]; then
        echo "ERROR: $DRIVE_DIR/finetune_clean.jsonl not found." >&2
        echo "Upload your JSONL to Google Drive at that path first." >&2
        exit 1
    fi
    cp "$DRIVE_DIR/finetune_clean.jsonl" "$REPO_DIR/source_data/finetune_clean.jsonl"
fi

# --- 2. Prep dataset (tokenize + mask + 90/10 split) ---
echo "[1/3] Preparing dataset"
python "$REPO_DIR/training/prepare_dataset.py" \
    --jsonl "$REPO_DIR/source_data/finetune_clean.jsonl" \
    --out_dir /content/sft_dataset \
    --tokenizer "$TOKENIZER" \
    --max_seq_length 2048

# --- 3. Train ---
echo "[2/3] Training $MODEL_SIZE"
OUT_DIR="/content/$OUTNAME"
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

# --- 4. Push artifacts to Drive ---
echo "[3/3] Saving to Drive"
mkdir -p "$DRIVE_DIR/output"
rm -rf "$DRIVE_DIR/output/$OUTNAME-merged" "$DRIVE_DIR/output/$OUTNAME-lora"
cp -r "$OUT_DIR/merged_16bit" "$DRIVE_DIR/output/$OUTNAME-merged"
cp -r "$OUT_DIR/lora_adapter" "$DRIVE_DIR/output/$OUTNAME-lora"

echo
echo "=== Done ==="
du -sh "$DRIVE_DIR/output/$OUTNAME-merged" "$DRIVE_DIR/output/$OUTNAME-lora"
echo
echo "Next: download $DRIVE_DIR/output/$OUTNAME-merged to your Mac,"
echo "      then run training/export_gguf.sh on it."
