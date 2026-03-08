"""
PersonaStore — 动态生成 + 锁定 + 持久化

核心流程:
  1. generate() → LLM 生成人设 + Qwen3 生成声音 + Image AI 生成头像
  2. lock()     → 锁定选中的角色，上传 MiniMax 克隆，持久化
  3. get()      → 获取已锁定的角色

所有角色数据存储在 personas/{persona_id}/ 目录下。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List


@dataclass
class VoiceProfile:
    """角色声音配置"""
    design_description: str = ""        # Qwen3 voice_design 描述
    ref_audio_path: str = ""            # 生成的参考音频路径
    ref_text: str = ""                  # 参考音频对应的文本
    minimax_voice_id: str = ""          # MiniMax 克隆后的 voice_id
    qwen3_speaker: str = ""             # Qwen3 内置音色 (如用内置)
    provider: str = "minimax"           # 日常 TTS 提供者


@dataclass
class AvatarProfile:
    """角色头像配置"""
    prompt: str = ""                    # 生成 prompt
    path: str = ""                      # 头像文件路径
    style: str = "realistic"            # 风格


@dataclass
class PersonaProfile:
    """
    动态生成的角色配置

    与旧版 Persona 的区别:
    - 不依赖静态 PERSONA.md 文件
    - 由 LLM+SKILL 动态生成
    - 锁定后持久化为 JSON
    """
    id: str = ""
    gender: str = "female"              # "female" | "male"
    name: str = ""
    age: int = 0
    personality: str = ""               # 性格描述
    speaking_style: str = ""            # 说话风格
    tags: List[str] = field(default_factory=list)
    backstory: str = ""                 # 背景故事
    voice: VoiceProfile = field(default_factory=VoiceProfile)
    avatar: AvatarProfile = field(default_factory=AvatarProfile)
    locked: bool = False
    created_at: float = 0.0
    locked_at: float = 0.0

    def build_system_prompt(self) -> str:
        """构建注入 System Prompt 的人设部分"""
        lines = [
            f"# 你的身份：{self.name}",
            f"- 性别：{'女' if self.gender == 'female' else '男'}",
            f"- 年龄：{self.age}岁",
            f"- 性格特点：{self.personality}",
            f"- 说话风格：{self.speaking_style}",
        ]
        if self.tags:
            lines.append(f"- 标签：{', '.join(self.tags)}")
        if self.backstory:
            lines.append(f"\n## 背景故事\n{self.backstory}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PersonaProfile":
        voice_data = data.pop("voice", {})
        avatar_data = data.pop("avatar", {})
        profile = cls(**data)
        profile.voice = VoiceProfile(**voice_data) if voice_data else VoiceProfile()
        profile.avatar = AvatarProfile(**avatar_data) if avatar_data else AvatarProfile()
        return profile


class PersonaStore:
    """
    角色存储和管理

    目录结构:
        personas/
        ├── {persona_id}/
        │   ├── profile.json        # 人设数据
        │   ├── voice_ref.wav       # 参考音频
        │   └── avatar.png          # 头像
    """

    PROFILE_FILE = "profile.json"

    def __init__(self, personas_dir: str):
        self.personas_dir = Path(personas_dir)
        self.personas_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, PersonaProfile] = {}

    def generate_id(self) -> str:
        """生成唯一角色 ID"""
        return str(uuid.uuid4())[:8]

    def get_persona_dir(self, persona_id: str) -> Path:
        """获取角色目录"""
        return self.personas_dir / persona_id

    def save(self, profile: PersonaProfile) -> str:
        """
        保存角色到磁盘

        Returns:
            保存的 profile.json 路径
        """
        persona_dir = self.get_persona_dir(profile.id)
        persona_dir.mkdir(parents=True, exist_ok=True)

        path = persona_dir / self.PROFILE_FILE
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)

        self._cache[profile.id] = profile
        return str(path)

    def load(self, persona_id: str) -> Optional[PersonaProfile]:
        """从磁盘加载角色"""
        if persona_id in self._cache:
            return self._cache[persona_id]

        path = self.get_persona_dir(persona_id) / self.PROFILE_FILE
        if not path.exists():
            return None

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        profile = PersonaProfile.from_dict(data)
        self._cache[persona_id] = profile
        return profile

    def get_locked(self) -> Optional[PersonaProfile]:
        """获取当前已锁定的角色 (唯一)"""
        for pid in self.list_ids():
            profile = self.load(pid)
            if profile and profile.locked:
                return profile
        return None

    def lock(self, persona_id: str) -> PersonaProfile:
        """
        锁定角色

        - 标记 locked=True
        - 后续应调用 MiniMax clone_voice 上传音频
        """
        profile = self.load(persona_id)
        if not profile:
            raise ValueError(f"角色不存在: {persona_id}")

        # 解锁其他角色
        for pid in self.list_ids():
            other = self.load(pid)
            if other and other.locked and other.id != persona_id:
                other.locked = False
                self.save(other)

        profile.locked = True
        profile.locked_at = time.time()
        self.save(profile)
        return profile

    def list_ids(self) -> List[str]:
        """列出所有角色 ID"""
        ids = []
        for d in self.personas_dir.iterdir():
            if d.is_dir() and (d / self.PROFILE_FILE).exists():
                ids.append(d.name)
        return sorted(ids)

    def list_all(self) -> List[PersonaProfile]:
        """列出所有角色"""
        return [self.load(pid) for pid in self.list_ids() if self.load(pid)]

    def delete(self, persona_id: str):
        """删除角色"""
        import shutil
        persona_dir = self.get_persona_dir(persona_id)
        if persona_dir.exists():
            shutil.rmtree(persona_dir)
        self._cache.pop(persona_id, None)
