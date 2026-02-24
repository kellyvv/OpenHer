#!/usr/bin/env python3
"""
TTS API 使用示例

展示 Qwen3-TTS (本地音色设计) 和 MiniMax TTS (克隆+情绪) 的完整用法
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path

OUTPUT = Path("./tts_output")
OUTPUT.mkdir(exist_ok=True)


def demo_qwen3():
    """Qwen3-TTS 本地演示"""
    from tts.qwen3_tts import Qwen3TTSClient

    client = Qwen3TTSClient()

    # ---- 1. 文字描述设计音色 ----
    print("\n=== Qwen3-TTS: 音色设计 ===")
    result = client.voice_design(
        text="你好，我是你的专属助手，有什么可以帮你的吗？",
        description="一个温柔知性的年轻女性声音，语速适中，带有轻柔的气息感",
        language="Chinese",
    )
    path = result.save(str(OUTPUT / "qwen3_design.wav"))
    print(f"  ✓ {path} ({result.duration:.1f}s, 耗时{result.elapsed:.1f}s)")

    # 保存设计好的音频，后续可给 MiniMax 做克隆参考
    design_audio_path = str(OUTPUT / "qwen3_design.wav")

    # ---- 2. 内置音色 + 指令控制 ----
    print("\n=== Qwen3-TTS: 内置音色 + 情绪指令 ===")
    tests = [
        ("vivian", "用开心兴奋的语气说", "custom_happy"),
        ("vivian", "用伤心难过的语气说", "custom_sad"),
        ("serena", "用温柔轻声细语的方式说", "custom_gentle"),
    ]
    text = "收到好友从远方寄来的生日礼物，那份意外的惊喜让我心中充满了感动。"

    for speaker, instruct, name in tests:
        result = client.custom_voice(
            text=text,
            speaker=speaker,
            instruct=instruct,
        )
        path = result.save(str(OUTPUT / f"qwen3_{name}.wav"))
        print(f"  ✓ {path} ({result.duration:.1f}s)")

    # ---- 3. 克隆音色 ----
    print("\n=== Qwen3-TTS: 音色克隆 ===")
    # 用刚才设计的音色作为参考，克隆后说新句子
    result = client.voice_clone(
        text="明天的会议改到下午三点了，记得提前准备材料。",
        ref_audio=design_audio_path,
        ref_text="你好，我是你的专属助手，有什么可以帮你的吗？",
    )
    path = result.save(str(OUTPUT / "qwen3_clone.wav"))
    print(f"  ✓ {path} ({result.duration:.1f}s)")

    # 复用 prompt 说多句话
    print("\n--- 复用 clone prompt ---")
    prompt = client.create_clone_prompt(
        ref_audio=design_audio_path,
        ref_text="你好，我是你的专属助手，有什么可以帮你的吗？",
    )
    for i, t in enumerate([
        "今天天气不错，适合出去走走。",
        "你的快递已经到了，放在前台了。",
    ]):
        result = client.voice_clone(text=t, voice_clone_prompt=prompt)
        path = result.save(str(OUTPUT / f"qwen3_clone_multi_{i+1}.wav"))
        print(f"  ✓ {path} ({result.duration:.1f}s)")

    return design_audio_path


def demo_minimax(ref_audio_path: str = None):
    """MiniMax TTS API 演示"""
    from tts.minimax_tts import MiniMaxTTSClient

    try:
        client = MiniMaxTTSClient()  # 从环境变量读取 API Key
    except ValueError as e:
        print(f"\n⚠️  {e}")
        print("跳过 MiniMax 演示 (未设置 API Key)")
        return

    text = "收到好友从远方寄来的生日礼物，那份意外的惊喜让我心中充满了感动。"

    # ---- 1. 克隆音色 (如果有参考音频) ----
    voice_id = "Chinese_female_anchor_3"  # 默认用系统音色

    if ref_audio_path and os.path.exists(ref_audio_path):
        print("\n=== MiniMax: 克隆 Qwen3 设计的音色 ===")
        try:
            voice_id = client.clone_voice(
                audio_path=ref_audio_path,
                voice_id="qwen3_designed_voice_001",
            )
            print(f"  ✓ 克隆成功: {voice_id}")
        except Exception as e:
            print(f"  ⚠️ 克隆失败: {e}")
            print("  使用系统音色继续")
            voice_id = "Chinese_female_anchor_3"

    # ---- 2. 7 种情绪对比 ----
    print(f"\n=== MiniMax: 情绪控制 (音色: {voice_id}) ===")
    for emotion in client.list_emotions():
        result = client.speak(
            text=text,
            voice_id=voice_id,
            emotion=emotion,
        )
        path = result.save(str(OUTPUT / f"minimax_{emotion}.mp3"))
        print(f"  ✓ {path} ({result.duration:.1f}s, {result.characters}字)")

    # ---- 3. 语速对比 ----
    print("\n=== MiniMax: 语速控制 ===")
    for speed, label in [(0.7, "slow"), (1.0, "normal"), (1.5, "fast")]:
        result = client.speak(text=text, voice_id=voice_id, speed=speed)
        path = result.save(str(OUTPUT / f"minimax_speed_{label}.mp3"))
        print(f"  ✓ {path} (speed={speed}, {result.duration:.1f}s)")

    # ---- 4. 语气词 + 停顿 ----
    print("\n=== MiniMax: 语气词 + 停顿 ===")
    rich_text = MiniMaxTTSClient.format_text_with_pauses([
        ("(sighs)唉，又加班了", 1.5),
        ("(emm)让我想想", 1.0),
        ("算了，明天再说吧", 0.5),
        ("(laughs)反正也习惯了！", 0),
    ])
    result = client.speak(text=rich_text, voice_id=voice_id)
    path = result.save(str(OUTPUT / "minimax_rich_text.mp3"))
    print(f"  ✓ {path} ({result.duration:.1f}s)")

    # ---- 5. 音效修改 ----
    print("\n=== MiniMax: 音效 ===")
    result = client.speak(
        text="你好，这是一段带回声效果的测试。",
        voice_id=voice_id,
        voice_modify={
            "pitch": 0,
            "intensity": 0,
            "timbre": 0,
            "sound_effects": "spacious_echo",
        },
    )
    path = result.save(str(OUTPUT / "minimax_echo.mp3"))
    print(f"  ✓ {path} ({result.duration:.1f}s)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TTS API 使用示例")
    parser.add_argument("--qwen3", action="store_true", help="运行 Qwen3-TTS 演示")
    parser.add_argument("--minimax", action="store_true", help="运行 MiniMax 演示")
    parser.add_argument("--all", action="store_true", help="运行全部演示")
    args = parser.parse_args()

    if not any([args.qwen3, args.minimax, args.all]):
        args.all = True

    ref_audio = None

    if args.qwen3 or args.all:
        ref_audio = demo_qwen3()

    if args.minimax or args.all:
        demo_minimax(ref_audio)

    files = list(OUTPUT.glob("*"))
    print(f"\n{'='*50}")
    print(f"完成！共 {len(files)} 个文件 → {OUTPUT.absolute()}")
    print(f"{'='*50}")
