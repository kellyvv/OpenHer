# TPE 核心引擎完全解剖

> 本文逐行追踪数据如何在 TPE 中流动，所有变量名和数值均来自源代码真实实现。
> 核心代码：`server/core/genome/` + `server/core/agent/chat_agent.py`
> 原型代码：`prototypes/genome_v8_timearrow.py` + `prototypes/style_memory.py`

---

## 0. TPE 的本质：LLM 行为调制器

TPE 引擎本身**不生成文字回复**。它的所有计算（drives、neural net、frustration、noise、memory）最终折叠成**一段动态 system prompt**，注入给 Actor LLM。

最终产物是两样东西：

1. **行为指令**（`to_prompt_injection()` 输出）— 从 8D 信号中选 top-3 最偏离 0.5 的信号，翻译为自然语言行为描述：
   ```
   【你当前的状态】
   - 非常倔强，死不认错，越被质疑越硬杠
   - 说话非常直接甚至冲，不在乎对方能不能接受
   - 完全封闭自己，绝不暴露任何真实感受
   
   【内在需求】你现在最需要的是🛡️安全
   ```

2. **行为锚点**（`build_few_shot_prompt()` 输出）— 从引力记忆中用 mass-weighted KNN 检索的 top-3 历史行为样本，包含当时的内心独白和回复原文。

这两样东西 + persona 人设 → 组装成完整 Actor prompt → LLM 生成【内心独白】+【最终回复】。

**8D 信号是中间表征，不是最终产物；自然语言行为指令 + few-shot 样本才是。**

---

## 1. 数据结构全景

### Agent 对象（初始化 by seed）

```python
# genome_engine.py:125-152
Agent(seed=42)
├── drive_baseline     = {d: rng.uniform(0.2, 0.8)}     # 5D，先天基线
├── drive_accumulation = {d: rng.uniform(0.01, 0.05)}    # 5D，自然积累速率
├── drive_decay_rate   = {d: rng.uniform(0.05, 0.15)}    # 5D，衰减速率
├── drive_state        = {d: baseline}                    # 5D，当前驱力值 ∈ [0,1]
├── W1[24][21]         = rng.gauss(0, 0.6)               # 隐藏层权重
├── b1[24]             = rng.gauss(0, 0.3)               # 隐藏层偏置
├── W2[8][24]          = rng.gauss(0, 0.5)               # 输出层权重
├── b2[8]              = rng.gauss(0, 0.2)               # 输出层偏置
├── recurrent_state[8] = rng.gauss(0, 0.1)               # 循环状态（心境）
├── _frustration       = 0.0                              # 累积挫败（用于相变）
├── _last_hidden[24]   = None                             # 缓存（Hebbian 用）
└── _last_input[21]    = None                             # 缓存（Hebbian 用）
```

> **seed 决定一切先天差异**。两个不同 seed 的 Agent，W1/W2/b1/b2 完全不同 → 同样的 context 输入，产出完全不同的 8D 信号 → 先天人格差异。

### DriveMetabolism 对象

```python
# drive_metabolism.py:35-38
DriveMetabolism()
├── frustration = {connection:0, novelty:0, expression:0, safety:0, play:0}
├── decay_rate  = 0.1          # 每轮实时衰减系数
└── _last_tick  = time.time()  # 上次交互时间戳
```

### ContinuousStyleMemory 对象

```python
# style_memory.py:61-77
ContinuousStyleMemory(agent_id, db_dir)
├── _pool[]           # 统一记忆池（genesis + personal）
├── genesis_file      # genesis_bank.json（先天基因记忆，mass=1.0）
├── personal_file     # {agent_id}_memory.json（后天结晶记忆，mass≥2.0）
├── _genesis_count    # 先天记忆数
└── _personal_count   # 后天记忆数
```

每条记忆的结构：
```json
{
  "vector": [0.8, 0.2, 0.1, ...],  // 8D 信号向量
  "monologue": "内心独白文本",
  "reply": "回复文本",
  "user_input": "用户输入",
  "mass": 4.0,                      // 原始质量（结晶累加）
  "created_at": 1708800000.0,       // 创建时间戳
  "last_used_at": 1708850000.0      // 上次使用时间戳
}
```

