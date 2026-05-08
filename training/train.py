"""Unsloth QLoRA training for Yijun voice on Qwen2.5-3B-Instruct.

Hyperparameters are tuned for ~919 conversations (~23k messages):
- attention-only LoRA (style, not facts)
- low rank, low LR, dropout, early stop on val loss

Run on Kaggle T4×2 (free, 30h/wk) or Colab T4 free.

    python training/train.py \
        --dataset_dir source_data/sft_dataset \
        --base_model unsloth/Qwen2.5-3B-Instruct-bnb-4bit \
        --output_dir output/yijun-qwen2.5-3b-lora
"""
from __future__ import annotations

import argparse
from pathlib import Path

# Unsloth must be imported before transformers/trl/peft for its monkey-patches
# to take effect. Keep this import at the top of the file.
from unsloth import FastLanguageModel  # noqa: I001  (intentional ordering)
from unsloth.chat_templates import train_on_responses_only

import torch
from datasets import load_from_disk
from transformers import (
    EarlyStoppingCallback,
    TrainingArguments,
)
from trl import SFTTrainer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset_dir", type=Path, required=True)
    parser.add_argument(
        "--base_model",
        type=str,
        default="unsloth/Qwen2.5-3B-Instruct-bnb-4bit",
        help="Use unsloth/Qwen2.5-7B-Instruct-bnb-4bit for the 7B parallel run.",
    )
    parser.add_argument("--output_dir", type=Path, required=True)
    parser.add_argument("--max_seq_length", type=int, default=2048)
    parser.add_argument("--lora_r", type=int, default=8)
    parser.add_argument("--lora_alpha", type=int, default=16)
    # Unsloth fast LoRA fused path requires dropout = 0. Setting >0 forces a
    # slow fallback that uses 5-10× more activation memory and causes OOM
    # even on H100. We rely on attention-only LoRA + val-loss early stop +
    # only 3 epochs as the over-fitting guard instead of dropout.
    parser.add_argument("--lora_dropout", type=float, default=0.0)
    parser.add_argument("--learning_rate", type=float, default=1e-4)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--per_device_batch_size", type=int, default=4)
    parser.add_argument("--grad_accum_steps", type=int, default=4)
    parser.add_argument("--warmup_ratio", type=float, default=0.1)
    parser.add_argument("--save_merged_16bit", action="store_true")
    args = parser.parse_args()

    # --- Load model + tokenizer (4-bit base, prepared for QLoRA)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=args.max_seq_length,
        dtype=None,
        load_in_4bit=True,
    )

    # --- Attach LoRA: attention only, no MLP (style not facts)
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
        use_rslora=False,
        loftq_config=None,
    )

    # --- Dataset has a single "text" field (rendered chat template)
    dataset = load_from_disk(str(args.dataset_dir))
    print(f"Train: {len(dataset['train'])}  Val: {len(dataset['validation'])}")

    # --- TrainingArguments
    training_args = TrainingArguments(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.per_device_batch_size,
        per_device_eval_batch_size=args.per_device_batch_size,
        gradient_accumulation_steps=args.grad_accum_steps,
        learning_rate=args.learning_rate,
        warmup_ratio=args.warmup_ratio,
        lr_scheduler_type="cosine",
        weight_decay=0.01,
        optim="adamw_8bit",
        bf16=torch.cuda.is_bf16_supported(),
        fp16=not torch.cuda.is_bf16_supported(),
        logging_steps=5,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        save_total_limit=2,
        report_to="none",
        seed=42,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset["train"],
        eval_dataset=dataset["validation"],
        args=training_args,
        max_seq_length=args.max_seq_length,
        packing=False,
        dataset_text_field="text",
        callbacks=[EarlyStoppingCallback(early_stopping_patience=1)],
    )

    # Mask everything except assistant turns. Unsloth scans for the chat
    # template's instruction/response markers and sets labels=-100 on every
    # token that isn't part of an assistant response. This replaces our
    # earlier hand-rolled token-span masking, which was buggy and caused the
    # model to learn parts of the user side (role-confused outputs).
    trainer = train_on_responses_only(
        trainer,
        instruction_part="<|im_start|>user\n",
        response_part="<|im_start|>assistant\n",
    )

    trainer_stats = trainer.train()
    print(trainer_stats)

    # --- Save adapter
    args.output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(args.output_dir / "lora_adapter"))
    tokenizer.save_pretrained(str(args.output_dir / "lora_adapter"))

    # --- Optional: merged 16-bit weights ready for GGUF conversion
    if args.save_merged_16bit:
        merged_dir = args.output_dir / "merged_16bit"
        model.save_pretrained_merged(
            str(merged_dir),
            tokenizer,
            save_method="merged_16bit",
        )
        print(f"Merged 16-bit weights saved to {merged_dir}")


if __name__ == "__main__":
    main()
