#!/usr/bin/env bash
# Provision an Oracle Cloud Always Free ARM A1 (Ubuntu 22.04) for the Yijun bot.
#
# Usage:
#   1. ssh ubuntu@<vm-ip>
#   2. git clone https://github.com/KrimsonSun/Yijun.skill.git ~/Yijun.skill
#   3. cd ~/Yijun.skill && bash deploy/oracle_setup.sh
#   4. scp the GGUF to ~/models/yijun-Q4_K_M.gguf
#   5. cp deploy/.env.example /etc/yijunbot/.env  and fill in DISCORD_TOKEN
#   6. sudo systemctl enable --now llama-server.service yijunbot.service

set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/Yijun.skill}"
MODELS_DIR="${MODELS_DIR:-$HOME/models}"
LLAMA_DIR="${LLAMA_DIR:-$HOME/llama.cpp}"
PYENV_DIR="${PYENV_DIR:-$HOME/yijunbot-venv}"

echo "[1/6] System packages"
sudo apt-get update
sudo apt-get install -y \
    build-essential cmake git curl \
    python3 python3-venv python3-pip \
    libcurl4-openssl-dev pkg-config

echo "[2/6] Build llama.cpp (ARM NEON)"
if [ ! -d "$LLAMA_DIR" ]; then
    git clone https://github.com/ggerganov/llama.cpp "$LLAMA_DIR"
fi
cd "$LLAMA_DIR"
git pull --ff-only
cmake -B build -DGGML_NATIVE=ON -DLLAMA_CURL=ON
cmake --build build --config Release -j"$(nproc)"
cd "$REPO_DIR"

echo "[3/6] Python venv + bot deps"
python3 -m venv "$PYENV_DIR"
"$PYENV_DIR/bin/pip" install --upgrade pip
"$PYENV_DIR/bin/pip" install -r "$REPO_DIR/requirements.txt"

echo "[4/6] Build retrieval index"
mkdir -p "$REPO_DIR/bot/.index"
"$PYENV_DIR/bin/python" -m bot.retrieval \
    --jsonl "$REPO_DIR/source_data/finetune_clean.jsonl" \
    --index_dir "$REPO_DIR/bot/.index"

echo "[5/6] Directories + systemd units"
sudo mkdir -p /var/lib/yijunbot /etc/yijunbot
sudo chown "$USER:$USER" /var/lib/yijunbot
sudo install -m 644 "$REPO_DIR/deploy/llama-server.service" /etc/systemd/system/llama-server.service
sudo install -m 644 "$REPO_DIR/deploy/yijunbot.service" /etc/systemd/system/yijunbot.service
sudo systemctl daemon-reload

if [ ! -f /etc/yijunbot/.env ]; then
    sudo install -m 600 "$REPO_DIR/deploy/.env.example" /etc/yijunbot/.env
    sudo chown "$USER:$USER" /etc/yijunbot/.env
    echo ">>> EDIT /etc/yijunbot/.env to set DISCORD_TOKEN and ALERT_WEBHOOK_URL"
fi

echo "[6/6] Hint"
echo
echo "Next:"
echo "  scp your GGUF to $MODELS_DIR/yijun-Q4_K_M.gguf"
echo "  edit /etc/yijunbot/.env (DISCORD_TOKEN required)"
echo "  sudo systemctl enable --now llama-server.service yijunbot.service"
echo "  sudo journalctl -u yijunbot -f"