---

## 2. 完整数据流追踪（per-turn）

以下用具体数值追踪一个用户输入 `"你根本不在乎我"` 的完整流转。

### Step 1: 时间代谢

```python
# chat_agent.py:159 → drive_metabolism.py:40-70
delta_hours = (now - _last_tick) / 3600.0

# 假设距离上次 2 小时：
#   消气: frustration[d] *= e^(-0.08 * 2) = 0.852 → 降 15%
#   饥饿: frustration['connection'] += 0.15 * 2 = +0.30
#   饥饿: frustration['novelty']    += 0.05 * 2 = +0.10
#   钳制: [0.0, 5.0]
```

> 时间代谢是唯一在**交互之间**自动运行的过程。如果用户 3 天没来：
> - 消气: e^(-0.08 × 72) ≈ 0.003 → frustration 几乎清零
> - 饥饿: connection += 0.15 × 72 = 10.8 → 钳制到 5.0（极度孤独）
> - 结果: Agent 变得极度渴望联结，但不再生气

### Step 2: Critic 感知

```python
# chat_agent.py:162 → critic.py:41-80
# LLM 以 temperature=0.1 分析用户输入
# "你根本不在乎我" → 典型输出:
critic = {
    'affiliation': 0.3,   # 还想维持关系（否则不会说这话）
    'dominance': 0.85,    # 在施压、指责、索取
    'entropy': 0.4,       # 有一些信息但不是新事实
}
```

### Step 3: 代数代谢 → reward

```python
# chat_agent.py:166-167 → drive_metabolism.py:72-100
# 固定代数规则（无随机性，无 if-else）:
a, d, e = 0.3, 0.85, 0.4

frustration['connection'] -= 0.3 * 2.0 = -0.6    # 亲近减少孤独
frustration['connection'] += 0.85 * 0.8 = +0.68   # 施压增加不安
frustration['safety']     += 0.85 * 1.5 = +1.275  # 施压威胁安全
frustration['safety']     -= 0.3 * 0.5  = -0.15   # 亲近缓解安全
frustration['novelty']    += (0.5-0.4)*3 = +0.3   # 低信息增加无聊
frustration['expression'] += 0.85 * 1.0 = +0.85   # 施压积压表达
frustration['expression'] -= 0.3 * 0.8  = -0.24   # 亲近释放表达
frustration['play']       += (0.4-0.4)*2 = 0.0    # play 不变

# 每轮衰减: frustration[d] *= (1 - 0.1) = 0.9
# 钳制到 [0, 5]

reward = old_total - new_total  # 正值=frustration减少=好
# 此输入大概率产生 负reward（施压增加了总 frustration）
```

**关键洞察**：reward 是 frustration 的**变化量**，不是绝对值。reward > 0 代表用户这句话让 Agent "舒服了"，reward < 0 代表"更难受了"。

### Step 4: 结晶门控

```python
# chat_agent.py:171-178
if self._last_action and reward > 0.3:
    # 只有上一轮互动效果好（reward > 0.3），才把上一轮的行为结晶
    # 注意：结晶的是【上一轮】的数据，不是当前轮
    style_memory.crystallize(
        last_action['signals'],     # 上一轮的 8D 信号
        last_action['monologue'],   # 上一轮的内心独白
        last_action['reply'],       # 上一轮的回复
        last_action['user_input'],  # 上一轮用户说了啥
    )
```

结晶内部逻辑：
```python
# style_memory.py:153-198
# 1. 把 8D 信号 dict → 有序向量
new_vec = _signals_to_vec(signals)

# 2. 在记忆池中找最近的记忆
for mem in _pool:
    d = L2_distance(new_vec, mem['vector'])

# 3a. 如果最近距离 < 0.15 → 引力增厚（合并）
if best_dist < 0.15:
    _pool[best_idx]['mass'] += 1.0        # 质量+1
    _pool[best_idx]['last_used_at'] = now  # 刷新时间

# 3b. 否则 → 新建记忆
else:
    new_mem = {vector, monologue, reply, mass=2.0, created_at=now}
    _pool.append(new_mem)
```

