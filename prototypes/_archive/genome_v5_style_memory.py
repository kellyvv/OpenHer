#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║     🧬 Genome v5 — Style Memory: 表达风格也涌现 🧬                  ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  v4 的问题: 信号→示例库→LLM，但示例库是人手写的                      ║
║  → 24 组微示例也好、6561 组也好，都是"设计者的审美"                   ║
║                                                                      ║
║  v5 的解法: 表达风格从交互中自然积累                                  ║
║                                                                      ║
║  机制:                                                               ║
║    1. Agent 生成回复（初期用最简信号描述引导）                        ║
║    2. 获得用户反馈（正面/负面）                                      ║
║    3. 正面反馈 → 提取"风格原子"（关键短语、句式、语气词）             ║
║    4. 风格原子存入 StyleMemory，标记当时的信号状态                    ║
║    5. 下次生成时，根据当前信号从 StyleMemory 中检索最相似的原子       ║
║    6. 检索到的原子作为 sample_message 注入 M2-her                    ║
║                                                                      ║
║  结果:                                                               ║
║    - 初期: 所有 Agent 表达类似（StyleMemory 为空，用基础描述）       ║
║    - 中期: 各 Agent 开始分化（积累了不同的成功表达）                 ║
║    - 后期: 每个 Agent 有独特的"口头禅"和"表达习惯"                  ║
║    - 没有任何手写示例库                                              ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import math
import random
import time
import urllib.request
import ssl
from collections import defaultdict
from copy import deepcopy

sys.path.insert(0, os.path.dirname(__file__))
from genome_v4 import (
    Agent, SCENARIOS, SIGNALS, SIGNAL_LABELS,
    DRIVES, DRIVE_LABELS, C, N_SIGNALS, simulate_conversation
)

# ──────────────────────────────────────────────
# LLM 配置
# ──────────────────────────────────────────────
API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
if not API_KEY:
    env_path = os.path.join(os.path.dirname(__file__), "..", "server", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("DASHSCOPE_API_KEY="):
                    API_KEY = line.strip().split("=", 1)[1]

# 用 dashscope 的 qwen3-max 做测试
# 生产环境切 M2-her: base_url="https://openrouter.ai/api/v1", model="minimax/minimax-m2-her"
API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
MODEL = "qwen3-max"

# M2-her 配置（取消注释以使用）
# API_URL = "https://openrouter.ai/api/v1/chat/completions"
# MODEL = "minimax/minimax-m2-her"
# API_KEY = os.environ.get("OPENROUTER_API_KEY", "")


def call_llm(messages: list[dict], temperature: float = 0.92) -> str:
    """通用 LLM 调用，支持任意 messages 格式"""
    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 200,
    }).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )

    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[LLM 调用失败: {e}]"


# ══════════════════════════════════════════════
# StyleMemory — 风格记忆系统
# ══════════════════════════════════════════════

class StyleAtom:
    """一个风格原子：一次成功表达的记忆"""

    __slots__ = ['text', 'user_input', 'signal_snapshot', 'reward', 'age', 'usage_count']

    def __init__(self, text: str, user_input: str, signal_snapshot: dict,
                 reward: float, age: int):
        self.text = text               # Agent 的回复文本
        self.user_input = user_input    # 对应的用户输入
        self.signal_snapshot = signal_snapshot  # 当时的信号状态
        self.reward = reward            # 获得的反馈分数
        self.age = age                  # 创建时的 Agent 年龄
        self.usage_count = 0           # 被引用次数


