#!/usr/bin/env python3
"""
MiniMax TTS API 测试 — 中文语音合成
Speech-2.8-HD 模型 + 情绪控制 + 克隆音色

使用前设置环境变量：
  export MINIMAX_API_KEY="your-api-key"

如果你已经在 MiniMax 平台克隆了音色，把 voice_id 填入 CLONE_VOICE_ID。
voice_id 获取方式：MiniMax Audio → 个人音色 → 点击音色 → 复制 voice_id
"""
import os
import sys
import json
import time
import requests
from pathlib import Path

# ============================================================
# 配置
# ============================================================
API_KEY = os.environ.get("MINIMAX_API_KEY", "")
API_URL = "https://api.minimax.io/v1/t2a_v2"
MODEL = "speech-2.8-hd"  # 最新最好的模型

# 克隆音色 ID（在 MiniMax Audio 平台创建后填入）
# 如果没有克隆音色，留空则用系统音色
CLONE_VOICE_ID = ""  # 例: "your_cloned_voice_id"

# 系统内置中文音色（备选）
SYSTEM_VOICE_ID = "Chinese_female_anchor_3"  # 或 "Chinese_male_voice_1"

OUTPUT_DIR = Path("./minimax_tts_output")
OUTPUT_DIR.mkdir(exist_ok=True)

if not API_KEY:
    print("❌ 请设置环境变量 MINIMAX_API_KEY")
    print("   export MINIMAX_API_KEY='your-api-key'")
    sys.exit(1)

