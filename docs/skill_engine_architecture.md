# SkillEngine 统一改造架构说明

> 本文档记录 SkillEngine v9 的完整架构设计，包括 Stage 1（骨架 + 人格技能迁移）和 Stage 2（Task Skill 零侵入集成）。

---

## 1. 核心架构：双层 Skill

SkillEngine 将所有技能统一为 `SKILL.md` 格式，但运行时分为两条完全独立的执行路径：

| 维度 | 任务 Skill（Task） | 人格内敛 Skill（Intrinsic） |
|------|--------------------|-----------------------------|
| **trigger** | `tool` | `modality` |
| **典型例子** | weather、翻译、搜索、代码执行 | selfie_gen（自拍）、语音克隆 |
| **触发机制** | LLM function calling 路由（Step -1） | Express pass 涌现 modality（"照片"） |
| **执行器** | `sandbox_executor`（shell 命令） | Python handler（`handler_fn` 入口点） |
| **经过人格引擎** | ❌ early return | ✅ 完整 Critic→Feel→Express |
| **记忆写入** | `task.db`（隔离 SQLite） | EverMemOS + Hebbian |
| **回复生成** | `_express_wrap`（轻量 LLM 包装） | Express pass（完整人格表达） |
| **语义** | 用户要求"帮忙做的事" | 角色主动"想做的事" |

### 为什么要分两层

人格内敛 Skill 是 Express pass 涌现的结果——角色通过 Feel（内心活动）产生表达需求，Express 选择 modality（"照片"），然后触发 selfie_gen。这是角色自我表达的延伸，必须经过完整人格引擎。

任务 Skill 是纯工具执行，用户说"查天气"不需要角色"内心活动"，直接路由→执行→用角色口吻包装结果即可。如果强行走人格引擎，Critic/Feel/Express 处理"查天气"会产生无意义的内心活动和 Hebbian 学习记录。

---

## 2. 数据模型：L1/L2 渐进式加载

```
SKILL.md
├── YAML frontmatter (L1: 元数据) ← load_all() 批量加载
│   ├── name, description
│   ├── trigger: modality | tool | cron | manual
│   ├── executor: handler | sandbox
│   ├── handler_fn (Python 入口点)
│   └── modality (绑定的 Express modality)
└── Markdown body (L2: 指令) ← activate(skill_id) 按需加载
    └── 完整技能文档（handler 提示词 / shell 命令示例）
```

### 设计理由

- **L1 永远加载**：启动时读取所有 SKILL.md frontmatter，构建 `modality_skills` 映射和 `tool_skills` 列表
- **L2 按需加载**：body 可能很大（几 KB 的提示词），只在技能首次执行时加载
- **activate() 幂等**：重复调用不会重新读文件

### Skill dataclass 关键属性

```python
@dataclass
class Skill:
    skill_id: str          # 目录名
    name: str
    description: str       # L1 路由用（function calling description）
    trigger: str           # "modality" | "tool" | "cron" | "manual"
    modality: str          # Express modality 绑定（如 "照片"）
    executor: str          # "handler" | "sandbox"
    handler_fn: str        # Python 入口（如 "skills.selfie_gen.handler.generate_selfie"）
    body: Optional[str]    # L2 指令，None = 未激活

    @property
    def is_activated(self) -> bool:
        return self.body is not None
```

---

## 3. 执行路径

### Task Skill 端到端路径

```
"帮我看下北京天气"
  ↓
_chat_inner() [under turn_lock]
  ↓
Step -1: build_skill_declarations() → [{name:"weather", description:...}]
  ↓
LLM routing: chat([user_msg], tools=[...], tool_choice="auto")
  ↓ tool_calls: [{name:"weather"}]
skill_engine.execute("weather", user_intent, llm)
  ↓
  ├─ skill_id.lower() → 归一化大小写
  ├─ activate("weather") → 加载 body
  ├─ 空 body 检查
  ├─ LLM([system:技能文档, user:用户请求], temperature=0.1) → 生成 shell 命令
  ├─ re.sub 清洗 markdown code block
  ├─ 空命令检查
  └─ sandbox_executor.execute_shell(command, timeout=30)
  ↓
SkillExecutionResult(success=True, output={stdout, stderr, command})
  ↓
_express_wrap(result, user_message)
  ├─ LLM([system:persona_section[:500], user:工具输出+原话])
  └─ 三层兜底：content or stdout or "（查询完成）"
  ↓
_log_task → task.db (隔离)
  ↓
history 追加 + max_history 截断
  ↓
return {"reply": "北京今天22度晴天哦～", "modality": "文字"}
  ↓
Critic / Feel / Express / Hebbian / EVERMEMOS 从未执行 ✓
```

### 人格内敛 Skill 路径（对比）

