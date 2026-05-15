# Yijun Bot — local Docker stack

Three containers, all local, no external APIs:

```
yijun-llama (Yijun-7B Q4 stylist, :8080)
reasoner    (Qwen2.5-3B-Instruct base, plan-then-style logic guard, :8081)
bot         (discord.py + RAG over your corpus)
```

## Prerequisites

- Docker Desktop running (Mac, Linux, or Windows WSL2)
- Your trained `yijun-7b-Q4_K_M.gguf` ready (built in Colab via `colab/build_gguf.sh`)
- A Discord bot token from https://discord.com/developers/applications
  - Enable **MESSAGE CONTENT INTENT** in your application's Bot tab
  - Invite the bot to your test server with `bot` + `Send Messages` scopes

## One-time setup

From the repo root:

```bash
cd docker

# 1. Place the Yijun model
mkdir -p models
cp /path/to/yijun-7b-Q4_K_M.gguf models/

# 2. Download the reasoner model (~2 GB)
bash download_reasoner.sh

# 3. Configure Discord token
cp .env.example .env
$EDITOR .env   # set DISCORD_TOKEN
```

## Run

```bash
docker compose up -d
docker compose logs -f bot
```

First start of the bot container builds the RAG index from your
[../source_data/finetune_clean.jsonl](../source_data/finetune_clean.jsonl)
(takes ~30 s for 23k pairs). Subsequent restarts reuse the cached index.

## Verify

```bash
# Reasoner sanity
curl -s http://localhost:8081/v1/chat/completions -H "content-type: application/json" -d '{
  "messages":[{"role":"user","content":"say hi in one word"}],
  "max_tokens": 16
}' | jq -r '.choices[0].message.content'

# Yijun model sanity
curl -s http://localhost:8080/v1/chat/completions -H "content-type: application/json" -d '{
  "messages":[
    {"role":"system","content":"你是 Yijun"},
    {"role":"user","content":"早安"}
  ],
  "max_tokens": 80
}' | jq -r '.choices[0].message.content'
```

In Discord, DM the bot or @ it in a channel — it should reply.

## What's where

| Container | Image / Build | RAM | Port |
|-----------|--------------|-----|------|
| `yijun-llama` | `ghcr.io/ggerganov/llama.cpp:server` | ~5 GB | 8080 |
| `reasoner` | `ghcr.io/ggerganov/llama.cpp:server` | ~2 GB | 8081 |
| `bot` | built from [Dockerfile.bot](Dockerfile.bot) | ~0.7 GB | — |

Total RAM: **~7.7 GB**. Fits on 8 GB hosts with thin margin; 16 GB safer.

## Common ops

```bash
# Restart just the bot (e.g. after a code change in bot/)
docker compose up -d --build bot

# Rebuild the RAG index (if you updated finetune_clean.jsonl)
docker compose exec bot rm -rf /data/index
docker compose restart bot

# Inspect the SQLite memory db
docker compose exec bot sqlite3 /data/memory.db "SELECT * FROM user_mode;"

# Tear down (keeps volume / index intact)
docker compose down

# Tear down + wipe bot data
docker compose down -v
```

## Disable reasoner (faster, lower RAM)

Edit `docker-compose.yml`:
- Remove the `reasoner` service block
- Under `bot.environment`, set `USE_REASONER: "0"`

Saves ~2 GB and ~500 ms per reply. The bot still works, just back to the
"warm style but inconsistent context" state from before.

## Deploy to a remote VM

Same setup works on any x86 Linux box (Hetzner CX32 / CX42, DO droplet, etc.):

```bash
# On the VM (Ubuntu 22.04, Docker installed)
git clone https://github.com/KrimsonSun/Yijun.skill.git
cd Yijun.skill/docker
mkdir -p models

# scp the Yijun GGUF from your Mac
# (on Mac): scp yijun-7b-Q4_K_M.gguf user@vm:~/Yijun.skill/docker/models/

bash download_reasoner.sh
cp .env.example .env && nano .env
docker compose up -d
```

The bot makes only outbound connections (to Discord), so no inbound ports
need to be opened.

## Mac-specific note

On Apple Silicon, the `ghcr.io/ggerganov/llama.cpp:server` image runs
natively on ARM64 but **inside Docker has no Metal acceleration** — it
falls back to CPU. M4 Pro should still pull ~10-15 tok/s for 7B Q4, which
is workable for testing but slower than native `llama-cli` (60+ tok/s).

For dev iteration: native `llama-cli` is faster.
For production-shape testing: this Docker stack is what runs on the VM.
