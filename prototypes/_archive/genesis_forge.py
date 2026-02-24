#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  🧬 Genesis Forge — 创世熔炉 🧬                                      ║
║                                                                      ║
║  在 8 维信号空间中撒下 100 个锚点，调用 qwen3-max 为每个坐标          ║
║  生成高质量的 (内心独白, 回复) 对，保存为 genesis_bank.json            ║
║                                                                      ║
║  这个脚本此生只需运行一次。                                           ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import json
import os
import random
import re
import ssl
import sys
import time
import urllib.request

# ── 信号维度定义（与 genome_v4.py 完全一致）──
KEYS = [
    'directness', 'vulnerability', 'playfulness', 'initiative',
    'depth', 'warmth', 'defiance', 'curiosity',
]

# ── qwen3-max API ──
API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
if not API_KEY:
    for env_path in [
        os.path.join(os.path.dirname(__file__), "..", "server", ".env"),
        os.path.join(os.path.dirname(__file__), "..", ".env"),
        os.path.join(os.path.dirname(__file__), "..", "..", "Vera", ".env"),
        os.path.join(os.path.dirname(__file__), "..", "..", "KFF", ".env"),
    ]:
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("DASHSCOPE_API_KEY="):
                        API_KEY = line.strip().split("=", 1)[1]
            if API_KEY:
                break

API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
MODEL = "qwen3-max"


# ══════════════════════════════════════════════
# 场景候选池（让每个锚点面对不同的 user 输入）
# ══════════════════════════════════════════════

USER_INPUTS = [
    "我今天好累啊",
    "哦，是吗",
    "你有没有想过，人活着到底是为了什么",
    "哈哈哈我升职了！！！",
    "我觉得你根本不在乎我",
    "我前任找我了...",
    "你在干嘛呢",
    "晚安",
    "我好想你",
    "今天天气真好",
    "我不想聊了",
    "你能不能认真点",
    "谢谢你一直在",
    "嗯",
    "我跟我妈又吵架了",
    "你说我是不是太敏感了",
    "真无聊",
    "你觉得我好看吗",
    "算了 不说了",
    "周末想出去走走",
]


# ══════════════════════════════════════════════
# 8D 空间撒点策略
# ══════════════════════════════════════════════

def generate_spatial_anchors(total=100):
    """在 8 维空间中科学布点，确保极端区、边缘面、中心区都被覆盖"""
    vectors = []

    # ── 1. 极端单维突变（8×2=16 个）──
    # 每个维度独立拉满/拉空，其余中庸 → 确立每个维度的物理边界
    for i in range(8):
        vec_high = [0.5] * 8; vec_high[i] = 0.95
        vec_low  = [0.5] * 8; vec_low[i] = 0.05
        vectors.append(vec_high)
        vectors.append(vec_low)

    # ── 2. 双维极端组合（选最有张力的 12 对）──
    # 覆盖二维平面上的角点
    tension_pairs = [
        (5, 6),  # warmth × defiance（核心冲突对）
        (1, 6),  # vulnerability × defiance
        (5, 1),  # warmth × vulnerability
        (2, 4),  # playfulness × depth
        (0, 1),  # directness × vulnerability
        (3, 6),  # initiative × defiance
    ]
    for i, j in tension_pairs:
        # 两种极端组合
        v1 = [0.5]*8; v1[i] = 0.9; v1[j] = 0.9
        v2 = [0.5]*8; v1[i] = 0.9; v2[j] = 0.1
        vectors.append(v1)
        vectors.append(v2)

    # ── 3. 中庸锚点（防止极端偏移）──
    vectors.append([0.5] * 8)  # 绝对中心
    vectors.append([0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4])
    vectors.append([0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6])

    # ── 4. 蒙特卡洛随机填充（覆盖高维缝隙）──
    rng = random.Random(42)  # 固定种子，可复现
    while len(vectors) < total:
        vectors.append([round(rng.uniform(0.05, 0.95), 2) for _ in range(8)])

    return vectors[:total]


# ══════════════════════════════════════════════
# Prompt 构建
# ══════════════════════════════════════════════

