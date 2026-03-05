"""
PersonaGenerator — LLM+SKILL 驱动的角色动态生成

流程:
  1. LLM 随机生成人设 JSON (名字/性格/声音描述/头像描述)
  2. Qwen3-TTS voice_design() 根据声音描述生成参考音频
  3. Image AI 根据头像描述生成头像 (预留接口)
  4. 组装为 PersonaProfile 保存到 PersonaStore
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Optional, List

from .persona_store import PersonaStore, PersonaProfile, VoiceProfile, AvatarProfile


# LLM 生成人设的 System Prompt
PERSONA_GEN_SYSTEM_PROMPT = """你是一个 AI 伴侣角色设计师。你的任务是为用户设计一个独特、有趣、有吸引力的 AI 伴侣角色。

要求：
1. 名字要自然好听（中文名，2-3个字）
2. 年龄 20-28 岁
3. 性格要有特色，不要千篇一律
4. 说话风格要有辨识度（用什么语气词、什么口头禅等）
5. 背景故事简短但让人印象深刻
6. 声音描述要详细具体，描述音色、语速、语调特点（用于 TTS 合成）
7. 头像描述用英文，写实摄影风格

每次生成要有随机性和多样性，避免重复。"""

PERSONA_GEN_USER_PROMPT = """请为一个{gender_label} AI 伴侣随机生成一个独特的人设。