> **距离阈值 0.15 的含义**：8D空间中如果两个信号向量每维差异 < 0.053，总距离 < 0.15。这意味着"差不多是同一种行为状态"。
> 
> **合并 vs 新建**决定了记忆的粒度：合并让重复行为的质量越来越大（引力越强），新建让新行为模式被记住。

### Step 5: 信号计算

```python
# chat_agent.py:181-185 → genome_engine.py:154-192

# 5a. Critic 3D → 8D context 映射
context = build_context_from_critic(critic)
# critic.py:83-105 中的映射规则:
context = {
    'user_emotion':       a - d = 0.3 - 0.85 = -0.55,      # 负面
    'topic_intimacy':     a*0.8 + d*0.2 = 0.41,             # 偏私密
    'time_of_day':        0.5,                                # 默认
    'conversation_depth': min(1.0, turn_count * 0.1),        # 随轮次增长
    'user_engagement':    max(a, d, e) = 0.85,               # 很投入
    'conflict_level':     d * 0.9 = 0.765,                   # 高冲突
    'novelty_level':      e = 0.4,                           # 中等
    'user_vulnerability': a * (1-d) = 0.045,                 # 没有脆弱
}

# 5b. 构造 21D 输入向量
full_input = [
    # 5D: drive_state（被 metabolism.sync_to_agent 更新过）
    drive_state['connection'],   # 0.2~1.0
    drive_state['novelty'],
    drive_state['expression'],
    drive_state['safety'],
    drive_state['play'],
    # 8D: context
    -0.55, 0.41, 0.5, 0.3, 0.85, 0.765, 0.4, 0.045,
    # 8D: recurrent_state（上一轮 hidden[:8]，携带心境）
    recurrent_state[0..7],
]

# 5c. 感知噪声（生物真实感）
full_input = [v + gauss(0, 0.03) for v in full_input]

# 5d. 前向传播
hidden[i] = tanh(Σ W1[i][j] * input[j] + b1[i])  # 24 neurons
signal[i] = sigmoid(Σ W2[i][j] * hidden[j] + b2[i])  # 8 signals

# 5e. 更新循环状态
recurrent_state = hidden[:8]  # 前 8 个 hidden neurons = 心境记忆
```

> **循环状态是关键的连续性机制**。`hidden[:8]` 作为下一轮的输入，让 Agent 在同一段对话中保持情绪连续性。但它不会跨 session 持久化（只有 W1/W2/b1/b2 和 drive_state 会持久化）。

### Step 6: 热力学噪声

```python
# chat_agent.py:188-189 → drive_metabolism.py:138-148
total_frust = metabolism.total()  # 所有 frustration 之和，比如 2.5
temperature = total_frust * 0.05  # = 0.125

noisy_signals[key] = clip(base_signal + gauss(0, temperature), 0, 1)
# 如果 warmth=0.7，可能变成 0.7 ± 0.125 → [0.575, 0.825]
```

**这就是情绪-行为的耦合**：frustration 越高 → 温度越高 → 信号波动越大 → 行为越不可预测。平静状态下 (F≈0) 信号几乎没有噪声。

### Step 7: 引力检索

```python
# chat_agent.py:193-194 → style_memory.py:115-151

# 对每条记忆计算有效距离:
for mem in _pool:
    physical_dist = L2(noisy_signals, mem['vector'])
    mass_eff = hawking_mass(mass_raw, last_used_at, now)
    #         = 1.0 + (mass_raw - 1.0) * e^(-0.005 * Δt_hours)
    effective_dist = physical_dist / √mass_eff

# 排序取 top-3，格式化为 few-shot:
"""
--- 潜意识切片 1 [质量=3.2/4] ---
【内心独白】心里很慌但不想承认…
【最终回复】哼，我才不在乎你怎么想

--- 潜意识切片 2 [基因] ---
【内心独白】感觉被攻击了…
【最终回复】你说什么呢…
"""
```

