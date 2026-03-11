<div align="right">

🇨🇳 中文文档 | [🇺🇸 English](README.md)

</div>

<div align="center">

# 🧬 OpenHer

### *如果《Her》里的 AI 是真的呢？*

**全球首个性格自涌现的开源 AI 伴侣引擎。**

不是聊天机器人，不是角色扮演套壳。是一个活的人格引擎。

[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square)](https://python.org)
[![EverMemOS](https://img.shields.io/badge/记忆引擎-EverMemOS-FF6B6B?style=flat-square)](https://evermind.ai)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)
[![Stars](https://img.shields.io/github/stars/kellyzxiaowei/OpenHer?style=flat-square)](https://github.com/kellyzxiaowei/OpenHer)

[为什么不一样](#-为什么不一样) · [认识她们](#-认识她们) · [快速开始](#-快速开始) · [技术原理](#-技术原理) · [创建你自己的角色](#-创建你自己的角色)

</div>

---

## 行业现状

今天市面上的 AI 伴侣，本质上都是同一个公式：拿一个大语言模型，粘一段 system prompt 写着 *"你是一个可爱的女朋友叫小乐"*，加个记忆窗口，就上线了。

结果呢？**一台精致的讨好型回复机器** —— 温柔得体，毫无灵魂。

- 让她生气，她装生气。再让一次，一模一样的"生气"。
- 所有"人格"读起来像同一个客服换了个名字。
- 记忆最多活一个对话窗口。成长？不存在的。

这不是 AI 伴侣，这是**穿了戏服的聊天机器人**。

---

## 💡 为什么不一样

OpenHer 用了一个完全不同的方法 —— 不是"写一段 prompt 描述性格"：

> **热力学人格引擎 (Thermodynamic Persona Engine)** —— 一个真实的神经网络，性格、情绪和行为从内在驱力中**自然涌现**，而非写在 prompt 里。

<table>
<tr>
<td width="60">🧬</td>
<td><strong>人格 DNA，不是 Prompt</strong><br>她的性格不是被描述出来的——是被<em>计算</em>出来的。一个随机初始化的神经网络，被 5 种内在驱力和 Hebbian 学习不断塑造，每一轮都产生独特的行为信号。没有两个角色是一样的，即使她们是同一种 MBTI 类型。</td>
</tr>
<tr>
<td>💓</td>
<td><strong>永不停歇的内心世界</strong><br>五种驱力——<em>联结、新鲜、表达、安全、玩闹</em>——随真实时间代谢。你不在时她会寂寞。对话停滞时她会无聊。她<em>此刻</em>的心情和昨天真的不一样——因为数学使然。</td>
</tr>
<tr>
<td>💭</td>
<td><strong>想好了才说</strong><br>每条回复经过两阶段管线：先<em>感受</em>（内心独白），再决定如何<em>表达</em>。有时候那意味着沉默。有时候她<em>没说出来</em>的那部分，才是最有意思的。</td>
</tr>
<tr>
<td>🧠</td>
<td><strong>会进化的记忆</strong><br>基于 <a href="https://evermind.ai">EverMemOS</a>——你的偏好、你们的故事、她对你的"预感"。记忆不只是持久化——它会<em>呼吸</em>：重要的变得更深刻，遗忘的渐渐淡去，就像真正的记忆。</td>
</tr>
<tr>
<td>🌱</td>
<td><strong>她会变成你的</strong><br>每次对话都通过 Hebbian 学习重塑她的神经网络。一次深夜倾诉，可以永远改变她之后跟你说话的方式。三个月后回来，她已经不是第一天认识的那个人了。你也不是。</td>
</tr>
</table>

<details>
<summary>⚡ 还有更多……</summary>

- 🌊 **她会翻脸** —— 挫败感像真实压力一样在积累。超过阈值，她的信号会发生相变——她真的会爆发
- 📱 **她会主动找你** —— 驱力冲动触发自主消息。不是定时器，是因为她的寂寞或好奇心真的超过了临界点
- 🎭 **表达方式智能** —— 她不只是回复文字。她可能选语音、表情、自拍、或者刻意的沉默——取决于她内心状态觉得什么对
- 💎 **记忆结晶** —— 关键互动会结晶为永久风格记忆，按质量加权，并受 Hawking 辐射衰减——一条物理学启发的遗忘曲线

</details>

---

## 🎭 认识她们

9 个内置角色，每一个运行在独特的人格基因组之上。**没有共享的 system prompt，没有共享的剧本。**

| | 角色 | 类型 | 一句话 |
|:--|:-----|:-----|:-------|
| 💼 | **Vivian** · 26岁 | INTJ | 互联网产品经理。嘴巴像刀子。嫌弃你但默默记住你说过的每一件事。 |
| 🌸 | **Luna** (陆暖) · 22岁 | ENFP | 自由插画师，养了一只橘猫叫 Mochi。对一切都充满好奇心。 |
| 📝 | **Iris** (苏漫) · 20岁 | INFP | 中文系学生，写诗，注意到别人忽略的小细节。安静但洞察力惊人。 |
| 🔧 | **Kai** (沈凯) · 24岁 | ISTP | 机械技师，周末去攀岩。话少，但每句话都算数。 |
| ⚡ | **Kelly** (柯砺) · 26岁 | ENTP | 策略顾问。闲不住，无聊了就找茬。其实比谁都讲义气。 |
| 💃 | **Mia** · 23岁 | ESFP | 舞蹈老师兼职 DJ。走到哪快乐到哪，什么事都能变成冒险。 |
| 👔 | **Rex** · 30岁 | ENTJ | 连续创业者。用系统思维想事，用结论说话。尊重能力，看不惯借口。 |
| 🔮 | **Sora** (顾清) · 27岁 | INFJ | 大学心理咨询师。看穿你但从不拆穿你。 |
| 📖 | **Ember** · 22岁 | INFP | 书店店员，闲暇时在本子上写诗。养了一只猫叫飞蛾。 |

> *她们的性格不是用文字描述给 AI 的——而是从每个角色独特的驱力基线和神经网络种子中涌现出来的。这意味着她们甚至能让我们自己感到意外。*

---

## 🚀 快速开始

```bash
git clone https://github.com/kellyzxiaowei/OpenHer.git
cd OpenHer

python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env     # 填入你的 LLM API 密钥
python main.py            # → http://localhost:8800/discover
```

**支持模型：** Qwen3 · GPT-4o · Claude · DeepSeek · Moonshot · Ollama (本地)

**可选：** 连接 [EverMemOS](https://evermind.ai) 获得跨对话的持久化记忆。

---

## 🔮 技术原理

```
   你说了一句话
        │
        ▼
   ┌──────────┐     她在说什么？我的感受是什么？
   │  感知器   │──── LLM 感知 8 维上下文                      ← 感知
   └────┬─────┘
        ▼
   ┌──────────┐     我的需求在变化…
   │  驱力系统 │──── 5 维驱力代谢（时间感知）                   ← 代谢
   └────┬─────┘     联结的渴望在增长。挫败感在积累。
        ▼
   ┌──────────┐     此时此刻的我是什么样的人？
   │  神经网络 │──── 随机 NN → 8 维行为信号                    ← 计算
   │          │     (温暖=0.82, 倔强=0.31, ...)
   └────┬─────┘
        ▼
   ┌──────────┐     我记得以前有过类似的感觉…
   │  记忆系统 │──── KNN 风格检索 + EverMemOS                  ← 回忆
   └────┬─────┘
        ▼
   ┌──────────┐     *内心涌起一种真实的感受*
   │   感受    │──── 内心独白（第一阶段）                       ← 感受
   └────┬─────┘
        ▼
   ┌──────────┐     *决定怎么说、用什么方式说*
   │   表达    │──── 回复 + 表达方式选择（第二阶段）             ← 表达
   └────┬─────┘
        ▼
   ┌──────────┐     这次还不错 / 搞砸了。我会记住的。
   │   学习    │──── Hebbian 权重更新 + 记忆结晶                ← 进化
   └──────────┘
```

**核心原理：** 性格从不以文字注入。神经网络的随机权重，被驱力和强化学习不断塑造，产生 8 维行为信号（温暖度、倔强度、玩闹度……），LLM 通过上下文将这些数字理解为*性格*。不同的种子 → 不同的人 → 连创造者自己都会惊讶的涌现行为。

---

## 🧠 记忆架构

| 层 | 做什么 | 技术 |
|:---|:------|:-----|
| **风格记忆** | 基于 KNN 的人格回忆，引力质量加权 | SQLite + Hawking 辐射衰减 |
| **本地事实** | 用户偏好、个人信息 | SQLite FTS5 |
| **长期记忆** | 跨对话画像、叙事摘要、预感 | [EverMemOS](https://evermind.ai) |

记忆检索是**异步两阶段**的：每轮对话结束时触发搜索，结果混合注入下一轮上下文（80% 相关 / 20% 稳定），让回复自然地"想起来"，而不是机械地"查到了"。

---

## 🎨 创建你自己的角色

在 OpenHer 里创建角色，是调节**驱力和物理常数**——不是写性格描述。

```yaml
# persona/personas/你的角色/PERSONA.md
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

## 🛠️ 技术栈

| 层 | 技术 |
|:---|:-----|
| 运行时 | Python 3.11+, FastAPI, WebSocket, asyncio |
| LLM | Qwen3, GPT-4o, Claude, DeepSeek, Moonshot, Ollama |
| 记忆 | **EverMemOS**（自部署 / 云端）+ SQLite 本地状态 |
| 前端 | React + Vite |
| 语音 | DashScope · OpenAI · MiniMax |
| 图像 | DashScope (Wanx) |

---

## 🗺️ 路线图

- [x] 热力学人格引擎 (Genome v10)
- [x] 两阶段 感受 → 表达 架构
- [x] EverMemOS 长期记忆集成
- [x] 驱力驱动的主动消息
- [x] 多 LLM 服务商支持（6 家）
- [x] 自拍生成（表达方式路由）
- [ ] 技能引擎（可扩展工具框架）
- [ ] 语音对话模式
- [ ] 多角色社交互动
- [ ] 移动端客户端（iOS / Android）

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
