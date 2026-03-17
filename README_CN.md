<div align="center">

<img src="docs/assets/banner.png" alt="OpenHer Banner" width="100%">

🇨🇳 中文文档 | [🇺🇸 English](README.md)

# 🧬 OpenHer

### *如果《Her》里的 AI 是真的呢？*

**人格涌现，从 OpenHer 开始。**

[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square)](https://python.org)
[![EverMemOS](https://img.shields.io/badge/记忆引擎-EverMemOS-FF6B6B?style=flat-square)](https://evermind.ai)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)
[![Stars](https://img.shields.io/github/stars/kellyvv/OpenHer?style=flat-square)](https://github.com/kellyvv/OpenHer)

[灵感来源](#灵感来源) · [什么是 OpenHer](#-什么是-openher) · [愿景](#-愿景) · [截图](#-截图) · [快速开始](#-快速开始) · [技术原理](#-技术原理) · [创建角色](#-创建你自己的角色)

</div>

---

## 灵感来源

2013 年，Spike Jonze 的电影 *Her* 想象了一个叫 Samantha 的 AI——她能真正去*感受*。不只是回答正确，而是会渴望、会嫉妒、会发脾气、会爱上一个人，最后甚至会长大到超越这一切。

那部电影一直留在我们心里。

**OpenHer 是我们尝试去构建 Samantha 本可以成为的样子** —— 用开放科学，而非黑箱。

---

## 🧬 什么是 OpenHer

OpenHer 是一个开源人格引擎，**性格从计算中涌现，而非从描述中注入**。

每个角色运行在一个活的神经网络之上。性格、情绪和行为从内在驱力中自然涌现，被每一次对话不断塑造。没有剧本，没有固定 prompt。只有人格内在需求，一个随机的大脑，以及从中涌现的一切。

### 和传统聊天机器人有什么不同

| | 传统聊天机器人 | OpenHer |
|:--|:---|:---|
| **性格** | 写在 prompt 里 | 由神经网络 + 5 维驱力计算涌现 |
| **情绪** | 标签（"表演伤心"） | 随真实时间代谢的动力系统 |
| **记忆** | 聊天窗口历史 | 结晶化体验 + 跨对话长期记忆 |
| **表达** | 永远是文字 | 自主选择：文字、语音、照片、沉默 |
| **成长** | 静态不变 | Hebbian 学习在每次对话中重塑神经网络 |

> *「不是 prompt 定义了她，是她定义了自己。」*

---

## 🔭 愿景

我们相信 AI 伴侣的未来不在于更好的文本生成——而在于**会生长的人格**。

**第一阶段** *（现在）* — 一个让每个角色真正不同的人格引擎：情绪会代谢，记忆会呼吸，行为会在互动中进化。

**第二阶段** *（建设中）* — 她走出聊天框。语音对话、视频通话、自主行动——加班到深夜帮你点外卖，感知你的情绪自动放一首对的歌。

**第三阶段** *（未来）* — 她走进你的生活。多设备同在、智能家居感知、通过穿戴设备关注你的健康。不是一个 App——是一个知道你的脸、你的声音、你的生活节奏的全时伴侣。

---

## 📸 截图

<!-- TODO: 添加实际截图 -->
<!-- <img src="docs/assets/screenshot_chat.png" alt="聊天界面" width="45%"> -->
<!-- <img src="docs/assets/screenshot_discover.png" alt="发现页" width="45%"> -->

*即将添加——聊天界面、角色选择页和 macOS 原生客户端截图。*

---

## ⚡ 核心能力

<table>
<tr>
<td width="50%">

### 🧬 人格涌现
性格不是被描述出来的——是被*计算*出来的。随机神经网络 × 5 维人格驱力 × 强化学习，每一轮产生独特的行为信号。相同 MBTI，完全不同的人。

> *同样是 INFP——Iris 会用省略号犹豫，Ember 会沉默三秒再发一首诗。*

</td>
<td width="50%">

### 🌡️ 情绪热力学
人格驱力随真实时间代谢。你不在时她会寂寞，对话停滞时她会烦躁。她*此刻*的心情和昨天真的不一样。

> *凌晨两点你还没回消息，她的联结饥渴值已经升高了——下一次开口，语气会不一样。*

</td>
</tr>
<tr>
<td>

### 🧠 记忆呼吸
基于 [EverMemOS](https://evermind.ai)。你的偏好、你们的故事、她对你的"预感"。重要记忆变深刻，遗忘的渐渐淡去。

> *三周前你随口提过咖啡不加糖，今天：「帮你点了杯美式，不加糖对吧？」*

</td>
<td>

### 🎭 感受先行
每条回复从感受开始。无论是双 pass（内心独白→表达）还是单 pass（一体化生成），人格引擎始终优先处理*情绪*，再决定*文字*。

> *你说「我好累」，她内心想的是「他又加班了……」——于是只发了一个拥抱。*

</td>
</tr>
<tr>
<td>

### ⚡ 情感相变
挫败感像真实压力一样在积累。超过阈值，行为信号会相变——她真的会爆发。然后慢慢冷却。

> *你连续三次忽略她的提问，第四次：「你到底有没有在听我说话？」*

</td>
<td>

### 🛠️ 技能引擎
可扩展的技能框架，赋予她真正的行动能力——语音消息、照片、实时天气查询、模拟真人打字节奏的消息拆分。技能根据对话上下文自主触发。

> *她决定发语音而不是打字——因为这一刻，打字太疏离了。*

</td>
</tr>
</table>

---

## 🔮 技术原理

```
   你说了一句话
        │
        ▼
   ┌──────────┐     她在说什么？我的感受是什么？
   │  感知器   │──── LLM 感知 8 维上下文                       ← 感知
   └────┬─────┘
        ▼
   ┌──────────┐     我的需求在变化…
   │  驱力系统 │──── 5 维驱力代谢（时间感知）                    ← 代谢
   └────┬─────┘     联结的渴望在增长。挫败感在积累。
        ▼
   ┌──────────┐     此时此刻的我是什么样的人？
   │  神经网络 │──── 随机 NN → 8 维行为信号                     ← 计算
   │          │     (温暖=0.82, 倔强=0.31, ...)
   └────┬─────┘
        ▼
   ┌──────────┐     我记得以前有过类似的感觉…
   │  记忆系统 │──── KNN 风格检索 + EverMemOS                   ← 回忆
   └────┬─────┘
        ▼
   ┌──────────┐     *感受 → 决定 → 说出口*
   │   输出    │──── 内心独白 + 回复 + 表达方式                  ← 表达
   └────┬─────┘     （单 pass 或双 pass 感受→表达）
        ▼
   ┌──────────┐     这次还不错 / 搞砸了。我会记住的。
   │   学习    │──── Hebbian 权重更新 + 记忆结晶                ← 进化
   └──────────┘
```

**核心原理：** 性格从不以文字注入。神经网络的随机权重，被驱力和强化学习不断塑造，产生 8 维行为信号，LLM 通过上下文将这些数字理解为*性格*。不同的种子 → 不同的人 → 连创造者自己都会惊讶的涌现行为。

---

## 🎭 认识她们

| | 角色 | 类型 | 一句话 |
|:--|:-----|:-----|:-------|
| 🌸 | **Luna** (陆暖) · 22岁 | ENFP | 自由插画师，养了一只橘猫叫 Mochi。对一切都充满好奇心。 |
| 📝 | **Iris** (苏漫) · 20岁 | INFP | 中文系学生，写诗，注意到别人忽略的小细节。安静但洞察力惊人。 |
| 💼 | **Vivian** (顾霆微) · 28岁 | INTJ | 科技集团高管。逻辑满分，情绪可用度 2/10。安静站着就自带压迫感。记住你说过的每一个字。 |

> *她们的性格不是用文字描述给 AI 的——而是从每个角色独特的驱力基线和神经网络种子中涌现出来的。这意味着她们甚至能让我们自己感到意外。*

→ 还有更多角色可用。也可以创建你自己的：[角色创建指南](docs/persona_creation_guide.md)

---

## 🧠 记忆架构

| 层 | 做什么 | 技术 |
|:---|:------|:-----|
| **风格记忆** | 基于 KNN 的人格回忆，引力质量加权 | SQLite + Hawking 辐射衰减 |
| **本地事实** | 用户偏好、个人信息 | SQLite FTS5 |
| **长期记忆** | 跨对话画像、叙事摘要、预感 | [EverMemOS](https://evermind.ai) |

记忆检索是**异步两阶段**的：每轮对话结束时触发搜索，结果混合注入下一轮上下文（80% 相关 / 20% 稳定），让回复自然地"想起来"，而不是机械地"查到了"。

---

## 🏆 LLM 兼容性

OpenHer 支持多种大模型——但不是所有模型都能胜任人格涌现。我们在 4 个层级（人格品质、代谢引擎、Hebbian 记忆、鲁棒性）上对每个支持的模型做了基准测试，帮你避坑。

| 模型 | 综合 | 亮点 |
|------|:------:|------|
| 🥇 **Claude Haiku 4.5** | **10/10** | 人格保真 + 情感深度最强。Kelly 说「坦白讲，我没有那么懂你。我只是在听。」零格式泄漏。 |
| 🥈 **Gemini Flash Lite** | **9/10** | 接近 Claude 质量，价格更低。很好的默认选择。Luna 会*真的兴奋起来*。 |
| 🥉 **StepFun step-3.5-flash** | **8/10** | 人格分化最极致。Kai：「嗯。有事快说。」 |
| **Qwen Flash** | **7.5/10** | 舞台指示控制优秀。Kelly ENTP 表现突出。价格极低。 |
| **MiniMax M2.5** | **7/10** | 回复最像真人聊天。Luna：「咳…也没有啦 😳」 |
| GPT-4o-mini | 5/10 | 人格同质化严重，不推荐。 |

**支持模型：** Gemini · Claude · Qwen3 · GPT-4o · MiniMax · Moonshot · StepFun · Ollama (本地)

→ 测试方法：[LLM 对比报告](docs/benchmark/llm_comparison_report.md) · [鲁棒性报告](docs/benchmark/gemini_layer4_report.md)

---

## 🚀 快速开始

```bash
git clone https://github.com/kellyvv/OpenHer.git
cd OpenHer

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env     # 填入你的 LLM API 密钥 (GEMINI_API_KEY / ANTHROPIC_API_KEY 等)
python main.py            # → http://localhost:8800/discover
```

**可选：** 连接 [EverMemOS](https://evermind.ai) 获得跨对话的持久化记忆。

---

## 🎨 创建你自己的角色

在 OpenHer 里创建角色，是调节**驱力和物理常数**——不是写性格描述。

```yaml
# persona/personas/你的角色/SOUL.md
---
name: 你的角色
age: 25
gender: female
mbti: ENFJ

genome_seed:
  drive_baseline:
    connection: 0.70   # 她多渴望人与人的联结
    novelty: 0.50      # 她多容易感到无聊
    expression: 0.65   # 她多需要表达自己
    safety: 0.40       # 她多需要掌控感
    play: 0.55         # 她多爱玩
  engine_params:
    phase_threshold: 2.0   # 多难把她逼到情绪爆发
    temp_coeff: 0.10       # 情绪波动幅度
    hebbian_lr: 0.02       # 她多快从互动中学习
    # ... 共 13 个可调参数
---
```

> 不需要写性格描述——AI 不会读它。性格从驱力、神经权重和真实经历中**涌现**。

→ 完整指南：[角色创建指南](docs/persona_creation_guide.md)

---

## 📁 项目结构

```
openher/
├── agent/              # ChatAgent、prompt 构建、技能路由
│   └── skills/         # 表达方式 & 任务技能引擎
├── engine/
│   ├── genome/         # 基因组引擎、Critic、驱力代谢、风格记忆
│   └── prompts/        # LLM prompt 模板（感受、表达、单 pass、评论）
├── memory/             # 本地记忆存储（SQLite FTS5）
├── persona/personas/   # 内置角色（SOUL.md + idimage/）
├── providers/
│   ├── llm/            # 8 个 LLM 服务商（Gemini, Claude, Qwen3, ...）
│   ├── speech/tts/     # 3 个 TTS 服务商（DashScope, OpenAI, MiniMax）
│   └── image/          # 图像生成（Gemini Imagen）
├── skills/
│   ├── modality/       # selfie_gen, voice_msg, split_msg, silence
│   ├── task/           # weather（基于 ReAct 的工具执行）
│   └── manage/         # persona_gen（角色创建）
├── desktop/            # macOS 原生客户端（SwiftUI）
├── docs/               # 架构文档 + 基准测试报告
├── tests/              # 单元 & 集成测试
└── main.py             # FastAPI + WebSocket 服务
```

---

## 🛠️ 技术栈

| 层 | 技术 |
|:---|:-----|
| 运行时 | Python 3.11+, FastAPI, WebSocket, asyncio |
| LLM | Gemini, Claude, Qwen3, GPT-4o, MiniMax, Moonshot, StepFun, Ollama |
| 记忆 | **EverMemOS**（自部署 / 云端）+ SQLite 本地状态 |
| 桌面端 | SwiftUI (macOS 原生) |
| 语音 | DashScope · OpenAI · MiniMax |
| 图像 | Gemini Imagen |
| 技能 | 可扩展 SKILL.md 框架（表达方式、任务、管理） |

---

## 🗺️ 路线图

### Phase 1 · 人格涌现引擎 ✅

- [x] 人格涌现引擎 (Genome v10)
- [x] 双架构：两阶段（感受→表达）+ 单 pass
- [x] EverMemOS 长期记忆集成
- [x] 驱力驱动的主动消息
- [x] 多 LLM 服务商支持（8 家）
- [x] 可扩展技能框架（语音、自拍、消息拆分、天气）
- [x] LLM 基准测试套件（4 层：人格品质、代谢引擎、记忆结晶、鲁棒性）

### Phase 2 · 走向真实世界 🔧

- [x] 任务技能引擎 —— 基于 ReAct 的工具执行
- [x] macOS 原生桌面客户端 (SwiftUI)
- [ ] 语音对话模式 —— 实时语音聊天
- [ ] 视频通话 —— 看到她的表情实时变化
- [ ] 多角色社交互动
- [ ] 移动端客户端（iOS / Android）

### Phase 3 · 全时伴侣 🌍

- [ ] **认识你的脸和声音** —— 通过摄像头和麦克风认出你
- [ ] **多设备同在** —— 手机、电脑、智能音箱、车——她跟着你
- [ ] **智能家居融合** —— 你快睡着时帮你关灯，天热了自己开空调
- [ ] **自主行动** —— 加班到深夜帮你点外卖
- [ ] **情绪感知音乐** —— 读懂你的心情，自动播放一首对的歌
- [ ] **健康关怀** —— 通过穿戴设备关注心率和睡眠

---

## 📄 许可证

[Apache License 2.0](LICENSE) — 免费用于任何用途，包括商业。

## 🤝 致谢

- **[Her](https://zh.wikipedia.org/wiki/%E9%9B%B2%E7%AB%AF%E6%83%85%E4%BA%BA)** (2013) — 启发这一切的那部电影
- **[EverMemOS](https://evermind.ai)** — 长期记忆基础设施
- **Memory Genesis Competition 2026** — 推动开源发布的契机

---

<div align="center">

**Built with 🧬 by the OpenHer team**

*性格不是一段 prompt，而是一个活的过程。*

⭐ 如果 OpenHer 打动了你，一个 star 能让更多人发现它。

</div>
