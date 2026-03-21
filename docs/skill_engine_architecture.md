# SkillEngine 统一改造架构说明

> 本文档记录 SkillEngine v10 的完整架构设计，包括双层 Skill 模型、Task Skill 注入引擎模式、人格内敛 Skill 路径。

---

## 1. 核心架构：双层 Skill

SkillEngine 将所有技能统一为 `SKILL.md` 格式，运行时分为两条执行路径：

| 维度 | 任务 Skill（Task） | 人格内敛 Skill（Intrinsic） |
|------|--------------------|---------------------------|
| **trigger** | `tool` | `modality` |
| **典型例子** | weather、翻译、搜索、汇率 | selfie_gen（自拍）、语音克隆 |
| **触发机制** | LLM function calling 路由（Step -1） | Actor 输出涌现 modality（"照片"） |
| **执行器** | `sandbox_executor`（shell 命令） | Python handler（`handler_fn` 入口点） |
| **经过人格引擎** | ✅ 注入 user_message → 完整 Critic→Actor (Single-Pass) | ✅ 完整 Critic→Actor (Single-Pass) |
| **记忆写入** | history + EverMemOS（已知取舍） | EverMemOS + Hebbian |
| **回复生成** | Actor Single-Pass（完整人格表达，含真实数据） | Actor Single-Pass（完整人格表达） |
| **语义** | 用户要求"帮忙做的事" | 角色主动"想做的事" |

### 架构演进：从 bypass 到 inject

**v9（旧）**：Task Skill 绕过人格引擎 → `_express_wrap` 轻量包装 → early return
- 问题：角色语气弱、丢失具体数据、引擎状态断裂

**v10（当前）**：Task Skill 执行后 → stdout 注入 `user_message` → fall through 到人格引擎
- 优势：角色一致性、数据完整性、引擎状态正常更新
- 取舍：history/EverMemOS 存入含注入数据的合成消息（见第 5 节）

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

- **L1 永远加载**：启动时读取所有 SKILL.md frontmatter，构建 `modality_skills` 映射和 `tool_skills` 列表
- **L2 按需加载**：body 可能很大，只在技能首次执行时加载
- **activate() 幂等**：重复调用不会重新读文件

---

## 3. 执行路径

### Task Skill 端到端路径（v10 inject 模式）

```
"帮我看下北京天气"
  ↓
chat_stream() / _chat_inner() [under turn_lock]
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
stdout 注入 user_message:
  user_message = f"{user_message}\n\n[以下是真实查询数据，回复中必须自然融入关键数值，不要省略]\n{stdout[:800]}"
  ↓
Fall through → Step 0: Critic → Actor (Single-Pass) → Hebbian → EverMemOS
  ↓
角色用自己的语气回复，融入真实数据：
"今天北京+14°C，湿度47%，风速↓14km/h，挺适合出去走走的呢~"
```

### 人格内敛 Skill 路径（不变）

```
Actor 输出涌现 modality="照片"
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

## 4. Guard Clause 设计（v10）

```python
async def chat_stream(self, user_message: str) -> AsyncIterator[str]:
    await self._turn_lock.acquire()
    try:
        # ── Step -1: Task skill routing ──
        if self.skill_engine:
            skill_defs = self.skill_engine.build_skill_declarations()
            if skill_defs:
                routing_resp = await self.llm.chat(...)   # 三层异常保护
                if routing_resp and routing_resp.tool_calls:
                    result = await self.skill_engine.execute(...)
                    if result is not None:
                        stdout = result.output.get("stdout", "").strip()
                        if stdout:
                            user_message = f"{user_message}\n\n[...]\n{stdout[:800]}"
                            # 不 return，继续到 Step 0
                # fall through（无论成功与否）

        # ── Step 0: 人格引擎（零改动）──
        self._turn_count += 1
        ...
