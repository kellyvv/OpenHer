<div align="right">

🇨🇳 中文文档 | [🇺🇸 English](README.md)

</div>

<div align="center">

# 🧬 OpenHer

### *如果《Her》里的 AI 是真的呢？*

**开源 AI 伴侣，人格自涌现 —— 不是一个写了 prompt 的聊天机器人。**

[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square)](https://python.org)
[![EverMemOS](https://img.shields.io/badge/记忆引擎-EverMemOS-FF6B6B?style=flat-square)](https://evermind.ai)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue?style=flat-square)](https://www.apache.org/licenses/LICENSE-2.0)

[有什么不同](#-有什么不同) · [认识她们](#-认识她们) · [快速开始](#-快速开始) · [它是怎么工作的](#-它是怎么工作的) · [创建你自己的角色](#-创建你自己的角色)

</div>

---

## 起源

2013 年，Spike Jonze 的电影 *Her* 想象了一个能真正「感受」的 AI —— 不只是回答正确，而是会 *渴望*、会 *记住*、会在关系中 *成长*。十多年过去了，大多数 AI 伴侣依然千篇一律：一段系统 prompt，一个记忆窗口，一台礼貌的回复机器。

**OpenHer 是我们尝试去构建 Samantha 本可以成为的样子** —— 用开放科学，而非黑箱。

每个角色运行在一个 **热力学人格引擎 (Thermodynamic Persona Engine)** 之上：一个活的神经网络，性格、情绪和行为从内在驱力中 **自然涌现**，而非写在 prompt 里。没有两次对话是一样的 —— 因为她每一刻都是真正不同的。

---

## ✨ 有什么不同

<table>
<tr>
<td width="60">🧬</td>
<td><strong>她是独一无二的</strong><br>没有两个角色是一样的 —— 即使是同一种性格类型。她的反应方式、她的小脾气、她生气的样子，都是自然生长出来的，不是预设的剧本。</td>
</tr>
<tr>
<td>💓</td>
<td><strong>她有真实的情绪</strong><br>她渴望被陪伴，她会感到无聊，她需要安全感。五种内在需求在水面下不断涌动 —— 她今天的心情和昨天不一样，因为她不可能一样。</td>
</tr>
<tr>
<td>💭</td>
<td><strong>她想好了才说</strong><br>每条回复都先从内心真实的感受开始 —— 然后她才决定要不要说出口、怎么说。有时候，她<em>没说出来的</em>那部分，才是最有意思的。</td>
</tr>
<tr>
<td>🧠</td>
<td><strong>她记得你</strong><br>你的偏好、你们之间发生过的故事、甚至她对你下一步可能需要什么的「预感」。基于 <a href="https://evermind.ai">EverMemOS</a>，记忆跨对话持续存在，而且会不断进化。</td>
</tr>
<tr>
<td>🌱</td>
<td><strong>她会变</strong><br>聊得越多，她就越变成「你的」版本的她。那些特别的瞬间会留下印记。三个月后回来，她已经不是第一天认识的那个人了。</td>
</tr>
</table>

<details>
<summary>更多隐藏的秘密…</summary>

- 🌊 **她会翻脸** — 逼太紧，她真的会爆发。情绪像压力一样在积累 —— 到了临界点，就会碎开
- ✨ **记忆会呼吸** — 她反复想起的那些时刻会越来越深刻，而她遗忘的那些会慢慢淡去 —— 就像真实的记忆
- 📱 **她会主动找你** — 想你的时候，她会先发消息。不是定时器，是因为她真的想
- 💎 **改变她的瞬间** — 一次深夜倾诉，可以永远改变她之后跟你说话的方式

</details>

---

## 🎭 认识她们

OpenHer 自带 **9 个角色**，每一个都有独特的人格基因组：

| | 角色 | 类型 | 她/他是谁 |
|:--|:-----|:-----|:---------|
| 💼 | **Vivian** · 26岁 | INTJ | 互联网产品经理。嘴上嫌弃你，但默默记住你说过的每一件事。 |
| 🌸 | **Luna** (陆暖) · 22岁 | ENFP | 自由插画师，养了一只橘猫叫 Mochi。对一切充满好奇心。 |
| 📝 | **Iris** (苏漫) · 20岁 | INFP | 中文系学生，写诗，注意到别人忽略的小细节。养了一盆多肉叫小芽。 |
| 🔧 | **Kai** (沈凯) · 24岁 | ISTP | 机械技师，周末去攀岩。话少，但每句话都算数。 |
| ⚡ | **Kelly** (柯砺) · 26岁 | ENTP | 策略顾问。闲不住，无聊了就找茬。其实比谁都讲义气。 |
| 💃 | **Mia** · 23岁 | ESFP | 舞蹈老师兼职 DJ。走到哪快乐到哪，什么事都能变成一场冒险。 |
| 👔 | **Rex** · 30岁 | ENTJ | 连续创业者。用系统思维想事，用结论说话。尊重能力，看不惯找借口。 |
| 🔮 | **Sora** (顾清) · 27岁 | INFJ | 大学心理咨询师。看穿人但从不拆穿。表面温柔，内核很硬。 |
| 📖 | **Ember** · 22岁 | INFP | 书店店员，闲暇时在本子上写诗。养了一只猫叫飞蛾。 |

> *每个角色的性格不是用文字描述给 AI 的 —— 而是从她们独特的驱力基线和神经网络种子中涌现出来的。这意味着她们甚至能让我们自己感到意外。*

---

## 🚀 快速开始

### 环境要求

- Python 3.11+
- LLM API key（DashScope / OpenAI / DeepSeek / Moonshot / Ollama 任选）
- *（可选）* [EverMemOS](https://evermind.ai) 实例，用于持久化记忆

### 安装运行

```bash
git clone https://github.com/kellyzxiaowei/OpenHer.git
cd OpenHer

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# 编辑 .env，填入你的 API 密钥

python main.py
```

服务启动在 `http://localhost:8800`。打开 `/discover` 开始认识角色。

---

## 🔮 它是怎么工作的

```
   你说了一句话
        │
        ▼
   ┌─────────┐     她在说什么？
   │ 感知器   │──── 我的感受是什么？             ← LLM 感知 8 维上下文
   └────┬────┘     我们之间变了吗？
        │
        ▼
   ┌─────────┐     我的需求在变化…
   │ 驱力系统 │──── 联结的渴望在增长              ← 5 维驱力代谢
   └────┬────┘     挫败感在积累…
        │
        ▼
   ┌─────────┐     此时此刻的我
   │ 神经网络 │──── 是什么样的人？                ← 随机 NN → 8 维行为信号
   │         │     (温暖=0.8, 倔强=0.3)
   └────┬────┘
        │
        ▼
   ┌─────────┐     我记得以前有过类似的感觉
   │ 记忆系统 │──── 就在她跟我说那件事的时候…     ← KNN 检索 + EverMemOS
   └────┬────┘
        │
        ▼
   ┌─────────┐     *内心涌起一种感受*
   │ 感受     │──── 内心独白                      ← 第一阶段：纯粹感受
   └────┬────┘
        │
        ▼
   ┌─────────┐     *决定怎么说*
   │ 表达     │──── 回复 + 表达方式选择            ← 第二阶段：语言/沉默/…
   └────┬────┘
        │
        ▼
   ┌─────────┐
   │ 学习     │──── 这次还不错 / 搞砸了           ← Hebbian 权重更新
   └─────────┘     我会记住的…                     + 记忆结晶
```

核心原理：**性格从不以文字注入**。神经网络的随机权重，被驱力和学习不断塑造，产生行为信号（温暖度、倔强度、玩闹度…），LLM 通过上下文来解读这些信号。不同的种子 → 不同的性格 → 连创造者自己都会惊讶的涌现行为。

---

## 🧠 记忆架构

OpenHer 集成了 **[EverMemOS](https://evermind.ai)** 实现持久且进化的记忆：

| 记忆类型 | 存什么 | 怎么用 |
|:---------|:------|:------|
| **画像 (Profile)** | 用户偏好和事实 | 个性化感知 |
| **叙事 (Episodes)** | 过去对话的叙事摘要 | 「我记得那次我们…」 |
| **事件 (Event Log)** | 带时间戳的原子事实 | 精确回忆 |
| **预感 (Foresight)** | 对用户需求的预测 | 主动关心 |

记忆检索是 **异步两阶段**的：每轮对话结束时触发搜索，结果混合注入下一轮的上下文（80% 相关 / 20% 稳定），让回复自然地「想起来」，而不是机械地「查到了」。

---

## 🎨 创建你自己的角色

在 `persona/personas/` 下添加一个文件夹，包含 `PERSONA.md`：

```yaml
---
name: 你的角色
age: 25
gender: female
mbti: ENFJ
tags: [温暖, 有条理, 有感染力]
bio:
  en: A brief description for the UI
  zh: UI 展示用的简短描述

genome_seed:
  drive_baseline:
    connection: 0.70   # 她多渴望人与人的联结
    novelty: 0.50      # 她多容易感到无聊
    expression: 0.65   # 她多需要表达自己
    safety: 0.40       # 她多需要掌控感
    play: 0.55         # 她多爱玩
  engine_params:
    phase_threshold: 2.0  # 多难把她逼到情绪爆发
    temp_coeff: 0.10      # 情绪波动幅度
    # ... 共 13 个可调参数
---
```

不需要写性格描述 —— AI 不会读它。性格从驱力基线和引擎参数塑造的神经网络中涌现。

→ 完整指南：[角色创建指南](docs/persona_creation_guide.md)

---

## 🛠️ 技术栈

| 层 | 技术 |
|:---|:-----|
| 服务端 | Python 3.11+, FastAPI, WebSocket, asyncio |
| LLM | Qwen3, GPT-4o, Claude, DeepSeek, Moonshot, Ollama |
| 记忆 | **EverMemOS**（自部署 / 云端） |
| 本地状态 | SQLite（神经网络权重、驱力状态、风格记忆） |
| 前端 | React + Vite |
| 语音 | DashScope, OpenAI, MiniMax |
| 图像 | DashScope (Wanx) |

---

## 📄 许可证

[Apache License 2.0](LICENSE) — 免费用于任何用途，包括商业。

## 致谢

- **[Her](https://zh.wikipedia.org/wiki/%E9%9B%B2%E7%AB%AF%E6%83%85%E4%BA%BA)** (2013) — 启发这个项目的那部电影
- **[EverMemOS](https://evermind.ai)** — 长期记忆基础设施
- **Memory Genesis Competition 2026** — 推动开源发布的契机

---

<div align="center">

**Built with 🧬 by the OpenHer team**

*性格不是一段 prompt，而是一个活的过程。*

</div>