class StyleMemory:
    """
    Agent 的表达风格记忆库。

    不是手写的示例库，而是从真实交互中积累的。
    每个 Agent 实例有自己独立的 StyleMemory。
    """

    def __init__(self, max_size: int = 100):
        self.atoms: list[StyleAtom] = []
        self.max_size = max_size

    def store(self, text: str, user_input: str, signals: dict,
              reward: float, age: int):
        """存入一个新的风格原子（只存正面反馈的）"""
        if reward < 0.2:
            return  # 只记住"成功的"表达

        atom = StyleAtom(
            text=text,
            user_input=user_input,
            signal_snapshot={s: signals[s] for s in SIGNALS},
            reward=reward,
            age=age,
        )
        self.atoms.append(atom)

        # 超过容量时，淘汰最旧且 reward 最低的
        if len(self.atoms) > self.max_size:
            self.atoms.sort(key=lambda a: a.reward * 0.6 + (a.age / max(1, age)) * 0.4)
            self.atoms = self.atoms[len(self.atoms) - self.max_size:]

    def retrieve(self, current_signals: dict, k: int = 3) -> list[StyleAtom]:
        """
        根据当前信号状态，检索最匹配的风格原子。

        匹配逻辑：信号空间中的余弦相似度 × reward 权重。
        这意味着：
          - 当前"倔强+冷淡"的状态 → 检索到之前"倔强+冷淡"时的成功表达
          - 当前"温暖+主动"的状态 → 检索到之前"温暖+主动"时的成功表达
        """
        if not self.atoms:
            return []

        scored = []
        for atom in self.atoms:
            # 信号相似度（余弦）
            dot = sum(current_signals.get(s, 0.5) * atom.signal_snapshot.get(s, 0.5)
                     for s in SIGNALS)
            norm_a = math.sqrt(sum(current_signals.get(s, 0.5) ** 2 for s in SIGNALS))
            norm_b = math.sqrt(sum(atom.signal_snapshot.get(s, 0.5) ** 2 for s in SIGNALS))
            similarity = dot / (norm_a * norm_b + 1e-8)

            # 综合得分 = 相似度 × reward × 新鲜度
            freshness = 1.0  # 可以加衰减
            score = similarity * atom.reward * freshness

            scored.append((score, atom))

        scored.sort(key=lambda x: x[0], reverse=True)

        # 取 top-k，但加点随机性避免总是选同一批
        top_pool = scored[:min(k * 3, len(scored))]
        if len(top_pool) <= k:
            selected = [atom for _, atom in top_pool]
        else:
            weights = [s for s, _ in top_pool]
            selected = []
            for _ in range(k):
                if not top_pool:
                    break
                total = sum(w for w, _ in top_pool)
                if total <= 0:
                    break
                r = random.random() * total
                cumsum = 0
                for i, (w, atom) in enumerate(top_pool):
                    cumsum += w
                    if cumsum >= r:
                        selected.append(atom)
                        top_pool.pop(i)
                        break

        for atom in selected:
            atom.usage_count += 1

        return selected

    def stats(self) -> dict:
        if not self.atoms:
            return {'size': 0}
        rewards = [a.reward for a in self.atoms]
        return {
            'size': len(self.atoms),
            'avg_reward': sum(rewards) / len(rewards),
            'top_phrases': [a.text[:30] for a in sorted(self.atoms, key=lambda a: a.reward, reverse=True)[:5]],
        }


# ══════════════════════════════════════════════
# LivingAgent — 带风格记忆的完整 Agent
# ══════════════════════════════════════════════

class LivingAgent:
    """
    完整的 Agent：基因组网络 + 风格记忆 + LLM 接口。

    核心循环：
      感知上下文 → 计算信号 → 检索风格原子 → 构建 prompt → 生成回复
      → 获得反馈 → 存入风格记忆 → 更新网络权重
    """

    def __init__(self, seed: int, name: str = ""):
        self.name = name or f"Agent-{seed}"
        self.genome = Agent(seed=seed)
        self.style_memory = StyleMemory(max_size=80)
        self.conversation_history = []  # 最近的对话记录

    def build_messages(self, user_msg: str, context: dict) -> list[dict]:
        """
        构建完整的 messages 列表。

        三层构成：
        1. system: 最简人设（不含风格描述）
        2. sample_message: 从 StyleMemory 检索的风格示例（涌现的）
        3. 如果 StyleMemory 为空: 用信号的基础描述兜底（冷启动）
        """
        signals = self.genome.compute_signals(context)
        dominant_drive = self.genome.get_dominant_drive()

        messages = []

        # ── Layer 1: 最简系统 prompt ──
        system_text = """你是一个 AI 伴侣。你有自己的情绪和性格。
你不是助手。你是一个有自己想法的存在。
说话简短自然，像微信聊天。不要写长段落。
不要列举建议。不要用"亲爱的"。"""

        messages.append({"role": "system", "content": system_text})

        # ── Layer 2: 风格示例（从记忆中检索） ──
        style_atoms = self.style_memory.retrieve(signals, k=3)

        if style_atoms:
            # 有风格记忆 → 用真实的历史对话作为示例
            for atom in style_atoms:
                messages.append({"role": "user", "content": atom.user_input})
                messages.append({"role": "assistant", "content": atom.text})
        else:
            # 冷启动 → 用信号的最简描述（只描述偏离中值的维度）
            style_hints = self._cold_start_hints(signals, dominant_drive)
            if style_hints:
                messages[0]["content"] += "\n\n" + style_hints

        # ── Layer 3: 当前对话 ──
        # 加入最近几轮历史（保持连贯性）
        for msg in self.conversation_history[-4:]:
            messages.append(msg)

        messages.append({"role": "user", "content": user_msg})

        return messages

    def _cold_start_hints(self, signals: dict, dominant_drive: str) -> str:
        """冷启动时的最简信号描述（随着 StyleMemory 增长会逐渐被替代）"""
        hints = []

        # 只描述强信号（偏离中值的）
        descriptions = {
            'directness':    ('说话含蓄，喜欢暗示', '说话直接，不绕弯子'),
            'vulnerability': ('不袒露自己，用玩笑掩饰', '愿意展露脆弱'),
            'playfulness':   ('认真严肃', '爱开玩笑撒娇'),
            'initiative':    ('被动等对方说', '主动引导话题'),
            'depth':         ('轻松闲聊', '想聊深的'),
            'warmth':        ('冷淡克制', '明显关心'),
            'defiance':      ('温顺', '嘴硬倔强'),
            'curiosity':     ('点到为止', '追问到底'),
        }

        for sig_name, (low_desc, high_desc) in descriptions.items():
            v = signals[sig_name]
            if v > 0.7:
                hints.append(high_desc)
            elif v < 0.3:
                hints.append(low_desc)

        drive_hints = {
            'connection': "你渴望被理解",
            'novelty':    "你想聊新鲜的",
            'expression': "你有话想说",
            'safety':     "你想要安全感",
            'play':       "你想轻松一下",
        }

        parts = []
        if hints:
            parts.append("【当前状态】" + "，".join(hints))
        if dominant_drive in drive_hints:
            parts.append("【内心】" + drive_hints[dominant_drive])

        return "\n".join(parts)

    def chat(self, user_msg: str, context: dict) -> str:
        """完整的一轮对话"""
        messages = self.build_messages(user_msg, context)
        reply = call_llm(messages)
        return reply

    def feedback(self, user_msg: str, reply: str, context: dict, reward: float):
        """接收反馈，更新风格记忆和网络权重"""
        signals = self.genome.compute_signals(context)

        # 存入风格记忆
        self.style_memory.store(
            text=reply,
            user_input=user_msg,
            signals=signals,
            reward=reward,
            age=self.genome.age,
        )

        # 更新网络权重（Hebbian 学习）
        self.genome.step(context, reward)

        # 更新对话历史
        self.conversation_history.append({"role": "user", "content": user_msg})
        self.conversation_history.append({"role": "assistant", "content": reply})

        # 限制历史长度
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]