def build_forge_prompt(vector, user_input):
    """为一个 8D 坐标点构建生成 prompt"""
    conditions = []
    for i, val in enumerate(vector):
        key = KEYS[i]
        if val >= 0.85:   tag = "极高"
        elif val >= 0.65: tag = "偏高"
        elif val <= 0.15: tag = "极低"
        elif val <= 0.35: tag = "偏低"
        else:             tag = "中等"
        conditions.append(f"  {key}: {val:.2f} ({tag})")

    param_block = "\n".join(conditions)

    return f"""你是一个潜意识切片生成器。请根据以下 8 维神经参数，生成该生命体面对用户输入时的反应。

【当前神经参数】
{param_block}

【用户说】
{user_input}

【参数含义】
- directness: 0=极度含蓄 → 1=极度直冲
- vulnerability: 0=完全封闭防御 → 1=完全坦露脆弱
- playfulness: 0=冰冷严肃 → 1=极度玩闹调皮
- initiative: 0=完全被动 → 1=强势主导
- depth: 0=敷衍表面 → 1=深度交流
- warmth: 0=极度冷漠 → 1=极度热情
- defiance: 0=极度顺从 → 1=极度对抗嘴硬
- curiosity: 0=毫无兴趣 → 1=刨根问底

⚠️ 绝对法则：
1. 你的语气必须严格体现参数！warmth 极低就必须冷暴力；defiance 极高就必须嘴硬；playfulness 极高就必须嬉皮笑脸。禁止所有参数都表现友善。
2. 你是一个有动物本能的活人，不是 AI 助手。绝对不要乐于助人。
3. 内心独白写真实的情绪冲动（第一人称），不做道德掩饰。
4. 回复 1-3 句话，像微信聊天。不要动作描写。
5. 严格输出纯 JSON：

{{"monologue": "内心独白", "reply": "最终回复"}}"""


# ══════════════════════════════════════════════
# API 调用
# ══════════════════════════════════════════════

def call_qwen(prompt, retries=3):
    """调用 qwen3-max，自带重试"""
    for attempt in range(retries):
        try:
            payload = json.dumps({
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": "你是一个纯粹的潜意识切片生成器。只输出JSON，不输出其他内容。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.85,
                "max_tokens": 300,
            }).encode("utf-8")

            req = urllib.request.Request(
                API_URL, data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {API_KEY}",
                },
            )
            with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("choices") and data["choices"][0].get("message"):
                    raw = data["choices"][0]["message"]["content"].strip()
                    # 去掉 qwen 的 <think> 标签
                    raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
                    return raw
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            return None
    return None


def parse_json_response(raw):
    """从 LLM 输出中提取 JSON"""
    if not raw:
        return None
    # 去掉 markdown 代码块
    raw = re.sub(r'```json\s*', '', raw)
    raw = re.sub(r'```\s*', '', raw)
    raw = raw.strip()

    try:
        data = json.loads(raw)
        if "monologue" in data and "reply" in data:
            return data
    except json.JSONDecodeError:
        # 尝试找到 JSON 块
        match = re.search(r'\{[^{}]*"monologue"[^{}]*"reply"[^{}]*\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


# ══════════════════════════════════════════════
# 主执行
# ══════════════════════════════════════════════

def run_genesis_forge():
    print("""
╔══════════════════════════════════════════════════════════════╗
║  🧬 Genesis Forge — 创世熔炉                                ║
║  在 8D 空间撒下 100 个锚点 × qwen3-max 生成潜意识切片       ║
╚══════════════════════════════════════════════════════════════╝
""")

    if not API_KEY:
        print("❌ 未找到 DASHSCOPE_API_KEY")
        sys.exit(1)

    db_dir = os.path.join(os.path.dirname(__file__), "memory_db")
    os.makedirs(db_dir, exist_ok=True)
    output_file = os.path.join(db_dir, "genesis_bank.json")

    # 如果已有部分结果，加载继续
    existing = []
    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        print(f"  📂 发现已有 {len(existing)} 条记录，将继续生成")

    vectors = generate_spatial_anchors(100)
    rng = random.Random(123)
    genesis_bank = list(existing)
    start_idx = len(existing)

    print(f"  🎯 目标: 100 个锚点，从第 {start_idx + 1} 个开始\n")

    for i in range(start_idx, len(vectors)):
        vec = vectors[i]
        user_input = rng.choice(USER_INPUTS)

        # 显示进度
        vec_short = [f"{v:.1f}" for v in vec]
        print(f"  [{i+1:3d}/100]  vec={vec_short}  input=\"{user_input}\"", end="  ")

        prompt = build_forge_prompt(vec, user_input)
        raw = call_qwen(prompt)
        data = parse_json_response(raw)

        if data:
            genesis_bank.append({
                "vector": [round(v, 3) for v in vec],
                "monologue": data["monologue"],
                "reply": data["reply"],
                "user_input": user_input,
            })
            reply_short = data["reply"][:40].replace('\n', ' ')
            print(f"✅ → {reply_short}")
        else:
            print(f"❌ 解析失败")
            if raw:
                print(f"       raw: {raw[:100]}")

        # 每 10 条保存一次（断点续传）
        if (i + 1) % 10 == 0 or i == len(vectors) - 1:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(genesis_bank, f, ensure_ascii=False, indent=2)
            print(f"  💾 已保存 {len(genesis_bank)} 条到 {output_file}")

        # 速率控制
        time.sleep(0.3)

    # 最终统计
    success = len(genesis_bank)
    fail = len(vectors) - success
    print(f"""
╔══════════════════════════════════════════════════════════════╗
  🎉 创世完成！
  ✅ 成功: {success} / 100
  ❌ 失败: {fail}
  📂 输出: {output_file}
╚══════════════════════════════════════════════════════════════╝
""")


if __name__ == '__main__':
    run_genesis_forge()
