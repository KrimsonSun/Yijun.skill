"""Smoke-test a freshly-trained Yijun model on Colab.

Loads the merged 16-bit model and generates replies to 5 hold-out prompts so
you can eyeball whether the LoRA actually learned your voice before
downloading 6 GB of weights.

Usage (in Colab cell):
    !python /content/Yijun.skill/colab/test_generate.py \
        --model_dir /content/yijun-3b/merged_16bit
"""
from __future__ import annotations

import argparse
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

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
    args = parser.parse_args()

    system = args.system_prompt.read_text(encoding="utf-8").strip()
    print(f"Loading {args.model_dir} ...")
    tokenizer = AutoTokenizer.from_pretrained(args.model_dir, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_dir,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
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
                temperature=0.85,
                top_p=0.9,
                repetition_penalty=1.05,
                pad_token_id=tokenizer.eos_token_id,
            )
        reply = tokenizer.decode(out[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True).strip()
        print(f"\n--- {i}/5 ---")
        print(f"对方: {prompt}")
        print(f"Yijun: {reply}")


if __name__ == "__main__":
    main()
