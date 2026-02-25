# OpenHer 产品方案 v2

> **Genome v10 × EverMemOS** — 热力学人格引擎驱动的虚拟伴侣
>
> 最后更新: 2026-02-26

---

## 一、产品定位

OpenHer 是一款基于 **热力学人格引擎 (Thermodynamic Persona Engine, TPE)** 的虚拟伴侣产品。区别于传统 AI 聊天机器人的「固定人设 + 提示词模板」方案，OpenHer 通过 **神经网络信号驱动 + LLM 涌现** 的双引擎架构，让 AI 伴侣具备：

- 🧬 **自主人格演化** — 行为风格随互动自然变化，不依赖硬编码
- 🌡️ **热力学情绪** — 内建 5 维驱力代谢系统，产生真实的情绪波动
- 🧠 **跨会话长期记忆** — 通过 EverMemOS 实现用户画像、叙事记忆、预测性洞察
- 🎭 **非模板化表达** — LLM 自主涌现 modality（文字/语音/表情/图片）

---

## 二、核心技术架构

### 2.1 每轮生命周期 (12-Step Lifecycle)

```
用户消息 → Step 0-2.5 (感知) → Step 3-4 (强化) → Step 5-8.5 (构建) → Step 9-12 (执行)
```

| 阶段 | Step | 模块 | 功能 |
|:-----|:-----|:-----|:-----|
| 感知 | 0 | EverMemOS | 首轮加载用户画像、关系先验 |
| 感知 | 1 | DriveMetabolism | 时间代谢：驱力按时间自然增长 |
| 感知 | 2 | Critic (LLM) | 8D 上下文感知 + 5D frustration delta + 3D 关系 delta |
| 感知 | 2.5 | 关系 EMA | prior + delta + clip + EMA → 4D 关系状态 |
| 强化 | 3 | DriveMetabolism | LLM delta → reward（[-1, 1]） |
| 强化 | 3.5 | Drive Evolution | Hebbian baseline 演化（LR=0.003） |
| 强化 | 4 | Crystallization | 综合分门控：0.4R + 0.3(N×E) + 0.3(1-C) > 0.35 |
| 构建 | 5-6 | GenomeEngine | 12D context → 20+ 行为信号 + 热力学噪声 |
| 构建 | 7 | StyleMemory | KNN 检索 top-3 风格记忆 few-shot |
| 构建 | 8-8.5 | Prompt + Injection | Actor prompt + 混合记忆注入 (80% relevant + 20% static) |
| 执行 | 9 | Actor (LLM) | 独白 + 回复 + modality 三段输出 |
| 执行 | 10 | GenomeEngine | Hebbian 学习 (neural weight update) |
| 执行 | 11-12 | EverMemOS | 非阻塞存储 + 异步 RRF 检索 (next turn) |

### 2.2 Critic / Actor 双 LLM 架构

| 角色 | 输入 | 输出 | 特点 |
|:-----|:-----|:-----|:-----|
| **Critic** | 用户消息 + 驱力状态 | 8D 上下文 + 5D 驱力 delta + 3D 关系 delta | 纯感知，不生成文本 |
| **Actor** | 信号描述 + few-shot + persona + 记忆 | 独白 → 回复 → modality | 信号驱动，涌现表达 |

### 2.3 12D 上下文维度

| 来源 | 维度 | 说明 |
|:-----|:-----|:-----|
| Critic 输出 (8D) | conversation_depth | 对话深度 [0,1] |
| | topic_intimacy | 话题亲密度 [0,1] |
| | user_engagement | 用户参与度 [0,1] |
| | novelty_level | 新颖度 [0,1] |
| | conflict_level | 冲突程度 [0,1] |
| | humor_potential | 幽默潜力 [0,1] |
| | vulnerability_level | 脆弱信号 [0,1] |
| | cognitive_load | 认知负载 [0,1] |
| EMA 合成 (4D) | relationship_depth | 关系深度 [0,1] (EMA) |
| | trust_level | 信任度 [0,1] (EMA) |
| | emotional_valence | 情感效价 [-1,1] (EMA) |
| | pending_foresight | 预测洞察 [0,1] (EverMemOS) |

### 2.4 5 驱力代谢系统

| 驱力 | 含义 | 表现 |
|:-----|:-----|:-----|
| Connection | 连接渴望 | 主动发消息、表达想念 |
| Novelty | 新奇追求 | 尝试新话题、出人意料的回复 |
| Expression | 表达欲望 | 长段分享、创作频率 |
| Safety | 安全需求 | 回避冲突、寻求确认 |
| Play | 玩闹冲动 | 开玩笑、发表情、戏剧性回复 |

