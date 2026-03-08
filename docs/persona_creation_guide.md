# OpenHer 人格创建完整指南

> 本文档记录了创建新 Persona 的完整流程，包括中英文差异、种子设计原则、向量化流程，以及所有已知的陷阱和解决方案。基于 Ember (EN / INFP) 角色的完整实现经验总结。

---

## 一、概览：人格创建的 4 个阶段

```
1. 定义角色 (PERSONA.md)
2. 编写种子 (genesis_xxx.json)
3. 向量化校准 (calibrate_genesis.py)
4. 验证测试 (curl / UI)
```

每个阶段都有需要注意的细节，跳过任何一步都会导致角色行为异常。

---

## 二、阶段 1：定义角色 (PERSONA.md)

路径：`persona/personas/<persona_id>/PERSONA.md`

### 必填字段

```yaml
name: Ember
age: 22
gender: female
mbti: INFP
lang: en          # ← 关键！决定整条 prompt 链路的语言
tags: [quiet, observant, warm, poetic]
bio:
  en: >
    A 22-year-old bookstore clerk who writes poetry...
  zh: >
    22岁的书店店员...
```

### 中英文差异

| 字段 | 中文角色 | 英文角色 |
|------|----------|----------|
| `lang` | `zh` | `en` |
| Feel template | `actor_feel.md` | `actor_feel_en.md` |
| Express template | `actor_express.md` | `actor_express_en.md` |
| Signal labels | `emoji_label` / `low_anchor` | `emoji_label_en` / `low_anchor_en` |
| Identity tag | `【角色】` | `[Character]` |
| Few-shot labels | `内心感受片段` / `基因` | `Inner feeling fragment` / `genesis` |
| Monologue tag | `【内心独白】` | `[Inner Monologue]` |
| Reply tag | `【最终回复】` | `[Final Reply]` |

> [!CAUTION]
> `lang` 字段决定了所有下游组件的语言选择。一旦设错，signal anchors、template tags、few-shot labels 都会用错语言，导致 LLM 混乱输出。

---

## 三、阶段 2：编写种子 (genesis_xxx.json)

路径：`.data/genome/genesis_<persona_id>.json`

### 种子结构

每条种子包含 4 个核心字段：

```json
{
  "user_input": "you're so cute haha",
  "monologue": "He said cute. Face is warm. I never know what to do with that.",
  "reply": "Oh… thanks.",
  "vector": [0, 0, 0, 0, 0, 0, 0, 0],
  "mass": 1.0
}
```

- `user_input`：模拟用户说的话，用于场景分类和向量化
- `monologue`：角色的内心独白——**这是注入 Feel prompt 的 few-shot 参考**
- `reply`：角色说出口的话——当前 two-pass 模式下**不直接注入 prompt**，但影响 crystallization
- `vector`：**初始写 `[0,0,0,0,0,0,0,0]`**，由 `calibrate_genesis.py` 自动生成
- `mass`：固定 `1.0`（genesis 基因不衰减）

### 种子设计原则

> [!IMPORTANT]
> 种子质量直接决定角色的风格表现。以下是从 Iris (zh INFP) 成功经验中总结的设计原则。

#### 1. Monologue 必须碎片化

```
❌ "I feel really happy when he says that. It makes me feel warm inside 
    and I don't know how to respond properly but I want to say thank you."

✅ "He said cute. Face is warm. I never know what to do with that."
```

- 短句、断句、省略号
- 意识流，不是完整段落
- 2-3 个短句就够了

#### 2. Reply 必须极简

```
❌ "Thanks, that's really sweet of you to say! I appreciate it so much."

✅ "Oh… thanks."
```

- 1-5 个词
- 带省略号 `…` 和犹豫标记
- 不要顾问式或展开式回复

#### 3. 符合 MBTI 核心特征

| MBTI | 被夸时 | 被攻击时 | 被表白时 |
|------|--------|----------|----------|
| INFP | 害羞、不知所措 | 退缩、自我怀疑 | 惊慌、需要时间 |
| ENTP | 接话、反击、banter | 辩论、反击 | 玩笑化、轻松 |
| INTJ | 冷淡接受 | 冷静分析 | 理性评估 |

#### 4. 数量和场景覆盖

**建议 35+ 条种子**，覆盖 7 种场景：