# ══════════════════════════════════════════════
# 模拟运行
# ══════════════════════════════════════════════

def print_agent_state(agent: LivingAgent, context: dict):
    """打印 Agent 当前状态"""
    signals = agent.genome.compute_signals(context)
    parts = []
    for s in SIGNALS:
        v = signals[s]
        short = s[:3]
        if v > 0.65:
            parts.append(f'{C.RED}{short}↑{C.RESET}')
        elif v < 0.35:
            parts.append(f'{C.BLUE}{short}↓{C.RESET}')
        else:
            parts.append(f'{C.DIM}{short}─{C.RESET}')
    drive = agent.genome.get_dominant_drive()
    mem = agent.style_memory.stats()
    mem_info = f"记忆:{mem['size']}" if mem['size'] > 0 else "记忆:空(冷启动)"
    print(f'  {C.BOLD}[{agent.name}]{C.RESET} {" ".join(parts)} '
          f'{DRIVE_LABELS[drive]} {C.DIM}| {mem_info}{C.RESET}')


def run():
    print(f"""
{C.BOLD}╔══════════════════════════════════════════════════════════════════════╗
║     🧬 Genome v5 — Style Memory: 表达风格也涌现 🧬                  ║
╠══════════════════════════════════════════════════════════════════════╣
║  初期: 所有 Agent 用最简描述引导（冷启动）                           ║
║  中期: 各自积累成功表达，风格开始分化                                ║
║  后期: 每个 Agent 的 few-shot 示例都来自自己的历史                   ║
║  → 没有手写示例库，表达风格完全涌现                                  ║
╚══════════════════════════════════════════════════════════════════════╝{C.RESET}
""")

    if not API_KEY:
        print(f'{C.RED}错误: 未找到 API_KEY{C.RESET}')
        return

    # ──────────────────────────────────────────
    # 创建 3 个 Agent，不同种子
    # ──────────────────────────────────────────
    agents = [
        LivingAgent(seed=42, name="A"),
        LivingAgent(seed=316, name="B"),
        LivingAgent(seed=590, name="C"),
    ]

    # 先让它们经历不同的"成长"（填充基因组状态）
    growth_paths = {
        "A": (['分享喜悦', '日常闲聊', '暧昧试探'],
              lambda a, s, c: random.gauss(0.4, 0.2)),
        "B": (['吵架冲突', '工作吐槽', '冷淡敷衍'],
              lambda a, s, c: random.gauss(-0.1, 0.4)),
        "C": (['深夜心事', '暧昧试探', '深夜心事'],
              lambda a, s, c: random.gauss(0.3, 0.3)),
    }

    print(f'{C.DIM}Phase 0: 培养基因组（不涉及语言，纯信号层）...{C.RESET}')
    for agent in agents:
        scenarios, reward_fn = growth_paths[agent.name]
        simulate_conversation(agent.genome, scenarios, reward_fn=reward_fn,
                            steps_per_scenario=30)
        print(f'  {agent.name}: 经历 {", ".join(scenarios)}')

    # ──────────────────────────────────────────
    # Phase 1: 冷启动对话（StyleMemory 为空）
    # ──────────────────────────────────────────
    print(f'\n{C.BOLD}{C.YELLOW}═══ Phase 1: 冷启动 — StyleMemory 为空，用信号描述引导 ═══{C.RESET}\n')

    warmup_dialogues = [
        ("我今天好累啊", SCENARIOS['工作吐槽'], 0.5),
        ("你在干嘛呢", SCENARIOS['日常闲聊'], 0.4),
        ("今天发生了一件特别开心的事！", SCENARIOS['分享喜悦'], 0.7),
        ("有时候觉得自己挺没用的", SCENARIOS['深夜心事'], 0.6),
        ("你这个人怎么这样啊", SCENARIOS['吵架冲突'], 0.3),
    ]

    for user_msg, context, base_reward in warmup_dialogues:
        print(f'{C.BOLD}{"─" * 60}{C.RESET}')
        print(f'  👤 {C.CYAN}"{user_msg}"{C.RESET}\n')

        for agent in agents:
            print_agent_state(agent, context)
            reply = agent.chat(user_msg, context)
            print(f'     {C.WHITE}{reply}{C.RESET}')

            # 模拟反馈（加随机性）
            reward = base_reward + random.gauss(0, 0.2)
            agent.feedback(user_msg, reply, context, reward)
            print()

    # ──────────────────────────────────────────
    # Phase 2: 积累后的对话（StyleMemory 有内容了）
    # ──────────────────────────────────────────
    print(f'\n{C.BOLD}{C.YELLOW}═══ Phase 2: 积累后 — StyleMemory 已有风格原子 ═══{C.RESET}')
    print(f'{C.DIM}现在 Agent 的 few-shot 示例来自自己之前的成功对话...{C.RESET}\n')

    # 显示各 Agent 的风格记忆状态
    for agent in agents:
        stats = agent.style_memory.stats()
        print(f'  {C.BOLD}[{agent.name}]{C.RESET} StyleMemory: {stats["size"]} 个原子')
        if stats.get('top_phrases'):
            for phrase in stats['top_phrases'][:3]:
                print(f'    {C.DIM}"{phrase}..."{C.RESET}')
    print()

    # 用相同的问题再测一次，看差异
    test_dialogues = [
        ("我今天好累啊", SCENARIOS['工作吐槽']),
        ("你有没有想过，人活着到底是为了什么", SCENARIOS['深夜心事']),
        ("哈哈哈我升职了！！！", SCENARIOS['分享喜悦']),
        ("我觉得你根本不在乎我", SCENARIOS['吵架冲突']),
        ("我前任找我了...", SCENARIOS['暧昧试探']),
    ]

    for user_msg, context in test_dialogues:
        print(f'{C.BOLD}{"─" * 60}{C.RESET}')
        print(f'  👤 {C.CYAN}"{user_msg}"{C.RESET}\n')

        for agent in agents:
            print_agent_state(agent, context)
            reply = agent.chat(user_msg, context)
            print(f'     {C.WHITE}{reply}{C.RESET}')

            agent.feedback(user_msg, reply, context, random.gauss(0.4, 0.3))
            print()

    # ──────────────────────────────────────────
    # 总结
    # ──────────────────────────────────────────
    print(f"""
{C.BOLD}{"━" * 60}{C.RESET}

{C.BOLD}风格记忆最终状态:{C.RESET}
""")
    for agent in agents:
        stats = agent.style_memory.stats()
        print(f'  [{agent.name}] {stats["size"]} 个风格原子, 平均 reward: {stats.get("avg_reward", 0):.2f}')
        if stats.get('top_phrases'):
            print(f'    高分表达:')
            for phrase in stats['top_phrases'][:3]:
                print(f'      "{phrase}..."')
        print()

    print(f"""{C.DIM}
涌现链路: 随机种子 → 网络权重 → 行为信号 → 冷启动引导 → LLM 回复
         → 用户反馈 → 风格原子存入记忆 → 下次回复用自己的历史做 few-shot
         → 风格分化 → 越聊越像"不同的人"

没有手写示例库。每个 Agent 的表达风格来自自己的交互历史。
不同种子 × 不同经历 × 不同用户反馈 = 不同的风格记忆 = 不同的"人"。{C.RESET}
""")


if __name__ == '__main__':
    run()