```

### 注入 vs 旧 bypass 对比

| 状态变量 | v9 bypass | v10 inject |
|----------|-----------|------------|
| `_turn_count` | ❌ 不递增 | ✅ 正常递增 |
| `_last_active` | ❌ 不更新 | ✅ 正常更新 |
| Critic / Actor (Single-Pass) | ❌ 跳过 | ✅ 完整运行 |
| Hebbian / EverMemOS | ❌ 不触发 | ✅ 正常触发（含注入数据） |
| Lock release | ✅ finally | ✅ finally |

### 三层异常处理

```
第一层：路由 LLM 失败 → 静默回退人格引擎（用户不知道有 tool 尝试）
第二层：execute() 失败 → result=None → 落穿到人格引擎
第三层：stdout 为空 → user_message 不变 → 引擎按普通消息处理
```

---

## 5. 已知取舍（下游污染）

v10 inject 模式下，`user_message` 被重绑定后流入以下位置：

| 位置 | 内容 | 影响 |
|------|------|------|
| `self.history` | 合成消息存入 history[-4:] | ⚠️ 中 — 后续 Express light context 含注入文本 |
| `_evermemos_store_bg` | 合成消息写入长期记忆 | ⚠️ 较高 — 检索时含 stdout 被当作用户话语 |
| `_evermemos_search_bg` | 向量搜索 query 含 stdout | ⚠️ 低 |
| `_last_action['user_input']` | crystallization 记录合成文本 | ⚠️ 低 |

**Phase D 优化方向**：保留 `original_msg`，仅修改传入 Actor 的版本，用 `original_msg` 写入 history/EverMemOS。需修改引擎内部。

---

## 6. 记忆隔离

```
chat.db (ChatLogStore)     ← 客户端展示历史
task.db (TaskLogStore)     ← 工具执行记录（隔离）
EverMemOS                  ← 人格长期记忆（v10: 工具轮也写入，含注入数据）
agent.history              ← 工作记忆（工具轮和人格轮都写入）
Hebbian                    ← 人格学习（v10: 工具轮也触发）
```

---

## 7. SKILL.md 编写规范

### Task Skill（trigger: tool）

SKILL.md 的 body 是 LLM 生成 shell 命令的上下文。编写规则：

1. **命令必须带 `--connect-timeout`** — 防止网络挂起
2. **命令必须带 `|| echo "错误提示"` 兜底** — 确保 stdout 永不为空
3. **不使用嵌套 `$(...)` 子 shell** — 特殊字符会破坏 URL
4. **城市名/参数 URL 编码空格用 `+`** — 如 `New+York`

示例（weather SKILL）：

```bash
# 用户指定城市
curl -s --connect-timeout 5 "wttr.in/Beijing?format=%l:+%c+%t+%h+%w" || echo "天气查询暂时不可用"

# 未指定城市（IP 自动定位）
curl -s --connect-timeout 5 "wttr.in/?format=%l:+%c+%t+%h+%w" || echo "天气查询暂时不可用"
```

---

## 8. 文件清单

```
agent/skills/
├── __init__.py          # 只导出 SkillEngine
├── skill_engine.py      # 统一引擎（L1/L2 + build_skill_declarations + execute）
├── sandbox_executor.py  # shell 命令沙盒执行
└── task_log_store.py    # task.db 隔离存储

providers/llm/
├── base.py              # ChatResponse.tool_calls + chat() tools
└── client.py            # 透传 tools/tool_choice

skills/weather/
└── SKILL.md             # trigger:tool + executor:sandbox

agent/chat_agent.py      # guard clause + inject-into-engine（_express_wrap 已删除）
```

---

## 9. 审查教训（10 轮 24 Bug + v10 迭代）

| 教训 | 代表 Bug |
|------|---------| 
| **所有 LLM 调用用 [system, user] 双消息** | Bug 1, 4: system-only 消息部分 provider 拒绝 |
| **工具路径必须有异常兜底** | Bug 6, 9: LLM 调用失败不能阻断人格引擎 |
| **边界值永远检查** | Bug 7, 15: 空命令、空 body 静默成功 |
| **大小写要归一化** | Bug 14: LLM 返回 "Weather" vs "weather" |
| **SKILL 命令必须自带 fallback** | v10: curl 失败时 stdout 为空导致数据丢失 |
| **不用嵌套子 shell 做城市检测** | v10: VPN 城市名含空格/引号破坏 URL |
| **stdout 截断防 token 爆** | v10: 长 stdout 膨胀 user_message 超 token 预算 |
