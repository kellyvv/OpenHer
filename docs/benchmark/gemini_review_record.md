# Gemini 三层 Benchmark 评审记录

**时间**: 2026-03-17 · **模型**: `gemini-3.1-flash-lite-preview` · **评审轮次**: 4 轮

---

## 发现的问题与最终解决方案

### 🔴 P2: `status_summary()` 温度公式不同步 (代码 bug)

**问题**: `temperature()` 使用 tanh 压缩曲线（实际驱动系统），但 `status_summary()` 使用旧的线性公式（用于 dashboard 展示）。high frustration (total=5.0) 时偏差达 +97%，可能导致调参方向错误。

**修复**:

```diff
# engine/genome/drive_metabolism.py L150
-  'temperature': round(total * self.temp_coeff + self.temp_floor, 3),
+  'temperature': round(self.temperature(), 3),
```

---

### 🔴 P2: L2 MaxReward 三位小数精确复现 — 机制澄清

**问题**: Luna/Kai/Kelly 的 L2 MaxReward 在多次运行中精确到三位小数完全一致，评审质疑是否为 mock/缓存。

**根因追溯（3 轮迭代）**:
- Round 1: 错误地用全局默认 `hunger_k` 计算 → 得出 0.80 的 `old_total` → 无法闭合
- Round 2: 找到 Critic `temperature=0.2` 机制 → 但 reward=0.422 ≠ 0.542，缺口 0.12
- Round 3: **发现 per-persona `engine_params` 覆盖** → Luna `novelty_hunger_k=0.08`（非全局 0.05）→ `old_total=0.92` → `0.92 - 0.378 = 0.542` ✅

**最终结论**: 两层确定性叠加：
1. Stage A: `hunger_k × Δt` 完全确定（per-persona 参数 × 精确时间差）
2. Stage B: Critic `temperature=0.2` 近贪心解码 → 相同 prompt 产生一致的 `frustration_delta`

**Per-persona 代谢常量（SOUL.md `engine_params`）**:

| 参数 | Luna ENFP | Kai ISTP | Kelly ENTP | 全局默认 |
|------|:---------:|:--------:|:----------:|:--------:|
| `connection_hunger_k` | 0.15 | 0.10 | 0.08 | 0.15 |
| `novelty_hunger_k` | 0.08 | 0.05 | 0.15 | 0.05 |
| `temp_coeff` | 0.15 | 0.08 | 0.12 | 0.12 |
| `temp_floor` | 0.04 | 0.02 | 0.05 | 0.03 |

---

### 🔴 P2: Kai L3 缺席 → 补测结果

**问题**: L3 只测了 Luna + Kelly，Kai 未覆盖。

**补测结果**:

| | Luna ENFP | Kai ISTP | Kelly ENTP |
|--|:---------:|:--------:|:----------:|
| 结晶数 | 2 | **0** | 12 |
| S2 代谢残留 | 0.203 | **0.000** | 0.378 |
| S2 持久化 | ✅ | ✅ | ✅ |
| S2 age 恢复 | ✅ | ✅ | ✅ |

**结论**: Kai 零结晶是 ISTP 正确行为。结晶梯度 Kelly(12) >> Luna(2) >> Kai(0) 与 MBTI novelty-seeking 特质完全对齐。

**新发现**: L3 assertion（`crystal > 0`, `metabolism > 0.01`）对 ISTP 不适用。需要改为 per-persona 阈值。

---

### 🟡 P3: Per-persona 参数「隐身」问题

**问题**: 三轮分析都用全局默认常量推导，SOUL.md 里的覆盖参数直到 Round 3 才被发现。这暴露了系统设计的可见性缺陷。

**修复**:

```diff
# engine/genome/drive_metabolism.py L22-23
  # ── Global defaults (used when engine_params not specified) ──
+ # ⚠ Overridable per-persona via SOUL.md engine_params — see persona/personas/*/SOUL.md
```

