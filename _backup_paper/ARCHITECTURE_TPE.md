# Thermodynamic Persona Engine (TPE) — 完整架构手册

> 核心代码库：`/Users/zxw/AITOOL/tpe-engine/src/`
> 服务端集成：`/Users/zxw/AITOOL/openher/server/core/genome/`
> 论文原文：`/Users/zxw/AITOOL/openher/prototypes/paper/method.md`

## 一句话总结

TPE 是一个**物理隐喻的人格动力学系统**。它不告诉 LLM "你是温柔的"，而是通过随机神经网络实时计算行为信号，再翻译成具体的行为指令注入 LLM prompt。没有硬编码性格 — 所有人格从网络计算中涌现。

---

## 三层融合架构

```
Layer 1 — 驱力系统 (Drive System)
    5D frustration 向量，有自己的时间动力学
          ↓
Layer 2 — 随机神经网络 (Genome)
    [5D drive + 8D context + 8D recurrent] → 24 hidden → 8D signals
    权重随机初始化（DNA），Hebbian 学习持续进化
          ↓
Layer 3 — LLM 接口 (Prompt Injection)
    信号 → top-3 五档行为描述 + Drive 需求 + 矛盾检测
    + 引力记忆 few-shot → 注入 Actor prompt
          ↓
    Actor LLM → 回复
```

---

## Layer 1：驱力系统