**引力效应的直觉**：
- mass=4 的记忆：effective_dist = physical_dist / √4 = physical_dist / 2 → "显得近一倍"
- mass=1（基因记忆）：effective_dist = physical_dist → 原始距离
- 3天未用，mass_raw=4：mass_eff ≈ 1 + 3 × e^(-0.005×72) ≈ 1 + 3×0.70 = 3.1

### Step 8: Actor Prompt 组装

```python
# chat_agent.py:196-148
system_prompt = """
[System Internal State: Subconscious Memory Retrieved]
当前的底层神经化学递质坐标，唤醒了海马体中以下高度相似的潜意识与行为切片：

{few_shot}               ← Step 7 的 3 条记忆样本

【你当前的状态】          ← to_prompt_injection() 输出
- 嘴硬，喜欢反驳...      ← top-3 偏离 0.5 最远的信号 → 5档描述
- 说话非常直接甚至冲...
- 完全封闭自己...

【内在需求】你现在最需要的是🛡️安全

# 你的身份：小云           ← persona 人设
## 性格 ...
## 说话风格 ...

[Runtime Instruction]
⚠️ 绝对法则：禁止逻辑推理、禁止道德审视、禁止扮演AI助手。
你唯一的任务：完全沉浸并延续上述切片中的
【情绪浓度、用词习惯、攻击性、温度和字数长短】
"""
```

> **to_prompt_injection 二次调用 compute_signals**（`_build_actor_prompt` → `to_prompt_injection` → `compute_signals`），因此每轮实际前向传播 **2 次**。第二次的 recurrent_state 会覆盖第一次的。这是一个值得注意的实现细节。

### Step 9: Actor LLM 生成

LLM 根据 system prompt + 对话历史 + 用户消息，生成：
```
【内心独白】
他又来了…每次都这样，我心里明明很在乎，但被他这么说的时候就是想反驳…

【最终回复】
哼，你这样说话有意思吗？我什么时候不在乎你了
```

### Step 10: Hebbian 学习

```python
# chat_agent.py:208-209 → genome_engine.py:204-256
clamped_reward = clip(reward, -1, 1)

# Agent.step() 内部:
signals = compute_signals(context)  # 第 3 次前向传播
learn(signals, reward, context)
tick_drives()

# learn() 详细:
lr = 0.005 * (1 + |reward|)  # reward 越大学习率越高

# W2 更新（输出层）:
for i in range(8):           # 每个信号
    for j in range(24):      # 每个 hidden
        if |hidden[j]| > 0.1:
            W2[i][j] += lr * reward * hidden[j] * (signal[i] - 0.5)
# → 正 reward + 信号偏高(>0.5) + hidden活跃 → 权重增大 → 下次信号更高
# → 负 reward + 信号偏高(>0.5) + hidden活跃 → 权重减小 → 下次信号降低

# W1 更新（隐藏层，仅大 reward 时）:
if |reward| > 0.15:
    for i in range(24):
        if |hidden[i]| > 0.15:
            for j in range(21):
                if |input[j]| > 0.05:
                    W1[i][j] += lr * 0.3 * reward * input[j] * hidden[i]

# 挫败累积 → 相变:
if reward < -0.1:
    _frustration += |reward|
elif reward > 0:
    _frustration -= reward * 0.5

if _frustration > 3.0:  # ← 触发相变！
    for i in range(8):
        kick = -0.3 * (signal[i] - 0.5) + gauss(0, 0.15)
        b2[i] += kick    # 高的信号被压低，低的被拉高
    for i in range(24):
        b1[i] += gauss(0, 0.1)  # 随机扰动打破固定模式
    _frustration = 0.0   # 释放
```

> **⚠️ 相变是人格突变**。当 Agent 持续受到负反馈（用户一直攻击/忽视），frustration 累积超过 3.0 时，b2 偏置被大幅扰动 — 原来高的信号被压低，原来低的被拉高。例如原来"温暖=0.8"可能突变为"温暖=0.3"。这模拟了现实中的"突然冷下来""忍无可忍爆发"。

