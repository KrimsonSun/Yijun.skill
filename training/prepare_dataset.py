"""Convert finetune_clean.jsonl into a HuggingFace dataset for Qwen2.5 SFT.

This is the canonical-unsloth flow: we just emit a {"text": rendered_chat}
field. The trainer tokenizes during training, and we use unsloth's
`train_on_responses_only` to mask user turns automatically by matching the
chat-template's instruction/response markers. That replaces our previous
hand-rolled token-span masking, which was responsible for role-confused
outputs (model mimicking the user side instead of replying as Yijun).

Pipeline:
1. Load JSONL — each line is {chat, username, is_group, messages: [...]}
2. Strip de-identification placeholders (?A, ?B, ?JY, ...)
3. Conversation-level 90/10 train/val split (no message-level leakage)
4. Split long conversations on assistant boundaries so each chunk fits in
   max_seq_length
5. Render each chunk with the Qwen2.5 chat template + intimate system prompt
6. Save as a HuggingFace Dataset with a single "text" column

Run:
    python training/prepare_dataset.py \
        --jsonl source_data/finetune_clean.jsonl \
        --out_dir source_data/sft_dataset \
        --tokenizer Qwen/Qwen2.5-3B-Instruct \
        --max_seq_length 2048
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

from datasets import Dataset, DatasetDict
from transformers import AutoTokenizer

SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "yijun_voice_intimate.md"

# Placeholder tokens used in finetune_clean.jsonl for de-identification (?A,
# ?B, ?JY, etc.). Strip these so the model doesn't memorize them as part of
# Yijun's voice.
PLACEHOLDER_RE = re.compile(r"\?[A-Z]+")


def clean_placeholders(text: str) -> str:
    return PLACEHOLDER_RE.sub("", text).strip()


def load_conversations(jsonl_path: Path) -> list[list[dict]]:
    convs: list[list[dict]] = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            msgs = obj.get("messages", [])
            if not msgs:
                continue
            cleaned: list[dict] = []
            for m in msgs:
                content = clean_placeholders(m.get("content", ""))
                if not content:
                    continue
                cleaned.append({"role": m["role"], "content": content})
            if cleaned:
                convs.append(cleaned)
    return convs


def build_chat(messages: list[dict], system_prompt: str) -> list[dict]:
    """Prepend system prompt; drop a leading assistant turn so each chat
    starts with system → user (no orphan first reply)."""
    if messages and messages[0]["role"] == "assistant":
        messages = messages[1:]
    if not messages:
        return []
    return [{"role": "system", "content": system_prompt}] + messages


def render(chat: list[dict], tokenizer) -> str:
    return tokenizer.apply_chat_template(chat, tokenize=False, add_generation_prompt=False)


def token_count(text: str, tokenizer) -> int:
    return len(tokenizer(text, add_special_tokens=False)["input_ids"])


def split_long_conversation(
    messages: list[dict], tokenizer, max_seq_length: int, system_prompt: str
) -> list[list[dict]]:
    """Yield message-list chunks each ending on an assistant turn whose rendered
    chat fits within max_seq_length tokens."""
    chunks: list[list[dict]] = []
    current: list[dict] = []
    for msg in messages:
        candidate = current + [msg]
        chat = build_chat(candidate, system_prompt)
        if not chat:
            current = candidate
            continue
        n = token_count(render(chat, tokenizer), tokenizer)
        if n > max_seq_length and current:
            while current and current[-1]["role"] != "assistant":
                current.pop()
            if current:
                chunks.append(current)
            current = [msg]
        else:
            current = candidate
    if current:
        while current and current[-1]["role"] != "assistant":
            current.pop()
        if current:
            chunks.append(current)
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--out_dir", type=Path, required=True)
    parser.add_argument("--tokenizer", type=str, default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--max_seq_length", type=int, default=2048)
    parser.add_argument("--val_ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)

    raw_convs = load_conversations(args.jsonl)
    print(f"Loaded {len(raw_convs)} raw conversations")

    rng = random.Random(args.seed)
    rng.shuffle(raw_convs)
    n_val = int(len(raw_convs) * args.val_ratio)
    val_convs = raw_convs[:n_val]
    train_convs = raw_convs[n_val:]
    print(f"Split: {len(train_convs)} train / {len(val_convs)} val")

    def process(convs: list[list[dict]]) -> list[dict]:
        out: list[dict] = []
        skipped = 0
        for messages in convs:
            for chunk in split_long_conversation(
                messages, tokenizer, args.max_seq_length, system_prompt
            ):
                chat = build_chat(chunk, system_prompt)
                if not any(m["role"] == "assistant" for m in chat):
                    skipped += 1
                    continue
                text = render(chat, tokenizer)
                if token_count(text, tokenizer) > args.max_seq_length:
                    skipped += 1
                    continue
                out.append({"text": text})
        if skipped:
            print(f"  skipped {skipped} chunks (no assistant turn or oversize)")
        return out

    train_records = process(train_convs)
    val_records = process(val_convs)
    print(f"Rendered: {len(train_records)} train / {len(val_records)} val records")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ds = DatasetDict({
        "train": Dataset.from_list(train_records),
        "validation": Dataset.from_list(val_records),
    })
    ds.save_to_disk(str(args.out_dir))
    print(f"Saved dataset to {args.out_dir}")

    # Sanity peek
    sample = train_records[0]["text"]
    print("\n=== sample[0] (first 600 chars) ===")
    print(sample[:600])
    print("=== /sample[0] ===\n")


if __name__ == "__main__":
    main()
