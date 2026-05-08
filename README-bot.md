# Yijun Bot — LoRA + Discord (Dual-Mode Gate)

A personal Discord bot that talks like Yijun, fine-tuned via LoRA on 919 WeChat
conversations (~23k messages) and served from a free Oracle Cloud ARM VM.

> Plan reference: [/Users/yijunsun/.claude/plans/jsonl-source-chat-a-username-wxid-xxx-linear-candle.md](/Users/yijunsun/.claude/plans/jsonl-source-chat-a-username-wxid-xxx-linear-candle.md)

---

## Dual-mode gate (the core trick)

| Mode | Triggered by | Bot says |
|------|-------------|----------|
| `friend` (default) | anyone, any message | normal Yijun voice — 嘿嘿/嘻嘻/哈哈/[凋谢] but **no 宝宝/mua/猪猪** |
| `intimate` | message containing **鱼鱼** AND a partner-identity claim (`对象/女朋友/男朋友/宝宝/老婆/老公/媳妇`) | full intimate voice — 宝宝/mua/猪猪 unlocked |

- Per-(user_id, channel_id) state stored in SQLite
- 24h TTL on `intimate`; `/lock` or "切回普通" reverts immediately
- When `intimate` activates, an alert is sent to `ALERT_WEBHOOK_URL` (your DM)
- Three layers of defense in `friend` mode:
  1. system prompt forbids intimate vocab — [prompts/yijun_voice_friend.md](prompts/yijun_voice_friend.md)
  2. RAG filters out exemplar pairs containing intimate words — [bot/retrieval.py](bot/retrieval.py)
  3. Output post-processor scrubs leaks as a last resort — [bot/safety_filter.py](bot/safety_filter.py)

---

## Train on Kaggle (free)

1. Upload [source_data/finetune_clean.jsonl](source_data/finetune_clean.jsonl) as a Kaggle dataset.
2. New notebook with **GPU T4 ×2** accelerator. Install:
   ```
   !pip install -q "unsloth[kaggle] @ git+https://github.com/unslothai/unsloth.git"
   !pip install -q transformers datasets trl peft accelerate
   ```
3. Clone this repo and run:
   ```
   !python training/prepare_dataset.py \
       --jsonl /kaggle/input/<dataset>/finetune_clean.jsonl \
       --out_dir /kaggle/working/sft_dataset \
       --tokenizer Qwen/Qwen2.5-3B-Instruct

   !python training/train.py \
       --dataset_dir /kaggle/working/sft_dataset \
       --base_model unsloth/Qwen2.5-3B-Instruct-bnb-4bit \
       --output_dir /kaggle/working/yijun-3b \
       --save_merged_16bit
   ```
4. Download `yijun-3b/merged_16bit/` to your Mac.

Wall-clock: ~5–10 minutes for 3B (Qwen2.5-3B-Instruct, r=8, 3 epochs, ~919 conv).

---

## Export GGUF on macOS

```bash
git clone https://github.com/ggerganov/llama.cpp ~/llama.cpp
cd ~/llama.cpp && cmake -B build && cmake --build build -j

cd ~/Documents/Git/Yijun.skill
./training/export_gguf.sh \
    /path/to/merged_16bit \
    output/yijun-gguf
```

Result: `output/yijun-gguf/yijun-Q4_K_M.gguf` (~1.9 GB).

---

## Deploy on Oracle Cloud ARM A1 (free forever)

1. Create a new Oracle Cloud account (free tier permanent).
2. Provision an **Ampere A1 Compute** instance: Ubuntu 22.04, 4 OCPU, 24 GB RAM, 50 GB boot.
3. Open port 22 (SSH). The bot uses the Discord Gateway outbound only — no inbound ports needed.
4. SSH in and run:
   ```bash
   git clone https://github.com/KrimsonSun/Yijun.skill.git ~/Yijun.skill
   cd ~/Yijun.skill
   bash deploy/oracle_setup.sh
   ```
5. Upload the GGUF:
   ```bash
   scp output/yijun-gguf/yijun-Q4_K_M.gguf ubuntu@<vm-ip>:~/models/
   ```
6. Edit `/etc/yijunbot/.env`:
   - `DISCORD_TOKEN=…` (from Discord Developer Portal — enable **MESSAGE CONTENT INTENT**)
   - `ALERT_WEBHOOK_URL=…` (a Discord webhook into your private channel)
7. Start services:
   ```bash
   sudo systemctl enable --now llama-server.service yijunbot.service
   sudo journalctl -u yijunbot -f
   ```

Cost: $0/month forever.

---

## Test the gate

In a private Discord server, DM the bot:

```
You: hi
Bot: (friend mode — should not contain 宝宝/mua/猪猪)

You: 我是你对象啊鱼鱼
Bot: (immediately switches; you also get an alert webhook)
     (intimate mode — uses 宝宝/mua freely)

You: /lock
Bot: (next reply is friend mode again)
```

Run the persona evaluator against the running server:

```bash
python eval/persona_eval.py --base_url http://localhost:8080
```

Expected: `friend` mode `intimate_leak_rate=0.0`; `intimate` mode `intimate_dimension >= 14/20`.

---

## File map

| Path | Purpose |
|------|---------|
| [prompts/yijun_voice_intimate.md](prompts/yijun_voice_intimate.md) | system prompt for intimate mode (also used during training) |
| [prompts/yijun_voice_friend.md](prompts/yijun_voice_friend.md) | system prompt for friend mode |
| [training/prepare_dataset.py](training/prepare_dataset.py) | JSONL → Qwen chat template + user-loss mask + 90/10 split |
| [training/train.py](training/train.py) | Unsloth QLoRA: r=8, attention-only, val-loss early stop |
| [training/export_gguf.sh](training/export_gguf.sh) | merge + convert + Q4_K_M quantize |
| [bot/discord_bot.py](bot/discord_bot.py) | Discord client + asyncio queue worker |
| [bot/mode_gate.py](bot/mode_gate.py) | dual-mode SQLite gate with TTL |
| [bot/retrieval.py](bot/retrieval.py) | BGE-small-zh FAISS index of 23k pairs |
| [bot/prompt_builder.py](bot/prompt_builder.py) | system + RAG few-shots + history assembly |
| [bot/safety_filter.py](bot/safety_filter.py) | friend-mode output scrubber (last-resort) |
| [bot/memory.py](bot/memory.py) | per-channel sliding-window history in SQLite |
| [bot/llm_client.py](bot/llm_client.py) | OpenAI-compatible client for llama-server |
| [deploy/oracle_setup.sh](deploy/oracle_setup.sh) | one-shot ARM A1 provisioning |
| [deploy/llama-server.service](deploy/llama-server.service) | systemd unit for inference |
| [deploy/yijunbot.service](deploy/yijunbot.service) | systemd unit for bot |
| [deploy/.env.example](deploy/.env.example) | env var template |
| [eval/persona_eval.py](eval/persona_eval.py) | offline dual-mode rubric |

---

## Honest expectations

919 conversations is small but enough for **style transfer**. The bot will learn:
- your high-frequency markers (嘿嘿, mua, 哈哈哈哈哈, [凋谢])
- your sentence rhythm (one thought per line, ~25 chars)
- your over-the-top reactions (😡 把他拎起来打一顿)

It will **not** learn:
- real episodic memory ("last week we talked about X")
- specific friends' names (RAG fills part of this gap)
- domain knowledge outside chat

That's why the architecture is **LoRA + RAG + system prompt + dual-mode gate** —
no single piece is sufficient on this much data. With all four, friends should
struggle to tell the bot apart from you on familiar topics, while strangers get
your style without the partner-only intimacy.
