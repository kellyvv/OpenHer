---
name: persona-generator
description: 随机生成 AI 伴侣角色，包括人设、声音和头像
---

# 角色生成 SKILL

## 功能
根据用户选择的性别 (HER/HE)，随机生成一个完整的 AI 伴侣角色。

## 生成维度
1. **人设** — LLM 随机生成 (名字/年龄/性格/说话风格/背景故事)
2. **声音** — Qwen3-TTS voice_design() 根据人设描述生成
3. **头像** — Image AI 根据人设描述生成

## 输出
一个 PersonaProfile 对象，包含:
- id: 唯一标识
- gender: 性别
- name: 名字
- age: 年龄
- personality: 性格描述
- speaking_style: 说话风格
- tags: 标签列表
- backstory: 背景故事
- voice: {design_description, ref_audio_path}
- avatar: {prompt, path}

## 调用方式
```python
from server.core.persona.persona_generator import PersonaGenerator

generator = PersonaGenerator(
    personas_dir="server/personas",
    qwen3_tts_client=qwen3_client,  # 可选，不传则跳过声音生成
)

# 生成 3 个候选
candidates = await generator.generate_candidates(gender="female", count=3)

# 用户选择后锁定
generator.store.lock(candidates[0].id)
```

## LLM Prompt 模板
系统会用以下 prompt 让 LLM 生成随机人设:

```
你是一个 AI 伴侣角色设计师。请为一个 {gender} AI 伴侣随机生成一个独特的人设。

要求：
1. 名字要自然好听（中文名）
2. 年龄 20-30 岁之间
3. 性格要有特色，不要太老套
4. 说话风格要有辨识度
5. 背景故事简短但有趣
6. 声音描述要具体到音色、语速、语调特点

请用 JSON 格式输出：
{
  "name": "名字",
  "age": 数字,
  "personality": "性格描述(2-3句话)",
  "speaking_style": "说话风格描述",
  "tags": ["标签1", "标签2", "标签3"],
  "backstory": "背景故事(2-3句话)",
  "voice_description": "声音描述(用于 TTS 生成)",
  "avatar_prompt": "头像描述(用于图像生成，英文)"
}
```