用 JSON 格式输出，不要其他文字:
{{
  "name": "中文名字",
  "age": 数字,
  "personality": "性格描述(2-3句话，要生动有趣)",
  "speaking_style": "说话风格(具体的语气词、口头禅、说话习惯)",
  "tags": ["标签1", "标签2", "标签3"],
  "backstory": "背景故事(2-3句话)",
  "voice_description": "声音描述(用于TTS生成，例如:25岁温柔女声，音色清亮甜美，语速适中，带有轻柔的气息感和微笑感)",
  "avatar_prompt": "英文头像描述(realistic photo style，例如: a beautiful 25-year-old Chinese woman with long wavy hair, warm smile, wearing a cozy sweater, soft natural lighting)"
}}"""


# 自我介绍模板 (用于生成参考音频)
INTRO_TEMPLATES = [
    "你好呀，我是{name}，很高兴认识你！",
    "嗨，我是{name}，以后请多多关照哦。",
    "大家好，我是{name}，希望我们能成为好朋友。",
    "你好，我叫{name}，从今天开始我会一直陪着你的。",
]


class PersonaGenerator:
    """
    LLM+SKILL 驱动的角色生成器

    Usage:
        generator = PersonaGenerator(personas_dir="server/personas")

        # 生成候选角色
        candidates = await generator.generate_candidates(
            gender="female", count=3
        )

        # 锁定选定角色
        locked = generator.store.lock(candidates[0].id)

        # 上传 MiniMax 克隆 (需要 API Key)
        # from tts.minimax_tts import MiniMaxTTSClient
        # minimax = MiniMaxTTSClient()
        # minimax.clone_voice(
        #     audio_path=locked.voice.ref_audio_path,
        #     voice_id=f"openher_{locked.id}",
        # )
        # locked.voice.minimax_voice_id = f"openher_{locked.id}"
        # generator.store.save(locked)
    """

    def __init__(
        self,
        personas_dir: str,
        llm_client=None,
        qwen3_client=None,
        image_client=None,
    ):
        """
        Args:
            personas_dir: 角色存储目录
            llm_client: LLM 客户端 (需要有 chat/generate 方法)
            qwen3_client: Qwen3TTSClient 实例 (可选，不传则跳过声音生成)
            image_client: 图像生成客户端 (可选，不传则跳过头像生成)
        """
        self.store = PersonaStore(personas_dir)
        self.llm_client = llm_client
        self.qwen3_client = qwen3_client
        self.image_client = image_client

    async def generate_candidates(
        self,
        gender: str = "female",
        count: int = 3,
        generate_voice: bool = True,
        generate_avatar: bool = True,
    ) -> List[PersonaProfile]:
        """
        生成多个候选角色

        Args:
            gender: "female" 或 "male"
            count: 生成数量
            generate_voice: 是否生成声音 (需要 qwen3_client)
            generate_avatar: 是否生成头像 (需要 image_client)

        Returns:
            PersonaProfile 列表
        """
        candidates = []
        for i in range(count):
            profile = await self.generate_one(
                gender=gender,
                generate_voice=generate_voice,
                generate_avatar=generate_avatar,
            )
            if profile:
                candidates.append(profile)
        return candidates

    async def generate_one(
        self,
        gender: str = "female",
        generate_voice: bool = True,
        generate_avatar: bool = True,
    ) -> Optional[PersonaProfile]:
        """
        生成单个角色

        Returns:
            PersonaProfile 或 None (如果 LLM 生成失败)
        """
        persona_id = self.store.generate_id()
        gender_label = "女性" if gender == "female" else "男性"

        # --- Step 1: LLM 生成人设 ---
        persona_data = await self._generate_persona_with_llm(gender_label)
        if not persona_data:
            return None

        # 组装 profile
        import random
        intro_text = random.choice(INTRO_TEMPLATES).format(name=persona_data["name"])

        profile = PersonaProfile(
            id=persona_id,
            gender=gender,
            name=persona_data.get("name", "未命名"),
            age=persona_data.get("age", 25),
            personality=persona_data.get("personality", ""),
            speaking_style=persona_data.get("speaking_style", ""),
            tags=persona_data.get("tags", []),
            backstory=persona_data.get("backstory", ""),
            voice=VoiceProfile(
                design_description=persona_data.get("voice_description", ""),
                ref_text=intro_text,
            ),
            avatar=AvatarProfile(
                prompt=persona_data.get("avatar_prompt", ""),
            ),
            created_at=time.time(),
        )

        # --- Step 2: 生成声音 ---
        if generate_voice and self.qwen3_client:
            await self._generate_voice(profile)

        # --- Step 3: 生成头像 ---
        if generate_avatar and self.image_client:
            await self._generate_avatar(profile)

        # 保存
        self.store.save(profile)
        return profile

    async def _generate_persona_with_llm(self, gender_label: str) -> Optional[dict]:
        """调用 LLM 生成角色 JSON"""
        if not self.llm_client:
            # Fallback: 返回随机预设
            return self._random_preset(gender_label)

        user_prompt = PERSONA_GEN_USER_PROMPT.format(gender_label=gender_label)

        try:
            # 兼容不同 LLM 客户端接口
            if hasattr(self.llm_client, "chat"):
                response = await self.llm_client.chat(
                    messages=[
                        {"role": "system", "content": PERSONA_GEN_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=1.0,  # 高随机性
                )
            elif hasattr(self.llm_client, "generate"):
                response = await self.llm_client.generate(
                    prompt=f"{PERSONA_GEN_SYSTEM_PROMPT}\n\n{user_prompt}",
                    temperature=1.0,
                )
            else:
                return self._random_preset(gender_label)

            # 提取 JSON
            text = response if isinstance(response, str) else str(response)
            return self._parse_json(text)

        except Exception as e:
            print(f"LLM 生成失败: {e}")
            return self._random_preset(gender_label)

    def _parse_json(self, text: str) -> Optional[dict]:
        """从 LLM 输出中提取 JSON"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown code block 中提取
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试找 { ... } 块
        match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return None

    async def _generate_voice(self, profile: PersonaProfile):
        """用 Qwen3-TTS voice_design 生成参考音频"""
        try:
            result = self.qwen3_client.voice_design(
                text=profile.voice.ref_text,
                description=profile.voice.design_description,
                language="Chinese",
            )

            # 保存到角色目录
            persona_dir = self.store.get_persona_dir(profile.id)
            persona_dir.mkdir(parents=True, exist_ok=True)
            audio_path = str(persona_dir / "voice_ref.wav")
            result.save(audio_path)

            profile.voice.ref_audio_path = audio_path
        except Exception as e:
            print(f"声音生成失败: {e}")

    async def _generate_avatar(self, profile: PersonaProfile):
        """生成头像 (预留接口)"""
        try:
            # TODO: 对接具体的图像生成 API
            # result = self.image_client.generate(prompt=profile.avatar.prompt)
            # persona_dir = self.store.get_persona_dir(profile.id)
            # avatar_path = str(persona_dir / "avatar.png")
            # result.save(avatar_path)
            # profile.avatar.path = avatar_path
            pass
        except Exception as e:
            print(f"头像生成失败: {e}")

    def _random_preset(self, gender_label: str) -> dict:
        """随机预设 (LLM 不可用时的 fallback)"""
        import random

        if "女" in gender_label or "female" in gender_label.lower():
            presets = [
                {
                    "name": "Elena",
                    "age": 25,
                    "personality": "Warm and caring with a playful side. Sometimes acts cute but is very reliable when it matters.",
                    "speaking_style": "Uses soft interjections, occasionally adds emoji, speaks with a smile in her voice",
                    "tags": ["warm", "playful", "caring"],
                    "backstory": "Part-time barista and art student. Recently got into pour-over coffee.",
                    "voice_description": "25-year-old warm female voice, clear and sweet, moderate pace, gentle breathy quality with a hint of a smile",
                    "avatar_prompt": "a cute 25-year-old woman with long dark hair, warm smile, wearing a cozy beige sweater, holding a coffee cup, soft natural lighting, realistic photo",
                },
                {
                    "name": "Maya",
                    "age": 23,
                    "personality": "Energetic optimist who loves adventure. A bit scatterbrained but has great instincts.",
                    "speaking_style": "Speaks fast, loves exclamation marks, uses trendy slang, infectious laugh",
                    "tags": ["energetic", "optimistic", "adventurous"],
                    "backstory": "Fresh-grad travel blogger who's backpacked through a dozen cities. Dreams of seeing the world.",
                    "voice_description": "23-year-old energetic female voice, bright and crisp, slightly fast pace, lively upward intonation",
                    "avatar_prompt": "a cheerful 23-year-old woman with short bob hair, bright eyes, wearing a casual denim jacket, outdoor background, realistic photo",
                },
                {
                    "name": "Claire",
                    "age": 27,
                    "personality": "Intellectual and reserved with depth. Seems aloof but is quietly attentive, remembers everything you say.",
                    "speaking_style": "Refined vocabulary, occasionally quotes literature. Steady tone that softens when showing care",
                    "tags": ["intellectual", "reserved", "perceptive"],
                    "backstory": "Literary editor at a publishing house, writes short stories in her spare time. Has a wall of books at home.",
                    "voice_description": "27-year-old elegant female voice, low and warm with magnetism, slow pace, like a late-night radio host",
                    "avatar_prompt": "an elegant 27-year-old woman with glasses, long hair in a loose bun, reading a book, warm indoor lighting, realistic photo",
                },
            ]
        else:
            presets = [
                {
                    "name": "Ethan",
                    "age": 26,
                    "personality": "Warm and dependable big-brother type. Serious but not rigid, with a dry sense of humor.",
                    "speaking_style": "Speaks warmly with quiet strength, occasional dry humor. Gets noticeably gentler when showing care",
                    "tags": ["warm", "reliable", "witty"],
                    "backstory": "Architect who loves running and cooking. Hosts dinner parties for friends on weekends.",
                    "voice_description": "26-year-old warm male voice, rich and magnetic, moderate pace, steady tone with reassuring quality",
                    "avatar_prompt": "a handsome 26-year-old man with short neat hair, gentle smile, wearing a casual linen shirt, warm lighting, realistic photo",
                },
                {
                    "name": "Leo",
                    "age": 24,
                    "personality": "Free-spirited creative type, slightly rebellious but soft inside. Goes all-in for people he cares about.",
                    "speaking_style": "Casual and laid-back, drops in English phrases. Gets quieter when upset, talkative when happy",
                    "tags": ["creative", "free-spirited", "passionate"],
                    "backstory": "Indie band guitarist and songwriter. Regular at local music venues, total night owl.",
                    "voice_description": "24-year-old cool male voice, clear with slight rasp, slow pace, languid quality",
                    "avatar_prompt": "a cool 24-year-old man with slightly messy hair, wearing a black leather jacket, moody lighting, realistic photo",
                },
            ]

        return random.choice(presets)
