"""Convert finetune_clean.jsonl into a HuggingFace dataset ready for Qwen2.5 SFT.

Pipeline:
1. Load JSONL — each line is {chat, username, is_group, messages: [{role, content}, ...]}
2. Inject the intimate-mode system prompt at the start of each conversation
   (we train on the full intimate corpus; friend mode is enforced at inference)
3. Apply the Qwen2.5 chat template
4. Mask user-turn loss (we only want to learn assistant tokens — the user is not Yijun)
5. Conversation-level 90/10 train/val split (no message-level leakage)
6. Truncate to max_seq_length on speaker boundaries

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
from pathlib import Path

from datasets import Dataset, DatasetDict
from transformers import AutoTokenizer

SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "yijun_voice_intimate.md"
IGNORE_INDEX = -100


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
            convs.append(msgs)
    return convs


def build_chat(messages: list[dict], system_prompt: str) -> list[dict]:
    """Prepend system prompt; ensure roles alternate user/assistant.

    Drop a leading assistant turn (no preceding user turn would mean nothing
    to train on for the first reply — the model would learn to talk into the void).
    """
    if messages and messages[0]["role"] == "assistant":
        messages = messages[1:]
    if not messages:
        return []
    return [{"role": "system", "content": system_prompt}] + messages


def tokenize_with_assistant_mask(
    chat: list[dict],
    tokenizer,
    max_seq_length: int,
) -> dict | None:
    """Tokenize the full chat, mask non-assistant tokens in labels.

    Strategy: render the full chat once with the chat template (gets us
    correct special tokens), then for each assistant message, render the
    prefix-up-to-and-including-that-message and the prefix-up-to-but-not-
    including, diff to find the assistant token span, and unmask just that
    span in the labels.
    """
    full_text = tokenizer.apply_chat_template(chat, tokenize=False, add_generation_prompt=False)
    full_ids = tokenizer(full_text, add_special_tokens=False)["input_ids"]
    if len(full_ids) > max_seq_length:
        return None  # caller will split

    labels = [IGNORE_INDEX] * len(full_ids)

    # Walk through chat building cumulative prefixes
    for i, msg in enumerate(chat):
        if msg["role"] != "assistant":
            continue
        prefix_before = tokenizer.apply_chat_template(
            chat[:i], tokenize=False, add_generation_prompt=True
        )
        prefix_after = tokenizer.apply_chat_template(
            chat[: i + 1], tokenize=False, add_generation_prompt=False
        )
        ids_before = tokenizer(prefix_before, add_special_tokens=False)["input_ids"]
        ids_after = tokenizer(prefix_after, add_special_tokens=False)["input_ids"]
        start = len(ids_before)
        end = len(ids_after)
        for j in range(start, min(end, len(labels))):
            labels[j] = full_ids[j]

    return {"input_ids": full_ids, "labels": labels, "attention_mask": [1] * len(full_ids)}


def split_long_conversation(messages: list[dict], tokenizer, max_seq_length: int, system_prompt: str) -> list[list[dict]]:
    """If a single conversation tokenizes longer than max_seq_length, split on
    speaker boundaries (keeping user→assistant pairs together)."""
    chunks: list[list[dict]] = []
    current: list[dict] = []
    for msg in messages:
        candidate = current + [msg]
        chat = build_chat(candidate, system_prompt)
        if not chat:
            # candidate is e.g. a lone leading assistant turn that build_chat strips —
            # keep accumulating until we have a real (system + user + ...) chat.
            current = candidate
            continue
        text = tokenizer.apply_chat_template(chat, tokenize=False, add_generation_prompt=False)
        n = len(tokenizer(text, add_special_tokens=False)["input_ids"])
        if n > max_seq_length and current:
            # close current chunk (must end on assistant for any training signal)
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

    # Conversation-level shuffle + split BEFORE chunking long ones,
    # so all chunks of one conversation stay in the same split.
    rng = random.Random(args.seed)
    rng.shuffle(raw_convs)
    n_val = int(len(raw_convs) * args.val_ratio)
    val_convs = raw_convs[:n_val]
    train_convs = raw_convs[n_val:]
    print(f"Split: {len(train_convs)} train / {len(val_convs)} val")

    def process(convs: list[list[dict]]) -> list[dict]:
        out: list[dict] = []
        skipped_short = 0
        for messages in convs:
            chunks = split_long_conversation(messages, tokenizer, args.max_seq_length, system_prompt)
            for chunk in chunks:
                chat = build_chat(chunk, system_prompt)
                if not any(m["role"] == "assistant" for m in chat):
                    skipped_short += 1
                    continue
                tokenized = tokenize_with_assistant_mask(chat, tokenizer, args.max_seq_length)
                if tokenized is None:
                    skipped_short += 1
                    continue
                out.append(tokenized)
        if skipped_short:
            print(f"  skipped {skipped_short} chunks (no assistant turn or oversize)")
        return out

    train_records = process(train_convs)
    val_records = process(val_convs)
    print(f"Tokenized: {len(train_records)} train / {len(val_records)} val records")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ds = DatasetDict({
        "train": Dataset.from_list(train_records),
        "validation": Dataset.from_list(val_records),
    })
    ds.save_to_disk(str(args.out_dir))
    print(f"Saved dataset to {args.out_dir}")

    # Quick sanity report
    train_assistant_tokens = sum(
        sum(1 for x in r["labels"] if x != IGNORE_INDEX) for r in train_records
    )
    print(f"Train assistant-token count (loss-bearing): {train_assistant_tokens}")


if __name__ == "__main__":
    main()
