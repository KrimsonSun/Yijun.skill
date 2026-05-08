# Colab 训练流程

> 用 A100（学生计算单元）训 LoRA，权重存回 Google Drive，本地下载后转 GGUF。

## 步骤 1：准备 Google Drive

在你的 Google Drive 根目录新建 `yijun_bot/` 文件夹，把 `finetune_clean.jsonl` 上传进去：

```
MyDrive/
└── yijun_bot/
    └── finetune_clean.jsonl   ← 你的训练数据
```

## 步骤 2：新建 Colab notebook + 选 A100 runtime

`Runtime → Change runtime type → A100 GPU`

## 步骤 3：粘贴以下 4 个 cell，依次执行

### Cell 1：挂载 Drive

```python
from google.colab import drive
drive.mount('/content/drive')
```

### Cell 2：先确认 GPU 在线

```python
!nvidia-smi
```

如果看不到 A100/T4/V100 → runtime 没切到 GPU，去 `Runtime → Change runtime type → A100` 再回来。

### Cell 3：拉代码 + 装依赖（一次会话只跑一次）

```python
!git clone https://github.com/KrimsonSun/Yijun.skill.git /content/Yijun.skill
!pip install -q "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
```

> Colab 默认运行时偶尔会带 CPU-only 的 torch（错误："torch X.Y.Z+cpu" / "cannot find any torch accelerator"）。如果遇到，跑一次：
> ```python
> !pip uninstall -y torch torchvision torchaudio
> !pip install -q --upgrade torch
> !pip install -q --upgrade --force-reinstall "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
> ```
> 然后 **Runtime → Restart session**，重跑 Cell 1（挂 Drive）+ Cell 2（GPU 检查）+ 后续训练。

### Cell 4：跑训练（3B，约 2-3 分钟）

```python
!bash /content/Yijun.skill/colab/run.sh 3b
```

跑完后 `/content/drive/MyDrive/yijun_bot/output/yijun-3b-merged/` 就是合并好的 HF 权重，约 6 GB。

### Cell 5（可选）：肉眼检查模型有没有学到你的风格

```python
!python /content/Yijun.skill/colab/test_generate.py \
    --model_dir /content/yijun-3b/merged_16bit
```

会跑 5 条 hold-out prompt，看回复像不像你（有"嘿嘿/嘻嘻/[凋谢]"之类的就是学到了）。

## 步骤 4：本地下载 → 转 GGUF

在 Mac 上：

```bash
# 1. 把 Drive 里的 yijun-3b-merged/ 整个文件夹下载到 Mac，比如放到
#    ~/Downloads/yijun-3b-merged/

# 2. 转 GGUF Q4_K_M
cd ~/Documents/Git/Yijun.skill
./training/export_gguf.sh ~/Downloads/yijun-3b-merged output/yijun-gguf

# 完成后 output/yijun-gguf/yijun-Q4_K_M.gguf 约 1.9 GB，部署用这个
```

## 想顺便训一个 7B 对照？

A100 上 7B 也只要 5-10 分钟：

```python
!bash /content/Yijun.skill/colab/run.sh 7b
```

会输出到 `output/yijun-7b-merged`，下载下来同样跑 `export_gguf.sh` 即可。注意 7B Q4_K_M ~4.5 GB，在 Oracle ARM CPU 上太慢（2-4 tok/s）；7B 模型本地 Mac (Apple Silicon) 用 Ollama 跑还行。

## 常见坑

- **Drive 没挂载就跑 Cell 3**：会报"finetune_clean.jsonl not found"。先跑 Cell 1。
- **A100 排不到**：Colab Pro/学生计算单元偶尔会降级到 V100/T4，不影响训练正确性，只是慢一点。
- **Drive 写入 6 GB 慢**：合并权重写回 Drive 大约 1-2 分钟，正常现象。
- **重新训练**：直接重跑 Cell 3 即可，会覆盖 Drive 里的旧输出。
- **想保留 LoRA adapter**（小，30 MB）而不是 merged：去 Drive 看 `yijun-3b-lora/`，那个才是裸 adapter，改天想换底模可以重新合并。