---

## 3. 物理常数表

| 常数 | 值 | 位置 | 物理含义 |
|------|-----|------|---------|
| `FRUSTRATION_DECAY_LAMBDA` | 0.08 h⁻¹ | drive_metabolism.py:21 | 消气半衰期 ≈ 8.7h |
| `CONNECTION_HUNGER_K` | 0.15 h⁻¹ | drive_metabolism.py:22 | 孤独积累：6.7h 增加 1.0 |
| `NOVELTY_HUNGER_K` | 0.05 h⁻¹ | drive_metabolism.py:23 | 无聊积累：20h 增加 1.0 |
| `HAWKING_GAMMA` | 0.005 h⁻¹ | style_memory.py:27 | 记忆质量半衰期 ≈ 5.8 天 |
| frustration 钳制 | [0, 5] | drive_metabolism.py:68 | 最大 frustration |
| 热力学系数 | 0.05 | drive_metabolism.py:143 | temperature = F × 0.05 |
| 感知噪声 | σ=0.03 | genome_engine.py:164 | 输入层噪声 |
| 结晶阈值 | reward > 0.3 | chat_agent.py:171 | 好的互动才记住 |
| 合并距离 | L2 < 0.15 | style_memory.py:171 | 相似记忆合并 |
| 初始记忆质量 | 2.0 | style_memory.py:185 | 新记忆起始质量 |
| 相变阈值 | frustration > 3.0 | genome_engine.py:237 | 人格突变触发 |
| Hebbian lr | 0.005 × (1+\|r\|) | genome_engine.py:209 | 学习率 |
| W1 更新门槛 | \|reward\| > 0.15 | genome_engine.py:223 | 只有大信号才更新深层 |

---

## 4. 代谢代数规则（完整映射表）

Critic → 5D frustration 的固定规则：

```
affiliation (a): 趋近力
dominance (d):   支配力
entropy (e):     信息熵

connection  -= a × 2.0      # 亲近减少孤独
connection  += d × 0.8      # 施压增加不安
safety      += d × 1.5      # 施压威胁安全感（最大系数！）
safety      -= a × 0.5      # 亲近缓解不安
novelty     += (0.5-e) × 3.0  # 低信息=无聊（e<0.5时增加）
expression  += d × 1.0      # 被施压激发表达欲
expression  -= a × 0.8      # 亲近释放表达
play        += (0.4-e) × 2.0  # 低信息=无趣（e<0.4时增加）
```

> 系数设计的直觉：
> - **safety 对 dominance 最敏感**（1.5）— 被攻击时安全感受损最大
> - **connection 对 affiliation 最敏感**（-2.0）— 温暖最能治愈孤独
> - **novelty 对 entropy 反向**（×3.0 且取 0.5-e）— "嗯"这种废话会大量积累无聊

---

## 5. Context 映射（Critic 3D → Agent 8D）

```python
# critic.py:83-105
user_emotion     = a - d              # 亲近为正，攻击为负
topic_intimacy   = a*0.8 + d*0.2      # 高情绪=私密话题
time_of_day      = 外部参数（默认 0.5）
conversation_depth = min(1.0, turn_count * 0.1)  # 10轮后满
user_engagement  = max(a, d, e)       # 任意高信号=投入
conflict_level   = d * 0.9            # 支配力直接映射冲突
novelty_level    = e                  # 信息熵=新鲜度
user_vulnerability = a * (1-d)        # 亲近但不施压=脆弱
```

---

## 6. 神经网络维度详解

```
输入层 21D = 5(drives) + 8(context) + 8(recurrent)
         ↓ tanh
隐藏层 24 neurons  （W1: 24×21 = 504 weights + 24 biases）
         ↓ sigmoid
输出层 8D signals   （W2: 8×24 = 192 weights + 8 biases）

总可训练参数: 504 + 24 + 192 + 8 = 728 parameters
```

