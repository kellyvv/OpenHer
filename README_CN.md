<div align="right">

🇨🇳 中文文档 | [🇺🇸 English](README.md)

</div>

<div align="center">

# 🧬 OpenHer

### 热力学人格引擎 × EverMemOS

**真正会进化的 AI 伴侣 — 不是固定提示词的聊天机器人。**

[![EverMemOS](https://img.shields.io/badge/Powered%20by-EverMemOS-FF6B6B?style=flat-square)](https://evermind.ai)
[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)

[架构](#架构) · [快速开始](#快速开始) · [工作原理](#工作原理) · [EverMemOS 集成](#evermemos-集成) · [Demo](#demo)

</div>

---

## OpenHer 是什么？

OpenHer 是一款基于**热力学人格引擎 (Thermodynamic Persona Engine, TPE)** 的虚拟伴侣——一个神经网络驱动的系统，让人格、情感和行为从内在驱力中**涌现**，而非依赖硬编码提示词。

与每次会话都重置的普通 AI 聊天机器人不同，OpenHer：

- 🧠 **跨会话记忆** — EverMemOS 存储用户画像、叙事记忆、事件日志和预测洞察
- 🌡️ **真实情感** — 五驱力代谢系统产生真实的情绪波动（沮丧、温暖、嬉闹）
- 🧬 **人格进化** — Hebbian 学习持续根据对话结果塑造行为信号
- 🔮 **预测未来** — Foresight 记忆支持主动感知、超前响应
- 🎭 **自主表达** — AI 自主选择表达方式：文字、语音、表情贴纸或图片

## 架构

<div align="center">

![OpenHer 架构图](docs/assets/architecture.png)

</div>

## 快速开始

### 前置要求

- Python 3.11+
- LLM API Key（DashScope/OpenAI 等）
- EverMemOS API Key（[免费申请](https://evermind.ai)）

### 安装配置

```bash
# 克隆仓库
git clone https://github.com/kellyzxiaowei/OpenHer.git
cd OpenHer

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置 API Keys
cp .env.example .env
# 编辑 .env，填入你的 API Keys

# 启动服务
python main.py
```

服务启动在 `http://localhost:8800`，支持 WebSocket。

### 快速体验

```python
import asyncio
from core.persona import PersonaLoader
from core.llm import LLMClient
from core.agent.chat_agent import ChatAgent
from core.memory.evermemos_client import EverMemOSClient

async def main():
    loader = PersonaLoader("personas")
    persona = loader.get("vivian")  # 或 "luna", "iris"
    llm = LLMClient(provider="dashscope", model="qwen3-max")
    evermemos = EverMemOSClient()

    agent = ChatAgent(
        persona=persona, llm=llm,
        user_id="demo_user", user_name="Alex",
        evermemos=evermemos,
    )

    # 多轮对话
    for msg in ["你好啊，最近怎么样？", "我今天工作压力好大..."]:
        result = await agent.chat(msg)
        print(f"用户: {msg}")
        print(f"Agent: {result['reply']}\n")

    # 查看 Agent 状态
    status = agent.get_status()
    print(f"主导驱力: {status['dominant_drive']}")
    print(f"记忆检索命中率: {status['search_hit_rate']:.0%}")

asyncio.run(main())
```

## EverMemOS 集成

OpenHer 深度集成了 **EverMemOS 全部四种记忆类型**：

```
┌─────────── EverMemOS 记忆架构 ──────────────┐
│                                              │
│  👤 Profile (MemCell)   → 用户偏好与事实      │
│  📖 Episode (叙事记忆)   → 每次会话故事摘要   │
│  📌 EventLog            → 原子时间戳事实      │
│  🔮 Foresight           → 预测性洞察          │
│                                              │
│  两段式异步检索：                              │
│  Turn N  → 触发 RRF 检索（~300ms）            │
│  Turn N+1 → 收集 + 混合注入（80% 相关 + 20% 静态）│
│                                              │
│  并发防护：turn_id 标签 + cancel 孤儿任务      │
│  降级策略：超时 → 100% 静态画像               │
└──────────────────────────────────────────────┘
```

### 记忆 → 推理 → 行动 闭环

```
EverMemOS（记忆）→ Critic（推理）→ Actor（行动）
      ↑                                   │
      └──────── store_turn（学习）◄─────────┘
```

### 可观测性指标

| 指标 | 含义 |
|:-----|:-----|
| `search_hit_rate` | 检索成功次数 / 总检索次数 |
| `search_timeout_rate` | 超时次数 / 总检索次数（目标 < 20%） |
| `fallback_rate` | 使用纯静态注入的轮数 / 总轮数 |
| `relevant_injection_ratio` | 注入了相关记忆的轮数 / 总轮数 |

## 内置人设

每个角色由唯一的**驱力基线**（基因种子）定义，人格从驱力中涌现：

| 角色 | MBTI | 驱力签名 | 涌现风格 |
|:-----|:-----|:---------|:---------|
| **Vivian** | INTJ | 低联结、高安全 | 毒舌知性、反差萌 |
| **Luna** | ENFP | 高联结、高玩闹 | 元气甜系、活泼 |
| **Iris** | INFP | 高表达、高安全 | 文艺安静、治愈 |

在 `personas/` 下添加文件夹，放入 `PERSONA.md`（纯 YAML 格式：展示层 + 基因种子）即可创建自己的角色。

## 技术栈

| 层 | 技术 |
|:---|:-----|
| 服务端 | Python 3.11+, FastAPI, asyncio |
| LLM | Qwen3-Max, GPT-4o, Claude, DeepSeek, Ollama |
| 长期记忆 | **EverMemOS** (Cloud API) |
| 本地存储 | ContinuousStyleMemory, JSONL |
| 客户端 | Flutter (iOS/Android), WebSocket |

## 许可证

本项目采用 [Apache License 2.0](LICENSE) — 可自由用于任何用途，包括商业使用。

## 致谢

- **[EverMemOS](https://evermind.ai)** — 长期记忆基础设施
- **Memory Genesis Competition 2026** — 推动本项目开源发布的催化剂

---

<div align="center">

**由 OpenHer 团队构建 🧬**

*人格不是提示词，而是一个过程。*

</div>