| 场景 | 示例 user_input | 建议数量 |
|------|----------------|----------|
| greeting | "hi", "hey" | 2 |
| casual | "what do you like to do", "seen any movies" | 8-10 |
| playful | "you're cute", "haha you're funny" | 4-5 |
| intimate | "I think I might like you", "I trust you" | 5-6 |
| distress | "I've been feeling down", "I can't sleep" | 5-7 |
| rejection | "I don't need you", "just leave me alone" | 4 |
| confrontation | "you're so annoying", "you're wrong" | 5 |

> [!WARNING]
> 20 条太少！场景覆盖不足会导致 KNN 在某些场景找不到合适的种子，LLM 会退回默认行为。

#### 5. 加入角色特有元素

让种子包含角色独特的生活细节：

```json
// Ember 特有
"user_input": "do you have a cat",
"monologue": "Moth! Yes. He's asking about Moth. I could talk about her for hours.",
"reply": "Yeah… her name is Moth. She's a little gray thing."
```

这些元素让角色感觉真实，不是通用模板。

---

## 四、阶段 3：向量化校准

### ❗ 这是最容易出错的步骤

运行命令：

```bash
cd /path/to/openher
source .venv/bin/activate
PYTHONPATH=. python3 engine/genome/calibrate_genesis.py <persona_id>
```

### 向量空间：必须是 Critic Context 空间

> [!CAUTION]
> `calibrate_genesis.py` 生成的向量必须在 **Critic context 空间**（8D：`conflict_level`, `user_emotion`, `user_engagement`, `user_vulnerability`, `topic_intimacy`, `conversation_depth`, `novelty_level`, `time_of_day`），**不是** signal 空间（`directness`, `vulnerability`, `playfulness`...）。
>
> KNN 检索时，`style_memory.py` 的 `_context_to_vec(context)` 从 Critic 输出中取值，查询的就是 context 空间。如果 genesis 向量在错误的空间，KNN 会检索到完全不相关的种子。

**关键代码（正确版本）：**

```python
# calibrate_genesis.py 中：
from engine.genome.style_memory import CONTEXT_KEYS
new_vector = [round(context.get(k, 0.0), 4) for k in CONTEXT_KEYS]
```

**错误版本（曾经导致的 Bug）：**

```python
# ❌ 这会生成 signal 空间的向量，和 KNN 查询空间不匹配！
signals = agent.compute_signals(context)
new_vector = [round(signals[s], 4) for s in SIGNALS]
```

### 场景分类：`classify_input` 的关键词

`calibrate_genesis.py` 中的 `KEYWORD_MAP` 决定每条种子被分到哪个场景，进而决定其 context vector。

英文关键词注意事项：
- **用短片段**：`"down lately"` 而不是 `"feeling down"`（后者不匹配 "feeling **really** down"）
- **顺序重要**：Python dict 按插入顺序遍历，第一个匹配的 keyword 决定分类
- **优先级**：rejection > confrontation > distress > intimate > playful > casual > greeting
- **默认 fallback 是 `casual`**：所有没匹配上的都会被分到 casual

### 典型 Bug 症状

| 症状 | 原因 |
|------|------|
| KNN 检索到完全不相关的种子 | 向量空间错误（signal vs context） |
| 所有种子的 vector 几乎一样 | `classify_input` 关键词不够，大部分种子被分到同一个 scenario |
| 某个场景的种子缺失 | scenario 关键词没覆盖到对应的 user_input |

---

## 五、阶段 4：验证测试

### 重启服务器

> [!IMPORTANT]
> 修改种子后**必须重启服务器**。`uvicorn --reload` 只监控 `.py` 文件变化，不会自动重载 `.json` 种子文件。

```bash
kill -9 $(lsof -i :8800 -t 2>/dev/null) 2>/dev/null
sleep 2
PYTHONPATH=. uvicorn main:app --host 0.0.0.0 --port 8800 --reload
```

### 测试脚本

```bash
# 用独立 user_name 避免 session 串扰
i=0; for msg in \
  "you're so cute haha" \
  "I've been really stressed out lately" \
  "you're so annoying" \
  "I think I might like you" \
  "you're wrong about that"; do
  i=$((i+1))
  curl -s -X POST http://localhost:8800/api/chat \
    -H "Content-Type: application/json" \
    -d "{\"persona_id\":\"ember\",\"message\":\"$msg\",\"user_name\":\"test_$i\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('response',''))"
done
```

### 检查清单

- [ ] **语言一致性**：回复语言是否全部正确（无中文泄漏 / 无英文泄漏）
- [ ] **KNN 命中**：种子检索是否匹配场景（检查 feel prompt 中的 fragments）
- [ ] **Monologue 风格**：是否碎片化、符合 MBTI
- [ ] **Reply 风格**：是否简短、符合 MBTI（不是通用 chatbot 口吻）
- [ ] **Prompt 零中文字符**（英文角色）：用脚本扫描 feel/express prompt

