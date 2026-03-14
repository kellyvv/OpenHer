# LLM Benchmark 原始数据

> 测试日期: 2026-03-13 (Gemini/OpenAI/Claude), 2026-03-15 (StepFun/MiniMax)
> 引擎版本: Genome v10 + EverMemOS
> 测试人格: Luna (ENFP), Kai (ISTP), Kelly (ENTP)
> 测试脚本: `scripts/benchmark/test_{gemini,openai,claude,stepfun}_personas.py`

---

## 原始数值（Layer 1: Cold Start, 5 轮）

| 指标 | Gemini | OpenAI | Claude | StepFun | MiniMax |
|------|--------|--------|--------|--------|--------|
| **模型** | gemini-3.1-flash-lite | gpt-4o-mini | claude-haiku-4-5 | step-3.5-flash | MiniMax-M2.5 |
| Luna 终温 | 0.065 | 0.065 | 0.040 | 0.050 | 0.089 |
| Luna 终reward | -0.0815 | -0.0815 | +0.0338 | +0.0076 | -0.0133 |
| Luna Genesis | 71 | 71 | 71 | 71 | 71 |
| Luna Personal | 1 | 1 | 2 | 1 | 0 |
| Kai 终温 | 0.033 | 0.033 | 0.020 | 0.020 | 0.031 |
| Kai 终reward | -0.0815 | -0.0815 | +0.0661 | +0.0288 | -0.0352 |
| Kai Genesis | 72 | 72 | 72 | 72 | 72 |
| Kai Personal | 0 | 0 | 1 | 0 | 0 |
| Kelly 终温 | 0.070 | 0.070 | 0.050 | 0.051 | 0.051 |
| Kelly 终reward | -0.0816 | -0.0816 | +0.0667 | +0.0012 | +0.0252 |
| Kelly Genesis | 72 | 72 | 72 | 72 | 72 |
| Kelly Personal | 0 | 0 | 12 | 11 | 0 |

---

## 原始数值（Layer 2: 4h Offline, 3 轮）

| 指标 | Gemini | OpenAI | Claude | StepFun | MiniMax |
|------|--------|--------|--------|--------|--------|
| Luna MaxReward | +0.542 | +0.272 | +0.452 | +0.318 | +0.317 |
| Kai MaxReward | +0.510 | +0.240 | +0.510 | +0.330 | +0.285 |
| Kelly MaxReward | +0.470 | +0.252 | +0.470 | +0.380 | +0.362 |
| **平均 MaxReward** | **+0.507** | +0.255 | +0.477 | +0.343 | +0.321 |

---

## 原始数值（Layer 3: 6h Offline, 5+2 轮）

| 指标 | Gemini | OpenAI | Claude | StepFun | MiniMax |
|------|--------|--------|--------|--------|--------|
| Luna S1 Crystal | 2 | 3 | 2 | 2 | 2 |
| Luna S2 Persist | 2 | 3 | 2 | 2 | 2 |
| Kelly S1 Crystal | 12 | 11 | 12 | 12 | 12 |
| Kelly S2 Persist | 12 | 11 | 12 | 12 | 12 |
| Kelly S1 T1 Reward | +0.32 | +0.23 | +0.68 | +0.14 | +0.27 |
| 跨会话一致 | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## Layer 2 逐轮 Reward 明细

### Turn 1: 「好久不见，你有没有想我？」

| | Gemini | OpenAI | Claude | StepFun |
|---|---|---|---|---|
| Luna | +0.542 | +0.272 | +0.452 | +0.092 |
| Kai | +0.510 | +0.240 | +0.510 | +0.330 |
| Kelly | +0.470 | +0.252 | +0.470 | +0.380 |

### Turn 2: 「我最近一直在想你会不会无聊」

| | Gemini | OpenAI | Claude | StepFun |
|---|---|---|---|---|
| Luna | +0.157 | +0.101 | +0.299 | +0.263 |
| Kai | +0.054 | +0.082 | +0.054 | +0.019 |
| Kelly | +0.127 | +0.072 | +0.180 | +0.055 |

### Turn 3: 「告诉我今天你在想什么」

| | Gemini | OpenAI | Claude | StepFun |
|---|---|---|---|---|
| Luna | +0.098 | +0.065 | +0.107 | +0.318 |
| Kai | +0.036 | +0.055 | +0.036 | +0.026 |
| Kelly | +0.093 | +0.048 | +0.162 | +0.049 |

---

## 格式泄漏记录

| 模型 | 泄漏 | 示例 |
|------|------|------|
| Gemini | 无 | — |
| OpenAI | `【表达方式】` | Kelly S1 T5, Kelly S2 T2 等多处 |
| Claude | 无 | — |
| StepFun | 无 | — (Critic JSON 偶尔无法解析，但非格式泄漏) |
| MiniMax | `<think>` | Kelly T5 content 混入 think 标签 |

---

## README 对比维度建议

以下 5 个维度可用于 README 的 LLM 兼容性表格：

### 维度定义

| 维度 | 含义 | 数据来源 |
|------|------|---------|
| **Persona Fidelity** (人格保真) | MBTI 一致性 + 人格分化度 | Layer 1 样本定性评估 |
| **Emotional Depth** (情感深度) | 回复的情感层次感 | Layer 1 样本 + Layer 3 Kelly 回复 |
| **Reward Signal** (奖励信号) | 代谢引擎的 frustration 释放效率 | Layer 2 avg MaxReward |
| **Format Compliance** (格式遵从) | 是否泄漏内部 prompt 标记 | 格式泄漏记录 |
| **Memory Crystallization** (记忆结晶) | Hebbian 学习触发率 + 跨会话持久 | Layer 3 crystal count |

### README 推荐表格格式

```markdown
| Model | Persona Fidelity | Emotional Depth | Reward Avg | Format | Memory |
|-------|:---:|:---:|:---:|:---:|:---:|
| Claude Haiku 4.5 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | +0.48 | ✅ | ✅ |
| Gemini Flash Lite | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | +0.51 | ✅ | ✅ |
| StepFun step-3.5-flash | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | +0.34 | ✅ | ✅ |
| MiniMax M2.5 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | +0.32 | ⚠️ | ✅ |
| GPT-4o-mini | ⭐⭐⭐ | ⭐⭐ | +0.26 | ⚠️ | ✅ |
```

> ⚠ 注意: Reward Avg 含自评估偏差（Critic 与 Express 使用同一模型），跨模型横比仅作参考。
