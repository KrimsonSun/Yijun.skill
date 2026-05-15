#!/usr/bin/env bash
# Bot container entrypoint:
# 1. Build the RAG index over finetune_clean.jsonl if not already cached
# 2. Wait briefly for llama-server containers to be reachable
# 3. Launch the Discord bot

set -euo pipefail

JSONL_PATH="${JSONL_PATH:-/source_data/finetune_clean.jsonl}"
INDEX_DIR="${INDEX_DIR:-/data/index}"

# --- 1. RAG index ---
if [ ! -f "$INDEX_DIR/pairs.faiss" ]; then
    if [ ! -f "$JSONL_PATH" ]; then
        echo "ERROR: $JSONL_PATH not found. Mount your finetune_clean.jsonl read-only at /source_data/" >&2
        exit 1
    fi
    echo "[bot-entrypoint] Building RAG index from $JSONL_PATH ..."
    mkdir -p "$INDEX_DIR"
    python -m bot.retrieval --jsonl "$JSONL_PATH" --index_dir "$INDEX_DIR"
else
    echo "[bot-entrypoint] RAG index already present at $INDEX_DIR — skipping build."
fi

# --- 2. Wait for llama-server(s) ---
wait_for() {
    local url="$1"; local name="$2"
    echo "[bot-entrypoint] Waiting for $name at $url ..."
    for _ in $(seq 1 60); do
        if curl -fsS "$url/health" >/dev/null 2>&1 || curl -fsS "$url/v1/models" >/dev/null 2>&1; then
            echo "[bot-entrypoint] $name ready."
            return 0
        fi
        sleep 2
    done
    echo "[bot-entrypoint] WARN: $name never became reachable; starting bot anyway." >&2
}

wait_for "${LLAMA_BASE_URL:-http://yijun-llama:8080}" "yijun-llama"
if [ "${USE_REASONER:-0}" = "1" ]; then
    wait_for "${REASONER_BASE_URL:-http://reasoner:8081}" "reasoner"
fi

# --- 3. Launch ---
exec python -m bot.discord_bot
