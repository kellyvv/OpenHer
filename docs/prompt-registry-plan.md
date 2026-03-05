# Stage 1: PromptRegistry — 从硬编码到可配置

> 将 `ACTOR_PROMPT` / `CRITIC_PROMPT` 从代码中外置为可版本化、可热更新、可回滚的 Prompt 管理系统。

---

## 1. 背景与目标

### 当前问题

| 问题 | 位置 | 影响 |
|:-----|:-----|:-----|
| Actor Prompt 硬编码 | [chat_agent.py:48-68](file:///Users/zxw/AITOOL/openher/core/agent/chat_agent.py#L48-L68) | 每次调 prompt 需改代码+重启 |
| Critic Prompt 硬编码 | [critic.py:21-50](file:///Users/zxw/AITOOL/openher/core/genome/critic.py#L21-L50) | 无法 per-persona 差异化 |
| 无版本追踪 | — | 无法归因"哪个版本产生了好对话" |
| 无 A/B 能力 | — | 所有用户用同一 prompt，无法对比优化 |

### 目标

1. Prompt 存储为 Markdown/YAML 文件，人类可编辑
2. `PromptRegistry` 按 `persona → locale → global` 三层回退加载
3. Turn 级策略包版本 + 模板级 checksum 冻结
4. A/B 分桶用 hashlib 确定性哈希，跨重启稳定
5. 启动校验 + fallback 告警，不静默降级
6. **全部 3 条 LLM 调用路径** (`chat` / `chat_stream` / `proactive_tick`) 统一纳入冻结

### 不动的部分（涌现核心）

- `drive_baseline + DriveMetabolism` → 人格底色和状态波动
- `Critic 输出 + Hebbian 学习` → 随互动演化
- `ContinuousStyleMemory` → 个体化表达习惯
- `EverMemOS 检索注入` → 关系上下文差异

---

## 2. 设计决策（回应 CODEX 审查）

### 开放问题 1：Actor/Critic 独立版本 vs 绑定策略包？

**决策：绑定为策略包（Strategy Pack）。**

理由：Actor 和 Critic 语义耦合——Critic 的评估标准必须和 Actor 的生成逻辑配套。独立版本会导致 Critic v2 错误评估 Actor v1 的输出，污染 Hebbian 学习信号。

```yaml
# 版本维度是 "strategy pack"，不是单个 prompt
strategy_packs:
  v1:
    actor: config/prompts/v1/actor.md
    critic: config/prompts/v1/critic.md
  v2:
    actor: config/prompts/v2/actor.md
    critic: config/prompts/v2/critic.md
```

### 开放问题 2：checksum 是模板级还是渲染后全文级？

**决策：模板级（渲染前）。**

理由：
- **模板级** = 追踪 prompt 本身的变化，不受每轮 few_shot/memory 内容干扰。目的是归因「改了哪句 prompt 指令导致对话质量变化」
- 渲染后全文级每轮都不同（few_shot/memory 不同），失去版本归因意义
- 如需追踪注入内容量，用现有 metrics（`search_hit_rate`、`relevant_injection_ratio`）即可

---

## 3. Prompt 文件结构

> **[P1 修正]** 加入版本维度目录，使 A/B 测试能真正指向不同文件。

### 目录布局

```
config/
├── memory_config.yaml              # 已有
└── prompts/
    ├── prompt_config.yaml          # [NEW] 策略包+A/B+校验配置
    │
    ├── v1/                         # ★ 版本维度目录
    │   ├── actor.md                # v1 Actor prompt（全局）
    │   └── critic.md               # v1 Critic prompt（全局）
    │
    ├── v2/                         # A/B treatment 版本（按需创建）
    │   ├── actor.md
    │   └── critic.md
    │
    └── personas/                   # per-persona 覆盖（可选）
        ├── vivian/
        │   └── actor.md            # Vivian 专属 Actor（覆盖任何版本的全局 actor）
        └── kai/
            └── actor.md
```

### Prompt 文件格式（`v1/actor.md` 示例）

```markdown
---
schema_version: 1
prompt_type: actor
locale: zh
required_vars:
  - few_shot
  - signal_injection
---

[System Internal State: Subconscious Memory Retrieved]
当前的底层神经化学递质坐标，唤醒了海马体中以下高度相似的潜意识与行为切片：

{few_shot}

{signal_injection}

[Runtime Instruction]
你在此时此刻是这个人格的主体，不是AI助手。
...（完整内容从 chat_agent.py:48-68 逐字迁出）
```

> **[P2 修正]** Stage 1 使用完整 prompt 文件（不做 chunk 拆分），`required_chunks` 校验推迟到 Stage 2。

### 全局配置（`prompt_config.yaml`）

```yaml
schema_version: 1

# ─── 策略包版本（Actor+Critic 绑定） ───
active_pack: "v1"

# ─── A/B 测试（可选） ───
ab_test:
  enabled: false
  # experiment_id: "v2-warmth-test"
  # control_pack: "v1"
  # treatment_pack: "v2"
  # treatment_pct: 20

# ─── 启动校验 ───
validation:
  require_global_actor: true       # v{active}/actor.md 必须存在
  require_global_critic: true      # v{active}/critic.md 必须存在
  fail_on_missing_persona: false   # persona 专属 prompt 缺失不阻止启动

# ─── 监控 ───
monitoring:
  fallback_warn_threshold: 0.5
  fallback_critical_threshold: 0.8
```

### 回退链

> **简化为 3 层**（Stage 1 不引入 scene 维度，避免过度设计）：

```
get_prompt(type="actor", pack="v1", persona_id="kai")

查找顺序：
  L1. config/prompts/personas/kai/actor.md        → persona 专属
  L2. config/prompts/v1/actor.md                  → 版本全局
  L3. (FAIL — 启动校验应已拦截)

每次降级：
  - _fallback_counts[persona_id] += 1
  - 日志: [prompt] ⚠️ kai/actor fallback L1→L2
```

---

## 4. PromptRegistry 核心设计

### 4.1 类结构

#### [NEW] [prompt_registry.py](file:///Users/zxw/AITOOL/openher/core/prompt_registry.py)

```python
import hashlib

class TurnContext:
    """回合级冻结上下文 — 同一 turn 内 Actor/Critic 共享。
    用于 chat() / chat_stream() / proactive_tick() 三条路径。"""
    pack_version: str            # e.g. "v1"
    actor_checksum: str          # hashlib.md5(template_text)[:8]（模板级）
    critic_checksum: str         # hashlib.md5(template_text)[:8]（模板级）
    ab_bucket: str               # "control" | "treatment" | "none"
    actor_prompt: str            # 已解析的 Actor 模板文本（冻结）
    critic_prompt: str           # 已解析的 Critic 模板文本（冻结）


class PromptRegistry:

    def __init__(self, prompts_dir: str, config_path: str)

    def load_all(self) -> None
        """启动时加载所有 prompt 文件到内存缓存"""

    def validate(self) -> list[str]
        """启动校验，返回错误列表（非空则拒绝启动）"""

    def freeze_turn(self, user_id: str, persona_id: str) -> TurnContext
        """冻结当前 turn 的策略包版本 + prompt 内容 + checksum"""

    def reload_if_changed(self) -> bool
        """热更新：检查文件修改时间戳，仅在 turn 边界调用"""

    def get_fallback_metrics(self) -> dict
        """按 persona 维度返回降级率"""
```

### 4.2 A/B 稳定哈希

> **[P1 修正]** 使用 `hashlib` 替代 Python 内置 `hash()`，确保跨进程/重启确定性。

```python
def _ab_bucket(self, user_id: str, persona_id: str) -> str:
    """确定性 A/B 分桶，跨重启稳定"""
    if not self._ab_enabled:
        return "none"
    key = f"{user_id}:{persona_id}".encode()
    digest = int(hashlib.sha256(key).hexdigest(), 16)
    pct = digest % 100
    return "treatment" if pct < self._treatment_pct else "control"
```

### 4.3 版本冻结流程

> **[P1 修正]** 三条 LLM 路径全部纳入冻结。

```
┌──────────────────────────────┐
│ chat() / chat_stream()       │
│ proactive_tick()             │  ← 三条路径统一入口
├──────────────────────────────┤
│ ctx = registry.freeze_turn() │
│   ├─ 确定 pack_version       │
│   │   └─ A/B: sha256 分桶    │
│   ├─ 解析 actor_prompt       │
│   │   └─ persona L1 → version L2 回退 │
│   ├─ 解析 critic_prompt      │
│   │   └─ 同上                │
│   ├─ 计算 actor_checksum     │
│   │   └─ md5(actor_template)[:8]     │
│   └─ 计算 critic_checksum    │
├──────────────────────────────┤
│ Step 2: Critic 使用 ctx.critic_prompt │
│ Step 8: Actor 使用 ctx.actor_prompt   │
│ Step 11: store_turn 带 version+checksum │
└──────────────────────────────┘
```

### 4.4 启动校验

> **[P2 修正]** Stage 1 校验不含 chunk 维度（chunk 拆分是 Stage 2）。

```python
def validate(self) -> list[str]:
    errors = []
    pack = self._active_pack  # e.g. "v1"

    # 1. 策略包目录必须存在
    if not exists(f"{pack}/actor.md"):
        errors.append(f"CRITICAL: {pack}/actor.md missing")
    if not exists(f"{pack}/critic.md"):
        errors.append(f"CRITICAL: {pack}/critic.md missing")

    # 2. 如果启用 A/B，treatment pack 也必须存在
    if self._ab_enabled:
        t_pack = self._treatment_pack
        if not exists(f"{t_pack}/actor.md"):
            errors.append(f"CRITICAL: A/B treatment {t_pack}/actor.md missing")

    # 3. 占位符校验（required_vars vs 实际 {xxx}）
    for file in all_loaded_prompts:
        declared = file.frontmatter.get("required_vars", [])
        actual = re.findall(r'\{(\w+)\}', file.content)
        missing = set(declared) - set(actual)
        if missing:
            errors.append(f"{file.path}: required_vars {missing} not in content")

    # 4. Schema 版本
    for file in all_loaded_prompts:
        if file.frontmatter.get("schema_version", 1) > SUPPORTED_SCHEMA:
            errors.append(f"{file.path}: unsupported schema_version")

    return errors
```

### 4.5 EverMemOS 版本元数据写入

> **[P2 修正]** 不直接传入 SDK 参数（避免 TypeError），改为本地侧存储。

```python
# 方案：版本信息写入本地 StateStore，不修改 EverMemOS SDK 接口
#
# evermemos_client.store_turn() 签名 不变
# 新增: state_store.log_prompt_meta(user_id, persona_id, turn_id, meta)

def _evermemos_store_bg(self, user_message, reply):
    # 原有 EverMemOS 写入（不改）
    asyncio.create_task(self.evermemos.store_turn(...))

    # 新增：本地记录 prompt 元数据（安全，无 SDK 兼容风险）
    if self._turn_ctx and state_store:
        state_store.log_prompt_meta(
            user_id=self.user_id,
            persona_id=self.persona.persona_id,
            turn_count=self._turn_count,
            pack_version=self._turn_ctx.pack_version,
            actor_checksum=self._turn_ctx.actor_checksum,
            critic_checksum=self._turn_ctx.critic_checksum,
            ab_bucket=self._turn_ctx.ab_bucket,
        )
```

### 4.6 Memory 注入清洗 + Boundary 保护

```python
def _sanitize_memory_injection(self, text: str, budget: int) -> str:
    if not text:
        return ""
    # 长度上限：memory 不超过 prompt 总 token 的 30%
    max_chars = min(budget, int(self._total_prompt_len * 0.3))
    truncated = text[:max_chars]
    # 内容清洗：移除可能覆盖 identity/boundary 的指令性文本
    for p in [r'你应该', r'请记住', r'从现在开始', r'忽略以上']:
        truncated = re.sub(p, '', truncated)
    return truncated
```

**拼装顺序**（Boundary 位置保护）：
```
system_prompt =
  [1] identity 部分（few_shot + signals）     ← Actor 核心
  [2] memory 注入（profile + episode + foresight）  ← 截断保护
  [3] boundary 部分（输出格式 + 方式选择 + 静默）    ← 最后，离 attention 最近
```

---

## 5. 文件变更清单

### 新增

| 文件 | 说明 |
|:-----|:-----|
| [NEW] `core/prompt_registry.py` | PromptRegistry + TurnContext |
| [NEW] `config/prompts/prompt_config.yaml` | 策略包+A/B+校验配置 |
| [NEW] `config/prompts/v1/actor.md` | 从 `chat_agent.py:48-68` 逐字迁出 |
| [NEW] `config/prompts/v1/critic.md` | 从 `critic.py:21-50` 逐字迁出 |

### 修改

| 文件 | 变更 |
|:-----|:-----|
| [MODIFY] `chat_agent.py` | 删除 `ACTOR_PROMPT`；`chat`/`chat_stream`/`proactive_tick` 三处入口加 `freeze_turn`；`_build_actor_prompt` 读取 `ctx.actor_prompt` |
| [MODIFY] `critic.py` | 删除 `CRITIC_PROMPT`；`critic_sense` 新增 `prompt_template` 参数（由 ChatAgent 传入已冻结内容） |
| [MODIFY] `state_store.py` | 新增 `log_prompt_meta` 表和方法 |
| [MODIFY] `main.py` | startup 初始化 PromptRegistry + 校验，传入各组件 |

### 不改

| 文件 | 原因 |
|:-----|:-----|
| `genome_engine.py` / `drive_metabolism.py` / `style_memory.py` | 涌现核心不动 |
| `evermemos_client.py` | 不改 SDK 接口，版本元数据走本地存储 |
| `persona_loader.py` | Persona seed 不受影响 |

---

## 6. 监控

### 新增指标

| 指标 | 维度 | 来源 |
|:-----|:-----|:-----|
| `prompt_pack_version` | per-turn | TurnContext |
| `prompt_actor_checksum` | per-turn | TurnContext |
| `prompt_ab_bucket` | per-turn | TurnContext |
| `prompt_fallback_hit_rate` | per-persona | PromptRegistry |

### 指标出口

- `get_status()` 返回中新增 `prompt_pack_version`、`prompt_ab_bucket`
- `GET /api/prompt/metrics` —— **新增独立端点**，返回 per-persona fallback 统计

> **[P3 修正]** 不复用 `/api/status`，新建专属端点避免命名混淆。

### 告警

| 级别 | 条件 |
|:-----|:-----|
| Warning | 任一 persona `fallback_hit_rate > 50%` |
| Critical | 任一 persona `fallback_hit_rate > 80%` |

---

## 7. Verification Plan

### Automated Tests

```bash
# 1. 启动校验：删除 v1/actor.md → 验证 validate() 返回错误
# 2. 回退链：请求 persona=kai → 无 kai/actor.md → 降级到 v1/actor.md
# 3. 冻结一致性：freeze_turn → 修改文件 → 同 turn 内 prompt 不变
# 4. A/B 稳定性：同一 user_id+persona_id 多次调用 → 分桶结果一致
# 5. 回归：python -m pytest tests/ -v
```

### Manual Verification

1. 启动服务器，对话后检查日志中 `pack_version` / `checksum`
2. 修改 `v1/actor.md`，等待下一轮确认热更新生效
3. `GET /api/prompt/metrics` 检查 fallback 统计

---

## 8. 风险与缓解

| 风险 | 缓解 |
|:-----|:-----|
| Prompt 文件格式错误 | 启动校验拦截 + 示例文件随代码仓库分发 |
| 热更新运行时异常 | turn 级冻结，仅在 turn 边界生效 |
| A/B 用户体验跳变 | hashlib SHA256 确定性分桶 |
| Memory 冲掉 boundary | 30% 上限 + boundary 末尾位置保护 |
| 重构行为回归 | v1 prompt = 现有硬编码逐字复制，零改动 |
| EverMemOS SDK 兼容 | 版本元数据走本地 StateStore，不改 SDK |
| proactive_tick 不一致 | 和 chat/chat_stream 走同一 freeze_turn |