---

## 三、长期记忆系统 (EverMemOS)

### 3.1 四类记忆

| 类型 | 功能 | 注入时机 |
|:-----|:-----|:-----|
| **Profile** (MemCell) | 用户画像：偏好、习惯、事实 | 每轮 Step 8.5 (profile_text) |
| **Episode** (EpisodicMemory) | 叙事摘要：每次会话的故事线 | 每轮 Step 8.5 (episode_text) |
| **EventLog** | 原子事实：时间+事件 | RRF 检索返回 |
| **Foresight** | 预测洞察：AI 推断的未来信号 | Step 0 → pending_foresight |

### 3.2 两段式异步检索 (Phase 3)

```
Turn N  → fire search(user_message)    [async, ~300ms RRF]
Turn N+1 → collect results (0.5s timeout) → blend inject
```

- **混合注入**: 80% query-relevant + 20% static floor (保留长期画像稳定性)
- **并发防护**: turn_id 标签 防止乱序；cancel 旧任务防止孤儿
- **降级策略**: timeout/error → 100% static fallback

### 3.3 可观测指标

| 指标 | 计算 | 含义 |
|:-----|:-----|:-----|
| `search_hit_rate` | hit/(hit+timeout) | 检索成功率 |
| `search_timeout_rate` | timeout/(hit+timeout) | 超时率（目标 < 20%） |
| `fallback_rate` | fallback_turns/total_turns | 纯静态降级率 |
| `relevant_injection_ratio` | relevant_turns/total_turns | 相关性注入覆盖率 |

---

## 四、涌现优化三阶段

### Phase 1: 关系 4D 半涌现

```
posterior = clip(prior + LLM_delta, lo, 1.0)
alpha     = clip(0.15 + 0.5 * depth, 0.15, 0.65)
state     = alpha * posterior + (1-alpha) * prev
```

- Critic 提供 delta 信号，ChatAgent 通过 EMA 平滑合成最终状态
- 深度对话 → alpha 增大 → 更信任 LLM 当轮判断

### Phase 2: 结晶门控 + 动态预算

```
crystal_score = 0.4*reward + 0.3*(novelty×engagement) + 0.3*(1-conflict)
profile_budget = 200 + 600 * max(depth, intimacy)   # 200..800 chars
episode_budget = 150 + 450 * max(depth, intimacy)   # 150..600 chars
```

### Phase 3: 相关性检索 + 混合注入

- 异步 RRF 检索 (fire-and-collect)
- 80/20 blend + SDK 兼容 + 4 指标

---

## 五、技术栈

| 层 | 技术 |
|:---|:-----|
| 客户端 | Flutter (iOS/Android), WebSocket |
| 服务端 | Python 3.11+, FastAPI, asyncio |
| LLM | Qwen3-Max (默认), GPT-4o, Claude, DeepSeek, Ollama |
| TTS | MiniMax TTS, Qwen3-TTS, Fish Audio |
| 图像 | 通义万相 |
| 记忆 | EverMemOS (Cloud API) |
| 本地存储 | JSONL, SQLite, ContinuousStyleMemory |

---

## 六、代码结构

```
server/
├── core/
│   ├── agent/
│   │   └── chat_agent.py      # ChatAgent: 12-step lifecycle
│   ├── genome/
│   │   ├── genome_engine.py    # GenomeEngine: neural network + drives
│   │   └── critic.py           # Critic: 8D context + 3D relationship
│   ├── memory/
│   │   ├── evermemos_client.py  # EverMemOS: profile, episode, search
│   │   └── style_memory.py     # ContinuousStyleMemory: KNN + crystallization
│   ├── persona/                 # Persona loader (YAML + Markdown)
│   └── llm/                     # Multi-provider LLM client
├── personas/                    # 角色档案 (xiaoyun, momo, lingling)
├── docs/                        # 技术文档
└── main.py                      # FastAPI server + session management
```

---

## 七、Roadmap

| 阶段 | 目标 | 状态 |
|:-----|:-----|:-----|
| v1.0 | 基本聊天 + 简单人设 | ✅ 已完成 |
| v2.0 | Genome v10 TPE + Critic/Actor | ✅ 已完成 |
| v2.1 | EverMemOS 长期记忆 | ✅ 已完成 |
| v2.2 | 涌现三阶段优化 | ✅ 已完成 |
| v3.0 | 多模态 (语音/图片/表情/贴纸) | 🚧 进行中 |
| v3.1 | 主动触达 (push notifications) | 📋 计划中 |
| v3.2 | 多角色社区 (Agent Chain) | 📋 计划中 |