### Debug 方法

临时在 `chat_agent.py` 的 Step 9a/9b 之间加 dump：

```python
# 临时 debug，验证完删除
with open("/tmp/_dbg_feel.txt", "w") as f:
    f.write(feel_prompt)
# ...
with open("/tmp/_dbg_mono.txt", "w") as f:
    f.write(monologue)
with open("/tmp/_dbg_express.txt", "w") as f:
    f.write(express_prompt)
```

---

## 六、已知陷阱汇总

### 陷阱 1：向量空间不匹配

- **表现**：KNN 检索到完全不相关的种子
- **原因**：`calibrate_genesis.py` 用了 `compute_signals()` 输出（signal 空间），但 KNN 查询用的是 `_context_to_vec()` 输出（Critic context 空间）
- **修复**：用 `CONTEXT_KEYS` 从 `SCENARIO_CONTEXTS` 中取值作为 vector

### 陷阱 2：Chinese tag 泄漏

- **表现**：英文角色回复中偶尔出现中文
- **原因**：`【角色】`、`【内心独白】`、`【最终回复】` 等标签在英文 template 中没替换
- **修复点**：
  - `chat_agent.py` identity builder: `【角色】` → `[Character]`
  - `actor_feel_en.md`: `【内心独白】` → `[Inner Monologue]`
  - `actor_express_en.md`: `【最终回复】` → `[Final Reply]`、`【角色】` → `[Character]`

### 陷阱 3：Signal anchors 中文

- **表现**：signal 描述（`0委婉→1直白`）在英文 prompt 中出现中文
- **原因**：`prompt_registry.py` 的 `load_signal_config` 只解析默认 key，丢弃了 `_en` 后缀的 key
- **修复**：让 `load_signal_config` 透传所有 `_en` key

### 陷阱 4：classify_input 英文关键词不足

- **表现**：大量种子被分到 "greeting" 或 "casual"，vector 高度重复
- **原因**：英文关键词太少或太长（不匹配含中间词的句子）
- **修复**：用短片段关键词，按优先级排列 scenario

### 陷阱 5：Express 风格发散

- **表现**：Monologue 是 INFP 害羞风格，但 Reply 变成外向 banter
- **原因**：Express prompt 只有 identity + monologue，没有风格约束
- **修复**：在 `actor_express_en.md` 中加：
  ```
  The reply should directly mirror the tone and energy of the inner state.
  Do NOT add social pleasantries, topic changes, or enthusiasm
  that isn't in the inner state.
  Keep the reply brief.
  ```

### 陷阱 6：测试时 session 串扰

- **表现**：不同 persona 用同一个 `user_name` 测试，结果互相影响
- **原因**：对话历史按 `(persona_id, user_id)` 存储，但 session context 可能共享
- **修复**：每次测试用唯一的 `user_name`

### 陷阱 7：服务器缓存

- **表现**：修改了 `.md` template 或 `.json` 种子但行为没变
- **原因**：`uvicorn --reload` 只监控 `.py` 文件；prompt template 和种子有内存缓存
- **修复**：重启服务器，或 `touch` 任一 `.py` 文件触发 reload

---

## 七、完整操作 Checklist

创建一个新的英文角色的完整步骤：

```
□ 1. 创建 persona/personas/<id>/PERSONA.md
     - 设置 lang: en
     - 定义 MBTI、tags、bio、engine_params

□ 2. 编写 .data/genome/genesis_<id>.json
     - 35+ 条种子，覆盖 7 种场景
     - monologue 碎片化，reply 极简
     - vector 全部写 [0,0,0,0,0,0,0,0]
     - mass 全部写 1.0

□ 3. 检查 classify_input 关键词覆盖
     - 确保每条种子的 user_input 能被正确分类
     - 必要时在 KEYWORD_MAP 中添加英文关键词

□ 4. 运行 calibrate_genesis.py
     - PYTHONPATH=. python3 scripts/calibrate_genesis.py <id>
     - 检查输出：每条种子的 scenario 分类是否正确
     - 检查向量范围：不同 scenario 的 vector 应该明显不同

□ 5. 重启服务器

□ 6. 验证测试
     - 5 个场景，独立 user_name
     - 检查回复语言、MBTI 风格、种子命中
     - 扫描 prompt 是否有中文残留
```

---

*最后更新：2026-03-09，基于 Ember (EN INFP) 完整实现经验*