```
Express pass 涌现 modality="照片"
  ↓
_execute_skill(skill, modality, persona_id, raw_output)
  ↓
动态 import handler_fn → 调用 generate_selfie(...)
  ↓
返回 image_path，走正常 Express 后续
  ↓
Hebbian 学习 + EverMemOS 记忆 ✓
```

---

## 4. Guard Clause 设计

```python
async def _chat_inner(self, user_message: str) -> dict:
    # ── Step -1: Task skill routing ──
    # 位置：_turn_count += 1 之前（所有人格引擎步骤之前）
    if self.skill_engine:
        skill_defs = self.skill_engine.build_skill_declarations()
        if skill_defs:
            # 路由 LLM 调用
            ...
            if routing_resp and routing_resp.tool_calls:
                # execute → express_wrap → return
                ...
                return {"reply": reply, "modality": "文字"}

    # ── Step 0: 人格引擎（零改动）──
    self._turn_count += 1
    ...
```

### 为什么在 _turn_count 之前

| 状态变量 | 工具路径是否更新 | 理由 |
|----------|----------------|------|
| `_turn_count` | ❌ 不递增 | EverMemOS `if _turn_count == 1` 仍正确触发于第一个人格轮次 |
| `_last_active` | ❌ 不更新 | 人格节奏 EMA 只统计人格轮次 |
| `_search_turn_id` | ❌ 不触碰 | 异步搜索并发保护不受影响 |

### 三层异常处理

```
第一层：路由 LLM 失败 → 静默回退人格引擎
第二层：execute() 失败 → result=None → 落穿到人格引擎
第三层：express_wrap() 失败 → 用 stdout 兜底，不丢弃已有数据
```

设计原则：**路由/执行失败 = 回退人格引擎**（用户不知道有 tool 尝试），**包装失败 = 给原始数据**（已拿到数据不应丢弃）。

---

## 5. 记忆隔离

```
chat.db (ChatLogStore)     ← 前端展示历史
task.db (TaskLogStore)     ← 工具执行记录（隔离）
EverMemOS                  ← 人格长期记忆（仅人格轮次写入）
agent.history              ← 工作记忆（工具轮和人格轮都写入，用于上下文）
Hebbian                    ← 人格学习（仅人格轮次触发）
```

`task.db` schema：

```sql
CREATE TABLE task_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    persona_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    user_input TEXT NOT NULL,
    command TEXT DEFAULT '',
    stdout TEXT DEFAULT '',
    stderr TEXT DEFAULT '',
    success INTEGER NOT NULL DEFAULT 0,
    reply TEXT DEFAULT '',
    created_at REAL NOT NULL
);
```

---

## 6. LLM Provider 扩展

```python
# ChatResponse 新增
tool_calls: Optional[list[dict]] = None  # [{name, arguments}]

# chat() 签名扩展
async def chat(self, messages, temperature=None, max_tokens=None,
               tools=None, tool_choice=None) -> ChatResponse
```

- 5 个 provider（DashScope/Moonshot/OpenAI/DeepSeek/Ollama）全部继承 `OpenAICompatProvider`，改一处全生效
- `if tools:` 空列表不传 API（兼容不支持 function calling 的 provider）
- `chat_stream()` 不改（streaming 不支持 tools，已知限制）

---

## 7. 文件清单

```
agent/skills/
├── __init__.py          # 只导出 SkillEngine
├── skill_engine.py      # 统一引擎（L1/L2 + build_skill_declarations + execute）
├── sandbox_executor.py  # [NEW] shell 命令沙盒执行
└── task_log_store.py    # [NEW] task.db 隔离存储

providers/llm/
├── base.py              # [MODIFY] ChatResponse.tool_calls + chat() tools
└── client.py            # [MODIFY] 透传 tools/tool_choice

skills/weather/
└── SKILL.md             # [MODIFY] trigger:tool + executor:sandbox

agent/chat_agent.py      # [MODIFY] guard clause + _express_wrap + _log_task
pytest.ini               # [NEW] asyncio_mode + testpaths
tests/test_skill_engine.py  # [MODIFY] +9 Stage 2 测试
```

---

## 8. 审查教训（10 轮 24 Bug）

| 教训 | 代表 Bug |
|------|---------|
| **所有 LLM 调用用 [system, user] 双消息** | Bug 1, 4: system-only 消息部分 provider 拒绝 |
| **工具路径必须有异常兜底** | Bug 6, 9: LLM 调用失败不能阻断人格引擎 |
| **边界值永远检查** | Bug 7, 15: 空命令、空 body 静默成功 |
| **大小写要归一化** | Bug 14: LLM 返回 "Weather" vs "weather" |
| **decode 要加 errors='replace'** | Bug 16: 非 UTF-8 输出会崩溃 |
| **测试需要 fixture + import** | Bug 17-19: 测试文件缺 fixture 定义和 import |
| **确定性任务用低温度** | Bug 21: 命令生成用 0.92 会不稳定 |
| **pytest 配置必须限制 testpaths** | Bug 20: vendor 测试会被误收集 |
