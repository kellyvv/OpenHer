# Qwen3-TTS 自定义声音微调完整指南

## 目标

微调 Qwen3-TTS-12Hz-1.7B-Base 模型，创建自定义持久声音，支持**自定义音色 + 指令控制情绪**。

---

## 环境要求

| 项目 | 推荐配置 |
|------|---------|
| GPU | vGPU-48GB / A100 40GB / 4090 24GB |
| PyTorch | 2.x + CUDA 12.x（⚠️ **5090 暂不支持**，需 CUDA 12.8+） |
| 关键依赖 | `qwen-tts`, `soundfile`, `accelerate`, `safetensors`, `flash-attn`, `modelscope` |

> [!CAUTION]
> RTX 5090 (sm_120) 截至 2026-02 仍无稳定 PyTorch 支持。请选择 A100/4090 等 sm_80/sm_89 架构的 GPU。

---

## 完整流程

```mermaid
graph LR
    A[VoiceDesign 生成音频] --> B[EasyFT split 切分]
    B --> C[EasyFT ASR 转录]
    C --> D[生成 train_raw.jsonl]
    D --> E[官方 prepare_data.py]
    E --> F[官方 sft_12hz.py 训练]
    F --> G[推理测试]
```

---

## Step 1: 生成训练音频

用 VoiceDesign 定制音色，**一次调用生成长音频**确保音色一致。

```bash
python3 -c "
import torch, soundfile as sf
from qwen_tts import Qwen3TTSModel

vd = Qwen3TTSModel.from_pretrained(
    '/root/autodl-tmp/models/Qwen/Qwen3-TTS-12Hz-1___7B-VoiceDesign',
    device_map='cuda:0', dtype=torch.bfloat16, attn_implementation='flash_attention_2',
)

# 定义音色
VOICE = '少女感的女声，嗓音略带沙沙的气泡音质感，像是刚睡醒还带着一点奶味的慵懒'

# 所有训练文本拼在一起
texts = ['哈哈哈你太搞笑了！', '对不起，我知道是我不好。', ...]  # 完整列表见 gen_multi_emotion_data.py
combined = '。'.join(texts) + '。'

wavs, sr = vd.generate_voice_design(text=combined, language='Chinese', instruct=VOICE, max_new_tokens=16384)
sf.write('all_in_one.wav', wavs[0], sr)
"
```

> [!WARNING]
> VoiceDesign 单次生成超过 **5-6 分钟**后音频质量会退化。如果文本很多，建议分 2-3 批生成或只取前 6 分钟。

**裁剪前 6 分钟**：
```bash
python3 -c "
import soundfile as sf
data, sr = sf.read('all_in_one.wav')
sf.write('all_in_one_6min.wav', data[:sr*360], sr)
"
```

---

## Step 2: EasyFT 切分 + ASR 转录

```bash
# 复制音频
cp all_in_one_6min.wav /workspace/raw-dataset/openher_girl/all_in_one.wav

cd ~/EasyFT

# 切分
python src/cli.py split --input_dir raw-dataset/openher_girl --speaker_name openher_girl

# ASR（国内用 ModelScope 源）
python src/cli.py asr --speaker_name openher_girl --model_source ModelScope
```

---

## Step 3: 准备官方格式 JSONL

> [!IMPORTANT]
> **必须确保 `ref_audio` 字段不为空！** 这是之前训练出杂音的根本原因。

```bash
python3 -c "
import json, os, glob
segs = sorted(glob.glob('/workspace/final-dataset/openher_girl/audio_24k/*.wav'))
ref = segs[0]  # 第一段作为 ref_audio

entries = []
with open('/workspace/final-dataset/openher_girl/tts_train.jsonl') as f:
    for line in f:
        d = json.loads(line)
        audio = d.get('audio','')
        if not audio.startswith('/'):
            audio = '/workspace/' + audio
        if audio and d.get('text') and os.path.exists(audio):
            entries.append({'audio': audio, 'text': d['text'], 'ref_audio': ref})

with open('/root/autodl-tmp/train_raw.jsonl', 'w') as f:
    for e in entries:
        f.write(json.dumps(e, ensure_ascii=False) + '\n')
print(f'{len(entries)} 条')
"
```

---

## Step 4: 官方 prepare_data.py 提取 audio_codes

```bash
cd ~/Qwen3-TTS/finetuning

python prepare_data.py \
  --device cuda:0 \
  --tokenizer_model_path /root/autodl-tmp/models/Qwen/Qwen3-TTS-Tokenizer-12Hz \
  --input_jsonl /root/autodl-tmp/train_raw.jsonl \
  --output_jsonl /root/autodl-tmp/train_with_codes.jsonl
```

---

## Step 5: 官方 sft_12hz.py 训练

> [!IMPORTANT]
> **必须用官方脚本训练，不要用 EasyFT 的训练！** EasyFT 的 sft_12hz.py 有 bug，训练出的模型推理会产生杂音。