```diff
# agent/chat_agent.py L166-170
  evermemos_status = "ON" if (evermemos and evermemos.available) else "OFF"
+ m = self.metabolism
  print(f"✓ ChatAgent(Genome v10+EverMemOS) 初始化: ...")
+ print(f"  [metabolism] conn_k={m.connection_hunger_k}, nov_k={m.novelty_hunger_k}, "
+       f"decay={m.decay_lambda}, temp_coeff={m.temp_coeff}, temp_floor={m.temp_floor}")
```

---

### 🟡 P3: Kelly `playfulness=0.298` — 维度定义精度

**问题**: ENTP 的智识挑衅（wit/wordplay/provocation）是一种 playfulness，但引擎将 `playfulness` 锚定为「0=正经 → 1=调皮撒娇」，偏向 ENFP 式情感玩闹。

**分析**: Kelly 的挑衅行为被 `directness=0.637 + curiosity=0.668 + initiative=0.632` 三维联合表达，行为未丢失但信号语义不够精确。

**建议（backlog）**: 拆分 `emotional_play` + `intellectual_wit`，或重定义 playfulness 锚点。当前不阻塞。

---

### 🟡 P3: L1 终温系统性偏低 ~35%

**问题**: 本次 L1 终温（Luna 0.040, Kai 0.020, Kelly 0.050）比历史 raw_metrics 数据低 ~35%。

**根因**: Per-persona `temp_floor` 差异 + `temperature()` 从线性改为 tanh 压缩 + `pre_warm()` 增加 frustration 重置。当前值与 per-persona 参数完全一致，非退化。

---

### 🟡 P4: Cold Start reward ≈ 0

**问题**: 新用户首次对话 reward=0，Hebbian 学习无贡献。

**建议方案**: Per-persona `initial_connection` seed（Luna: 0.08, Kai: 0.01, Kelly: 0.03），从 `engine_params` 读取。物理正确但产品体验可优化。

---

### P5: `depth` 维度无分化

**现象**: 三人 depth 差异仅 0.025（0.374~0.399）。

**原因**: pre_warm 3 个场景的 `conversation_depth` 分布对所有 persona 相同，NN 对 depth 输出塑形方向趋同。不影响人格区分。

---

## 代码改动汇总

| 文件 | 改动 | 性质 |
|------|------|------|
| [drive_metabolism.py](file:///Users/zxw/AITOOL/openher-docker/engine/genome/drive_metabolism.py#L23) | 全局常量加 override 警告注释 | 防御性注释 |
| [drive_metabolism.py](file:///Users/zxw/AITOOL/openher-docker/engine/genome/drive_metabolism.py#L150) | `status_summary()` 改用 `self.temperature()` | Bug fix |
| [chat_agent.py](file:///Users/zxw/AITOOL/openher-docker/agent/chat_agent.py#L169-L170) | 启动日志打印 metabolism 实际常量 | 可见性增强 |
| [test_gemini_3layer.py](file:///Users/zxw/AITOOL/openher-docker/scripts/benchmark/test_gemini_3layer.py#L357) | L3 测试加入 Kai (ISTP) | 覆盖补全 |

## 测试产物

| 文件 | 说明 |
|------|------|
| [gemini_3layer_raw.json](file:///Users/zxw/AITOOL/openher-docker/docs/benchmark/gemini_3layer_raw.json) | 三层 benchmark 原始数据 |
| [kai_l3_result.json](file:///Users/zxw/AITOOL/openher-docker/docs/benchmark/kai_l3_result.json) | Kai L3 补测结果 |

## 关键教训

1. **先看数据源（SOUL.md），再推公式** — per-persona `engine_params` 从根本上改变代谢动力学
2. **纸面推导必须闭合到精确数值** — 区间推断无法解释精确复现
3. **Dashboard 展示必须与引擎行为使用同一计算路径** — `status_summary()` 的旧公式在 high frustration 时偏差可达 +97%
4. **Assertion 需要 per-persona 阈值** — 统一的 `crystal > 0` 对 ISTP 等低活跃人格不适用