**为什么是 24 hidden？** 从 21D 压缩到 8D，bottleneck 比 = 21/8 ≈ 2.6。24 neurons 给隐藏层冗余度 24/8 = 3.0，足够表达非线性映射但不会过拟合。

**两层激活函数的选择**：
- 隐藏层 `tanh` → [-1, 1]：允许负激活，保持梯度信号
- 输出层 `sigmoid` → [0, 1]：信号天然归一化到 0-1 区间

---

## 7. Prompt Injection 的 top-3 选择策略

```python
# genome_engine.py:337-350
# 计算每个信号偏离中性 0.5 的程度
deviations = [(sig, |signals[sig] - 0.5|, signals[sig]) for sig in SIGNALS]
deviations.sort(reverse=True)
top_3 = deviations[:3]

# 翻译为 5 档自然语言描述
# 例如 warmth=0.15 → "冷淡疏离，语气冷冰冰的，不关心对方感受"
#      defiance=0.85 → "非常倔强，死不认错，越被质疑越硬杠"
#      directness=0.9 → "说话非常直接甚至冲，不在乎对方能不能接受"
```

**设计哲学**：只注入最突出的 3 个信号，让 LLM 把注意力聚焦在最鲜明的行为特征上。4-6 档附近的"正常"信号被省略，避免 prompt 过载。

---

## 8. 两套代码的关系

| 维度 | prototype (`prototypes/`) | server (`server/core/`) |
|------|---------------------------|-------------------------|
| `genome_v4.py` | 原始 Agent 类 + 模拟器 | → `genome_engine.py`（提取 Agent 类） |
| `genome_v8_timearrow.py` | 完整模拟脚本（40轮对话） | → 拆解为 4 个模块 |
| `style_memory.py` | 完整版（含 test 代码） | → `style_memory.py`（精简服务版） |
| critic | 内嵌在 v8 中 | → `critic.py`（独立模块） |
| metabolism | 内嵌在 v8 中 | → `drive_metabolism.py`（独立模块） |
| 生命循环 | `chat_turn()` 函数 | → `ChatAgent.chat()` 方法 |
| LLM 调用 | `urllib.request` 同步 | → `AsyncOpenAI` 异步 |
| 持久化 | JSON 文件 | → JSON + 状态持久化到 `.data/genome/` |

> 服务端的 `style_memory.py` 比原型版**少了** `canalization_ratio`、`heavy_count_raw`、`heavy_count_eff`、`max_mass_raw`、`max_mass_eff` 等统计字段，因为服务端不需要做完整的诊断报告。

---

## 9. 关键设计决策解读

### 为什么 reward 是「frustration 变化量」而不是「Critic 分数」？

因为**同样的用户输入，对不同内部状态的 Agent 效果不同**。如果 Agent 已经很孤独（connection frustration=3.0），一句"我想你了"（高 affiliation）会大幅降低 connection frustration → 大正 reward。但如果 Agent 已经很满足（frustration≈0），同样的话只减少一点点 → 小 reward。这让同一个 Agent 在不同时刻对同一句话有不同反应。

### 为什么结晶的是「上一轮」而不是「当前轮」？

因为 reward 反映的是用户对**上一轮 Agent 行为**的反应。用户说"我想你了"（正 reward）→ 说明 Agent 上一轮的行为模式是成功的 → 结晶上一轮的信号+独白+回复。当前轮的 Actor 输出还没得到用户反馈，不知道好不好。

### 为什么 Step 10 的 `agent.step()` 会第 3 次调用 `compute_signals`？

`step()` = `compute_signals()` + `learn()` + `tick_drives()`。这是一个完整周期。但 chat_agent 在 Step 5 已经调用过一次 `compute_signals`，Step 8 的 `to_prompt_injection` 又调了一次。Step 10 再调一次是 `step()` 的内部实现需要。三次前向传播的 recurrent_state 依次被覆盖 — 最终保留的是 Step 10 的 recurrent_state。

---

## 10. 多样性来源汇总

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