> 文件：[genome_v4.py](file:///Users/zxw/AITOOL/tpe-engine/src/genome_v4.py#L50-L65)

### 5 种内在驱力

| Drive | 含义 | 类比 |
|-------|------|------|
| `connection` 🔗 | 想被理解、被记住 | 社交需求 |
| `novelty` ✨ | 想探索、想知道新东西 | 好奇心 |
| `expression` 💬 | 想说出自己的想法 | 表达欲 |
| `safety` 🛡️ | 想要稳定、可预期 | 安全感 |
| `play` 🎭 | 想逗乐、想撒娇 | 玩心 |

每个驱力有 3 个基因参数（随机初始化）：
- `drive_baseline` — 基础水平 (0.2~0.8)
- `drive_accumulation_rate` — 自然累积速率
- `drive_decay_rate` — 衰减速率

### 时间代谢（v8 新增）

> 文件：[genome_v8_timearrow.py](file:///Users/zxw/AITOOL/tpe-engine/src/genome_v8_timearrow.py#L139-L186)

两个时间方程在**交互之间**自动运行：

```
消气: frustration *= e^(-0.08 × Δt_hours)    半衰期 ≈ 8.7h
饥饿: connection.f += 0.15 × Δt_hours         孤独线性积累
      novelty.f    += 0.05 × Δt_hours         无聊线性积累
```

### 刺激响应

> 文件：[genome_v8_timearrow.py](file:///Users/zxw/AITOOL/tpe-engine/src/genome_v8_timearrow.py#L188-L211)

Critic LLM 从用户输入测量 3 维（人际环状模型）：
- `affiliation` (趋近力) — 拉近距离、示好
- `dominance` (支配力) — 施压、索取、控制
- `entropy` (信息熵) — 新信息含量

代数代谢规则（固定）：
```python
connection -= affiliation × 2.0    # 亲近减少孤独
connection += dominance × 0.8      # 施压增加不安
safety     += dominance × 1.5      # 施压威胁安全
novelty    += (0.5 - entropy) × 3.0  # 低信息增加无聊
```

Reward = 代谢前 total - 代谢后 total（frustration 减少量）

---

## Layer 2：随机神经网络

> 文件：[genome_v4.py](file:///Users/zxw/AITOOL/tpe-engine/src/genome_v4.py#L138-L210)

### 网络结构

```
输入层 (21D):
  [5D drive_state] + [8D context] + [8D recurrent_state]

隐藏层 (24 neurons):
  W1: 24×21, b1: 24    激活: tanh
  感知噪声: +N(0, 0.03)

输出层 (8D signals):
  W2: 8×24, b2: 8      激活: sigmoid → [0,1]
```

### 8D 行为调制信号

> 文件：[genome_v4.py](file:///Users/zxw/AITOOL/tpe-engine/src/genome_v4.py#L76-L95)

| Signal | 含义 | 0 端 | 1 端 |
|--------|------|------|------|
| `directness` | 直接度 | 委婉暗示 | 直说 |
| `vulnerability` | 坦露度 | 防御封闭 | 袒露脆弱 |
| `playfulness` | 玩闹度 | 认真严肃 | 玩闹撒娇 |
| `initiative` | 主动度 | 被动回应 | 主动引导 |
| `depth` | 深度 | 表面闲聊 | 深度对话 |
| `warmth` | 温暖度 | 冷淡疏离 | 热情关怀 |
| `defiance` | 倔强度 | 顺从 | 反抗嘴硬 |
| `curiosity` | 好奇度 | 无所谓 | 追问到底 |

**这些不是"性格标签"，是每轮实时计算的行为倾向。** 同一个 Agent 在不同上下文下信号组合完全不同。

### 8D 上下文特征（Critic 输出 → 映射）

> 文件：[genome_v4.py](file:///Users/zxw/AITOOL/tpe-engine/src/genome_v4.py#L105-L115)

```
user_emotion       -1=负面 → 1=正面
topic_intimacy     0=公事 → 1=私密
time_of_day        0=早晨 → 1=深夜
conversation_depth 0=刚开始 → 1=聊很久了
user_engagement    0=敷衍 → 1=投入
conflict_level     0=和谐 → 1=冲突
novelty_level      0=日常 → 1=全新话题
user_vulnerability 0=防御 → 1=敞开心扉
```

### Hebbian 学习

> 文件：[genome_v4.py](file:///Users/zxw/AITOOL/tpe-engine/src/genome_v4.py#L222-L289)

```python
lr = 0.005 × (1 + |reward|)

# W2 更新（输出层）:
ΔW2[i][j] = lr × reward × hidden[j] × (signal[i] - 0.5)

# W1 更新（隐藏层，仅 |reward| > 0.15 时）:
ΔW1[i][j] = lr × 0.3 × reward × input[j] × hidden[i]
```

### 相变机制

持续负反馈 → frustration 累积 → 超过 3.0 → **bias 大幅扰动**（信号翻转）

```python
if frustration > 3.0:
    b2[i] += -0.3 × (signal[i] - 0.5) + N(0, 0.15)  # 高的降低，低的升高
    b1[i] += N(0, 0.1)                                # 打破固定模式
    frustration = 0.0                                  # 释放
```

### 热力学噪声（v8）

> 文件：[genome_v8_timearrow.py](file:///Users/zxw/AITOOL/tpe-engine/src/genome_v8_timearrow.py#L89-L95)

```python
σ = 0.05 × total_frustration
signal_noisy = clip(signal + N(0, σ²), 0, 1)
```

**情绪越激动 → 行为越不可预测。**

---

## Layer 3：LLM 接口

### to_prompt_injection() — 信号→行为指令

> 文件：[genome_v4.py](file:///Users/zxw/AITOOL/tpe-engine/src/genome_v4.py#L352-L448)

**不注入数值，注入行为指令。** 每个信号有 5 档具体描述：

```
warmth 0.0~0.2: "冷淡疏离，语气冷冰冰的，不关心对方感受，甚至有点刻薄"
warmth 0.2~0.4: "比较冷淡，不太主动表达关心，回应简短"
warmth 0.4~0.6: "不冷不热，正常回应但不特别热情"
warmth 0.6~0.8: "温暖关心，语气柔和，会主动关心对方状态"
warmth 0.8~1.0: "非常热情体贴，嘘寒问暖，充满关怀和包容"
```

**只取 top-3 最偏离 0.5 的信号**（其余省略），加上：
- 最迫切的 Drive 需求（`你现在最需要的是🔗联结`）
- 内在矛盾检测（`你一方面想坦露，一方面又想倔强`）

### 注入到 Actor 的完整 prompt

> 文件：[chat_agent.py](file:///Users/zxw/AITOOL/openher/server/core/agent/chat_agent.py#L34-L51)

```
[System Internal State: Subconscious Memory Retrieved]
当前的底层神经化学递质坐标，唤醒了海马体中以下高度相似的潜意识与行为切片：

{few_shot}            ← 引力记忆检索的行为切片样本

{signal_injection}    ← to_prompt_injection() 输出的行为指令

{persona_section}     ← 角色人设 + 用户名

[Runtime Instruction]
你唯一的任务：完全沉浸并延续上述切片中的
【情绪浓度、用词习惯、攻击性、温度和字数长短】
```

---

## 引力记忆系统

> 文件：[style_memory.py](file:///Users/zxw/AITOOL/tpe-engine/src/style_memory.py)

### 结晶

每轮对话后，若 reward > 0.3，将 {信号向量, 内心独白, 回复文本} 存入记忆池：
- L2 距离 < 0.15 的已有记忆 → **质量+1**（引力增厚）
- 否则 → 新建记忆，初始质量 = 2.0

### 霍金辐射

```
mass_eff = 1.0 + (mass_raw - 1.0) × e^(-0.005 × Δt_hours)
```

半衰期 ≈ 5.8 天。基础质量 1.0 永不蒸发（先天基因记忆）。

### 引力检索

```
d_eff = ||query - memory_vector||₂ / √(mass_eff)
```

高质量记忆"弯曲"风格空间，吸引 Agent 重复成功模式。取 top-3 作为 few-shot。

---

## 完整 Per-Turn Pipeline

```
Step 1  ⏳ 时间代谢     frustration 衰减 + connection/novelty 饥饿
Step 2  👁️ Critic       LLM 测量用户输入 → (affiliation, dominance, entropy)
Step 3  🩸 代数代谢     Critic 三维 → frustration 5D 更新 → reward
Step 4  🧬 结晶门控     reward > 0.3 → 上一轮 {信号, 独白, 回复} 结晶入记忆
Step 5  🌡️ 信号计算     compute_signals(context) → 8D base signals
Step 6  🎲 热力学噪声   σ = 0.05 × F → 信号扰动
Step 7  🔭 引力检索     noisy_signals → KNN(mass-weighted) → top-3 few-shot
Step 8  📝 Actor Prompt  few_shot + signal_injection + persona → 完整 prompt
Step 9  🎭 Actor LLM    生成 【内心独白】+【最终回复】
Step 10 🧠 Hebbian      reward → W1/W2 权重更新 + frustration 累积/相变
```

---

## 多样性来源（完整）

| 来源 | 机制 | 影响什么 |
|------|------|---------|
| **种子不同** | 不同 W1/W2/b1/b2 初始化 | 先天人格差异 |
| **Drive 动力学** | frustration 时间衰减 + 饥饿累积 + 刺激响应 | 内部状态持续变化 |
| **Hebbian 进化** | 交互反馈修改权重 | 人格随经历进化 |
| **相变** | frustration > 3.0 → bias 翻转 | 人格突变 |
| **热力学噪声** | σ ∝ frustration | 情绪激动时行为不可预测 |
| **上下文不同** | 8D context features | 同一人不同场景不同信号 |
| **循环状态** | hidden[:8] 携带历史 | 对话心境连续性 |
| **引力记忆** | mass-weighted KNN | 成功模式被放大 |
| **霍金辐射** | 质量时间衰减 | 旧习惯逐渐被遗忘 |
| **to_prompt_injection** | top-3 行为指令 | LLM 按指令行动 |
| **few-shot 示例** | 具体的历史回复样本 | LLM 模仿风格锚点 |

**这些机制联合作用，产生持续变化又人格一致的行为输出。**

---

## TTS 集成点（待实现）

8D 信号已经描述了完整的**行为状态**。当前 `to_prompt_injection()` 的 5 档描述只覆盖了**文字层面的行为**（"说话绕弯子"、"语气冷冰冰"），但这些描述同样可以扩展到**语音层面**。

信号向量是 Agent 内部状态的完整表征 — 文字回复是一种输出通道，语音表达方式理应是同一个信号向量的另一种输出通道。