```bash
# 先去掉 tensorboard（如果环境没装）
sed -i 's/, log_with="tensorboard"//g' sft_12hz.py

python sft_12hz.py \
  --init_model_path /root/autodl-tmp/models/Qwen/Qwen3-TTS-12Hz-1___7B-Base \
  --output_model_path /root/autodl-tmp/output \
  --train_jsonl /root/autodl-tmp/train_with_codes.jsonl \
  --batch_size 2 --lr 1e-5 --num_epochs 8 \
  --speaker_name openher_girl
```

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| batch_size | 2 | 48GB 可到 4 |
| lr | 1e-5 | 学习率 |
| num_epochs | 5-8 | >10 可能过拟合 |
| speaker_name | 自定义 | 推理时使用同名 |

---

## Step 6: 推理测试

```python
import torch, soundfile as sf
from qwen_tts import Qwen3TTSModel

tts = Qwen3TTSModel.from_pretrained(
    '/root/autodl-tmp/output/checkpoint-epoch-7',
    device_map='cuda:0', dtype=torch.bfloat16,
    attn_implementation='flash_attention_2',
)

# 基础生成（无指令）
wavs, sr = tts.generate_custom_voice(
    text='你好呀，今天过得怎么样？',
    speaker='openher_girl',
    language='Chinese',
)

# 带指令控制
wavs, sr = tts.generate_custom_voice(
    text='对不起，我知道是我不好。',
    speaker='openher_girl',
    language='Chinese',
    instruct='用带着哭腔的悲伤语气说',
)
sf.write('output.wav', wavs[0], sr)
```

---

## 指令控制技巧

### 简短指令（稳定）
```
"用特别愤怒的语气说"
"用撒娇卖萌的语气说"
"用温柔慵懒的语气轻声说"
```

### 丰富指令（更有表现力）
```
"声音颤抖带着哽咽，语速从犹豫到急切，尾音微弱消散，像是在鼓起最后的勇气开口"
"嘴硬心软的别扭语气，前半句刻意冷淡但不自然，后半句语速加快暴露心虚"
"沉稳而富有画面感的叙述腔，在关键意象处稍作停顿，语调平缓但充满感染力"
```

### 指令风格参考
> 描述**声音的物理特征**（语速变化、音调走向、气息感）比单纯的情绪标签更有效。

---

## 踩坑记录

| 问题 | 根因 | 解决 |
|------|------|------|
| 训练出杂音 / 生成 40s+ 噪声 | JSONL 中 `ref_audio` **为空** | 确保每条都有 ref_audio |
| EasyFT 训练 loss 正常但推理全是噪声 | EasyFT sft_12hz.py 训练有 bug | **改用官方 sft_12hz.py** |
| Checkpoint 保存崩溃 | 系统盘空间不足 (overlay 30GB) | 输出目录放到数据盘 `/root/autodl-tmp/` |
| 10 epoch 过拟合变杂音 | 数据量少 + 训练太久 | 5-8 epoch 为宜，监控 loss |
| VoiceDesign 长音频退化 | 单次生成超 5-6 分钟 | 裁剪前 6 分钟或分批 |
| RTX 5090 无法运行 | PyTorch 不支持 sm_120 | 换 A100 / 4090 |
| HuggingFace 连不上 | 国内网络限制 | `--model_source ModelScope` 或 `pip install modelscope` |

---

## 提升指令控制能力

训练数据应覆盖**多种情绪场景**：开心、悲伤、生气、撒娇、惊喜、平静、困倦、害羞、傲娇、严肃、调皮等。完整的多情绪训练语料见 [gen_multi_emotion_data.py](file:///Users/zxw/AITOOL/openher/gen_multi_emotion_data.py)。

---

## 文件清单

| 文件 | 说明 |
|------|------|
| [gen_multi_emotion_data.py](file:///Users/zxw/AITOOL/openher/gen_multi_emotion_data.py) | 多情绪训练数据生成脚本（12 种情绪 × 8-10 句） |
| [official_train.sh](file:///Users/zxw/AITOOL/openher/official_train.sh) | 官方训练流程一键脚本 |
| [tts_finetune_colab.py](file:///Users/zxw/AITOOL/openher/tts_finetune_colab.py) | Colab 版本（已弃用，改用 AutoDL） |

---

## AutoDL 模型路径参考

```
/root/autodl-tmp/models/Qwen/Qwen3-TTS-12Hz-1___7B-Base          # 基础模型
/root/autodl-tmp/models/Qwen/Qwen3-TTS-12Hz-1___7B-VoiceDesign   # VoiceDesign
/root/autodl-tmp/models/Qwen/Qwen3-TTS-12Hz-1___7B-CustomVoice   # 官方预设 CV
/root/autodl-tmp/models/Qwen/Qwen3-TTS-Tokenizer-12Hz            # Tokenizer
/workspace/models/Qwen/Qwen3-ASR-1___7B                          # ASR 模型
```