# ============================================================
# 核心调用函数
# ============================================================
def tts_generate(
    text: str,
    voice_id: str,
    output_path: str,
    speed: float = 1.0,
    emotion: str = None,  # happy, sad, angry, fearful, disgusted, surprised, neutral
    language_boost: str = "Chinese",
    voice_modify: dict = None,
):
    """调用 MiniMax T2A HTTP API"""
    payload = {
        "model": MODEL,
        "text": text,
        "stream": False,
        "language_boost": language_boost,
        "output_format": "hex",
        "voice_setting": {
            "voice_id": voice_id,
            "speed": speed,
            "vol": 1,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
    }

    if emotion:
        payload["voice_setting"]["emotion"] = emotion

    if voice_modify:
        payload["voice_modify"] = voice_modify

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    t0 = time.time()
    resp = requests.post(API_URL, headers=headers, json=payload, timeout=60)
    elapsed = time.time() - t0

    if resp.status_code != 200:
        print(f"  ✗ HTTP {resp.status_code}: {resp.text[:200]}")
        return False

    result = resp.json()
    base_resp = result.get("base_resp", {})
    if base_resp.get("status_code", -1) != 0:
        print(f"  ✗ API Error: {base_resp.get('status_msg', 'unknown')}")
        return False

    # 解码 hex 音频
    audio_hex = result["data"]["audio"]
    audio_bytes = bytes.fromhex(audio_hex)
    with open(output_path, "wb") as f:
        f.write(audio_bytes)

    extra = result.get("extra_info", {})
    duration = extra.get("audio_length", 0) / 1000  # ms -> s
    chars = extra.get("usage_characters", 0)
    print(f"  ✓ {output_path} ({duration:.1f}s, {chars}字, {elapsed:.1f}s)")
    return True


# ============================================================
# 测试用例
# ============================================================

voice_id = CLONE_VOICE_ID if CLONE_VOICE_ID else SYSTEM_VOICE_ID
print(f"使用音色: {voice_id}")
print(f"模型: {MODEL}")
print(f"API: {API_URL}")

# --- 测试 1: 基础中文合成 ---
print(f"\n{'='*60}")
print("  测试 1: 基础中文语音合成")
print(f"{'='*60}")

basic_texts = [
    ("basic_greeting", "你好，欢迎使用MiniMax语音合成服务。今天天气不错，适合出去走走。"),
    ("basic_story",    "从前有一个小男孩，他住在山脚下的一个小村庄里。每天早上，他都会爬上山顶，看日出。"),
    ("basic_news",     "据新华社报道，我国科研团队在量子计算领域取得重大突破，成功实现了五百量子比特的纠错操作。"),
]

for name, text in basic_texts:
    print(f"\n--- {name} ---")
    tts_generate(text, voice_id, str(OUTPUT_DIR / f"{name}.mp3"))

# --- 测试 2: 7 种情绪控制 ---
print(f"\n{'='*60}")
print("  测试 2: 情绪控制 (7种情绪)")
print(f"{'='*60}")

emotion_text = "收到好友从远方寄来的生日礼物，那份意外的惊喜让我心中充满了感动。"

emotions = [
    ("emotion_neutral",   "neutral",   "中性"),
    ("emotion_happy",     "happy",     "开心"),
    ("emotion_sad",       "sad",       "悲伤"),
    ("emotion_angry",     "angry",     "愤怒"),
    ("emotion_fearful",   "fearful",   "恐惧"),
    ("emotion_disgusted", "disgusted", "厌恶"),
    ("emotion_surprised", "surprised", "惊讶"),
]

for name, emotion, label in emotions:
    print(f"\n--- {name} ({label}) ---")
    tts_generate(emotion_text, voice_id, str(OUTPUT_DIR / f"{name}.mp3"), emotion=emotion)

# --- 测试 3: 语速控制 ---
print(f"\n{'='*60}")
print("  测试 3: 语速控制")
print(f"{'='*60}")

speed_text = "收到好友从远方寄来的生日礼物，那份意外的惊喜让我心中充满了感动。"

speeds = [
    ("speed_slow",   0.7, "慢速"),
    ("speed_normal", 1.0, "正常"),
    ("speed_fast",   1.5, "快速"),
    ("speed_turbo",  2.0, "极速"),
]

for name, speed, label in speeds:
    print(f"\n--- {name} ({label}, speed={speed}) ---")
    tts_generate(speed_text, voice_id, str(OUTPUT_DIR / f"{name}.mp3"), speed=speed)

# --- 测试 4: 感叹词标签 (2.8专属) ---
print(f"\n{'='*60}")
print("  测试 4: 感叹词/语气词标签 (Speech-2.8 专属)")
print(f"{'='*60}")

interjection_texts = [
    ("interjection_laugh", "(laughs)哈哈，你说的太对了！我完全同意你的观点。"),
    ("interjection_sigh",  "(sighs)唉，又加班了，什么时候才能好好休息一下呢。"),
    ("interjection_gasp",  "(gasps)天哪！你居然来了！我完全没想到！"),
    ("interjection_hmm",   "(emm)让我想想...这个问题确实有点复杂，需要仔细考虑。"),
]

for name, text in interjection_texts:
    print(f"\n--- {name} ---")
    tts_generate(text, voice_id, str(OUTPUT_DIR / f"{name}.mp3"))

# --- 测试 5: 停顿控制 ---
print(f"\n{'='*60}")
print("  测试 5: 停顿控制 <#x#>")
print(f"{'='*60}")

pause_text = "接下来<#1.5#>我要宣布一个重要消息<#2#>我们的项目<#0.5#>成功了！"
print(f"\n--- pause_control ---")
tts_generate(pause_text, voice_id, str(OUTPUT_DIR / "pause_control.mp3"))

# --- 测试 6: 音效修改 ---
print(f"\n{'='*60}")
print("  测试 6: 音效修改 (voice_modify)")
print(f"{'='*60}")

modify_text = "你好，这是一段测试音频，用来测试不同的音效设置。"
modifies = [
    ("modify_echo",   {"pitch": 0, "intensity": 0, "timbre": 0, "sound_effects": "spacious_echo"}, "空间回响"),
    ("modify_highpitch", {"pitch": 5, "intensity": 0, "timbre": 0}, "高音调"),
    ("modify_lowpitch",  {"pitch": -5, "intensity": 0, "timbre": 0}, "低音调"),
]

for name, modify, label in modifies:
    print(f"\n--- {name} ({label}) ---")
    tts_generate(modify_text, voice_id, str(OUTPUT_DIR / f"{name}.mp3"), voice_modify=modify)

# ============================================================
# 统计
# ============================================================
all_files = list(OUTPUT_DIR.glob("*.mp3"))
total_size = sum(f.stat().st_size for f in all_files) / 1024
print(f"\n{'='*60}")
print(f"  完成！共生成 {len(all_files)} 个音频文件")
print(f"  输出目录: {OUTPUT_DIR.absolute()}")
print(f"  总大小: {total_size:.1f} KB")
print(f"{'='*60}")
