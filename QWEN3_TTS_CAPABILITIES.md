# Qwen3-TTS 控制能力手册

> 模型路径：`/Users/zxw/AITOOL/openher/Qwen3-TTS-12Hz-1.7B-CustomVoice`
> Python 包：`qwen_tts`（已安装在 server/venv）
> 官方博客：https://qwen.ai/blog?id=qwen3tts-0115
> 项目封装：`/Users/zxw/AITOOL/openher/server/tts/qwen3_tts.py`

---

## 三种模型变体

| 变体 | 用途 | instruct 控制 | 音色来源 |
|------|------|--------------|---------|
| **CustomVoice** | 内置音色 + 指令控制 | ✅ | 9 个预训练 speaker |
| **VoiceDesign** | 自然语言设计新音色 | 设计音色用，非表达控制 | 文字描述生成 |
| **Base** | 克隆任意音色 | ❌ | 参考音频 |

**项目使用 CustomVoice** — 内置音色 + instruct 控制表达。

---

## 9 个内置 Speaker

> 来源：`config.json` 中的 `spk_id` 字典

| Speaker | ID | 描述 | 母语 | 方言 |
|---------|-----|------|------|------|
| **vivian** | 3065 | 明亮、略带锐利的年轻女声 | 中文 | - |
| **serena** | 3066 | 温暖、温柔的年轻女声 | 中文 | - |
| **uncle_fu** | 3010 | 沉稳低沉的成熟男声 | 中文 | - |
| **dylan** | 2878 | 清澈自然的北京年轻男声 | 中文 | 北京话 |
| **eric** | 2875 | 活泼、略带沙哑的成都男声 | 中文 | 四川话 |
| **ryan** | 3061 | 充满节奏感的动感男声 | 英文 | - |
| **aiden** | 2861 | 阳光的美式男声 | 英文 | - |
| **ono_anna** | 2873 | 俏皮轻盈的日本女声 | 日文 | - |
| **sohee** | 2864 | 温暖富有情感的韩国女声 | 韩文 | - |

每个 speaker 都能说模型支持的所有 10 种语言，但用母语效果最好。

---

## Instruct 控制方式

`instruct` 参数接受**自然语言描述**，控制语音的表达方式而不改变音色。

### 调用方式

```python
from qwen_tts import Qwen3TTSModel

model = Qwen3TTSModel("Qwen3-TTS-12Hz-1.7B-CustomVoice")

audio = model.custom_voice(
    text="没事的，别担心，我一直都在呢。",
    speaker="vivian",
    instruct="温暖轻柔的语气，语速缓慢平稳，带安抚感",
)
```

### 可控维度

#### 1. 情绪/语气（emotion）

自由组合，不限于预设标签。支持复合情绪：

```
"用特别愤怒的语气说"
"展现出悲苦沙哑的声音质感，语速偏慢，情绪浓烈且带有哭腔"
"温柔中带点心疼"
"俏皮但又有点害羞"
"冷淡克制但内心不舍"
"兴奋到快要溢出来的开心"
```

#### 2. 音调（pitch）

```
"音调偏高"
"音调偏低且不稳定"
"音调起伏明显"
"音调平直克制"
"尾音上扬"
"尾音下沉"
```

#### 3. 语速（speed）

```
"语速轻快"
"语速缓慢"
"Speaking at an extremely slow pace"
"语速从平稳开始在叙述过程中逐渐加快"   ← 渐变控制！
```

#### 4. 音量/气息（volume）

```
"请特别小声的悄悄说"
"音量偏低带安抚感"
"气息柔和"
"气息收紧"
```

#### 5. 副语言（sub-vocalizations）

```
"夹杂自然的轻笑"
"带有哭腔"
"声音微微颤抖"
"像在耳边悄悄说"    （耳语）
"轻轻叹气"
```

#### 6. 渐变控制（temporal dynamics）

模型理解时间相关指令：

```
"语速从平稳开始在叙述过程中逐渐加快"
"音量随叙述深入逐渐降低"
"开头语气强硬，到句尾逐渐软化"
```

#### 7. 结构化 key-value 格式（也支持）

```
gender: Female. pitch: High... speed: Rapid during the laugh, 
then slowing... emotion: Forced amusement.
```

#### 8. 人设级综合描述

```
"采用高亢的男性嗓音，语调随兴奋情绪不断上扬，
以快速而充满活力的节奏传达信息，展现出外向、自信且张扬的个性"

"体现撒娇稚嫩的萝莉女声，音调偏高且起伏明显，
营造出黏人、做作又刻意卖萌的听觉效果"
```

---

## Instruct 示例库（可直接用于 Delivery LLM 参考）

### 安慰/温柔
```
温暖轻柔的语气，语速缓慢平稳，音量偏低，气息柔和带安抚感
```

### 撒娇/俏皮
```
音调偏高且起伏明显，尾音上扬拖长，语速轻快跳跃，带撒娇嘟嘴感
```

### 冷淡/疏离
```
音调平直克制，语速干脆不拖泥带水，情绪冷淡，气息收紧
```

### 愤怒/不满
```
用特别愤怒的语气说，语速偏快，音量加大，语调尖锐
```

### 悲伤/低落
```
展现出悲苦沙哑的声音质感，语速偏慢，情绪浓烈且带有哭腔
```

### 兴奋/开心
```
语气兴奋上扬，语速加快，音调偏高，夹杂自然的轻笑
```

### 害羞/紧张
```
声音轻柔微弱，偶有停顿和犹豫，音调略高且不稳定，带气息颤抖
```

### 嘴硬/倔强
```
语气不服气但声音偏软，音调起伏带别扭感，尾音轻微上扬像在赌气
```

---

## 技术细节

### 模型参数

- 模型大小：1.7B
- 采样率：12Hz token rate
- 支持语言：10 种（中文/英文/日文/韩文/法文/德文/西文/俄文/阿拉伯文/葡萄牙文）

### API 关键方法

```python
# 获取支持的 speaker 列表
speakers = model.get_supported_speakers()  # → ['aiden','dylan','eric',...]

# CustomVoice 合成（内置音色 + instruct）
audio = model.custom_voice(
    text="要说的文字",
    speaker="vivian",           # 9 选 1
    instruct="表达方式描述",     # 自然语言
)

# VoiceDesign 合成（设计新音色）
audio = model.voice_design(
    text="要说的文字", 
    design="描述想要的声音特征",
)
```

### 限制

- CustomVoice 只有 9 个内置音色，不能自定义
- Base 模型支持 voice clone 但**不支持 instruct 控制**
- instruct 过长可能降低效果，建议控制在 1-2 句话

---

## 备选方案：Fun-CosyVoice3

> 路径：`/Users/zxw/AITOOL/openher/Fun-CosyVoice3`

如需**克隆音色 + instruct 控制**同时使用，需走 Fun-CosyVoice3：

```python
cosyvoice.inference_instruct2(
    tts_text="要说的话",
    instruct_text="请用温柔的语气说话。<|endofprompt|>",
    prompt_wav=reference_audio,  # 参考音频决定音色
    stream=False,
)
```

支持方言切换、语速控制、情绪控制，但需要参考音频。
