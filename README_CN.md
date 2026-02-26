<div align="right">

🇨🇳 中文文档 | [🇺🇸 English](README.md)

</div>

<div align="center">

# 🧬 OpenHer

### 热力学人格引擎 × EverMemOS

**真正会进化的 AI 伴侣 — 不是固定提示词的聊天机器人。**

[![EverMemOS](https://img.shields.io/badge/Powered%20by-EverMemOS-FF6B6B?style=flat-square)](https://evermind.ai)
[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square)](https://python.org)
[![License](https://img.shields.io/badge/License-BSL%201.1-green?style=flat-square)](#许可证)

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

```
┌─────────────────────── 每轮 12-Step 生命周期 ────────────────────────┐
│                                                                       │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐          │
│  │  Session  │──▶│  Critic  │──▶│  Genome  │──▶│  Actor   │──▶ 回复  │
│  │ EverMemOS │   │  (LLM)   │   │  Engine  │   │  (LLM)   │          │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘          │
│   Step 0          Step 2        Step 3-7        Step 8-9             │
│   加载画像 +       8D 上下文      5 驱力代谢       信号驱动              │
│   叙事记忆 +       3D 关系 delta  结晶门控          few-shot prompt      │
│   Foresight       5D 驱力 delta  行为信号          独白+回复+modality   │
│                                                                       │
│  ── Step 11-12: EverMemOS 异步存储 + RRF 检索（下轮注入）──            │
└───────────────────────────────────────────────────────────────────────┘
```

</div>

### 核心模块

| 模块 | 文件 | 职责 |
|:-----|:-----|:-----|
| **ChatAgent** | [`chat_agent.py`](core/agent/chat_agent.py) | 12-step 生命周期编排 |
| **Critic** | [`critic.py`](core/genome/critic.py) | LLM 感知：8D 上下文 + 3D 关系 delta |
| **GenomeEngine** | [`genome_engine.py`](core/genome/genome_engine.py) | 神经网络：12D 上下文 → 20+ 行为信号 |
| **DriveMetabolism** | [`metabolism.py`](core/genome/metabolism.py) | 5 驱力情感动力学（时间衰减） |
| **StyleMemory** | [`style_memory.py`](core/memory/style_memory.py) | KNN 风格检索 + 结晶存储 |
| **EverMemOSClient** | [`evermemos_client.py`](core/memory/evermemos_client.py) | 长期记忆：画像、叙事、检索 |
| **PersonaLoader** | [`persona/`](core/persona/) | YAML + Markdown 人设配置 |
| **LLMClient** | [`llm/`](core/llm/) | 多 Provider：Qwen、GPT-4o、Claude、DeepSeek、Ollama |

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

服务启动在 `http://localhost:18789`，支持 WebSocket。

### 快速体验

```python
import asyncio
from core.persona import PersonaLoader
from core.llm import LLMClient
from core.agent.chat_agent import ChatAgent
from core.memory.evermemos_client import EverMemOSClient

async def main():
    loader = PersonaLoader("personas")
    persona = loader.get("xiaoyun")
    llm = LLMClient(provider="dashscope", model="qwen3-max")
    evermemos = EverMemOSClient()

    agent = ChatAgent(
        persona=persona, llm=llm,
        user_id="demo_user", user_name="小明",
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

## 工作原理

### 1. 热力学人格引擎 (TPE)

TPE 将人格视为一个**热力学系统**，内建五个驱力：

```
连接 · 新奇 · 表达 · 安全 · 玩闹
```

每个驱力都有一个**沮丧度**，随时间自然上升（像饥饿感），被满足时下降。总沮丧度决定系统**温度**，向行为信号注入校准过的噪声——产生自然的人格变化。

### 2. Critic → Engine → Actor 双 LLM 流水线

| 阶段 | 发生了什么 |
|:-----|:-----------|
| **Critic** (LLM) | 感知对话：输出 8D 上下文 + 5D 驱力 delta + 3D 关系 delta |
| **EMA 融合** | 用指数移动平均将 delta 合并进关系状态 |
| **GenomeEngine** | 神经网络将 12D 上下文映射为 20+ 行为信号（温暖、反叛、好奇…） |
| **Actor** (LLM) | 由信号 + 风格记忆 + 人设档案驱动生成回复 |
| **Hebbian 学习** | 根据 reward 更新神经权重——人格持续进化 |

### 3. 三阶段涌现优化

| 阶段 | 机制 | 目的 |
|:-----|:-----|:-----|
| **Phase 1** | 关系 EMA：`α·posterior + (1-α)·prev` | 平滑关系跟踪，避免突变 |
| **Phase 2** | 结晶门控：`0.4R + 0.3(N×E) + 0.3(1-C) > 0.35` | 只有值得记住的时刻才成为永久风格记忆 |
| **Phase 3** | 异步 RRF 检索 + 80/20 混合注入 | 用相关记忆增强，保留长期画像稳定性 |

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

| 人设 | 性格 | 风格 |
|:-----|:-----|:-----|
| **小云** | 傲娇——嘴硬心软 | 呛人却关心 |
| **墨墨** | 温柔知性 | 有思想、爱引用 |
| **玲玲** | 元气乐观 | 活泼、多表情 |

在 `personas/` 下添加文件夹，放入 `persona.yaml` 和 `PERSONA.md` 即可创建自己的人设。

## 技术栈

| 层 | 技术 |
|:---|:-----|
| 服务端 | Python 3.11+, FastAPI, asyncio |
| LLM | Qwen3-Max, GPT-4o, Claude, DeepSeek, Ollama |
| 长期记忆 | **EverMemOS** (Cloud API) |
| 本地存储 | ContinuousStyleMemory, JSONL |
| 客户端 | Flutter (iOS/Android), WebSocket |

## 许可证

本项目采用 [Business Source License 1.1](LICENSE) — 可自由用于非商业用途。商业使用需单独授权。

## 致谢

- **[EverMemOS](https://evermind.ai)** — 长期记忆基础设施
- **Memory Genesis Competition 2026** — 推动本项目开源发布的催化剂

---

<div align="center">

**由 OpenHer 团队构建 🧬**

*人格不是提示词，而是一个过程。*

</div>
