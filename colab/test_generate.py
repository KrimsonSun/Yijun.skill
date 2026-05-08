"""Smoke-test a freshly-trained Yijun model on Colab.

Loads the merged 16-bit model via unsloth's FastLanguageModel and generates
replies to 5 hold-out prompts. We use unsloth here (not transformers'
AutoModelForCausalLM) to bypass the torchvision import chain that breaks
when Colab's torch and torchvision versions don't match.

Usage (in a Colab cell):
    !python /content/Yijun.skill/colab/test_generate.py \
        --model_dir /content/yijun-3b/merged_16bit
"""
from __future__ import annotations

import argparse
from pathlib import Path

# Keep unsloth first (its monkey-patches must run before transformers import).
from unsloth import FastLanguageModel  # noqa: I001  (intentional ordering)

import torch

PROBES = [
    "今晚吃啥",
    "我今天好累",
    "我刚下班 嘿嘿",
    "气死我了 老板又加任务",
    "我朋友说他男朋友出轨了 怎么办",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_dir", type=Path, required=True)
    parser.add_argument(
        "--system_prompt",
        type=Path,
        default=Path("/content/Yijun.skill/prompts/yijun_voice_intimate.md"),
    )
    parser.add_argument("--max_new_tokens", type=int, default=200)
    parser.add_argument("--temperature", type=float, default=0.85)
    parser.add_argument("--top_p", type=float, default=0.9)
    parser.add_argument("--repetition_penalty", type=float, default=1.05)
    parser.add_argument("--max_seq_length", type=int, default=2048)
    args = parser.parse_args()

    system = args.system_prompt.read_text(encoding="utf-8").strip()
    print(f"Loading {args.model_dir} ...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(args.model_dir),
        max_seq_length=args.max_seq_length,
        dtype=None,           # auto: bf16 on A100/H100, fp16 on T4
        load_in_4bit=False,   # merged_16bit weights are already full precision
    )
    FastLanguageModel.for_inference(model)  # ~2x faster decode
    model.eval()

    for i, prompt in enumerate(PROBES, 1):
        chat = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        text = tokenizer.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(text, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=True,
                temperature=args.temperature,
                top_p=args.top_p,
                repetition_penalty=args.repetition_penalty,
                pad_token_id=tokenizer.eos_token_id,
            )
        reply = tokenizer.decode(
            out[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True
        ).strip()
        print(f"\n--- {i}/5 ---")
        print(f"对方: {prompt}")
        print(f"Yijun: {reply}")


if __name__ == "__main__":
    main()
