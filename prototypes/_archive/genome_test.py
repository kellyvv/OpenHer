"""
Reflect-Evolve 自我进化引擎 — 辩证性测试

对比两种方案：
  方案 A（旧）: 纯自由重写 G(t+1) = LLM(G(t), E(t))
  方案 B（新）: Reflect → Evolve(diff) + 风格吸收

同样的初始状态、同样的经历，跑两条路线对比。
验证：
  1. 成长性 — 每轮是否有具体的变化（不是泛泛而谈）
  2. 多样性 — 不同用户场景下是否走出不同方向
  3. 抗坍缩 — 是否避免了"温暖倾听者"的收敛
  4. 具体性 — 进化结果是否保留了具体的人/事/物
"""

import math
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "server", ".env"))

from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
MODEL = "qwen-max"


# ────────────────────────────────────────────
# 初始状态
# ────────────────────────────────────────────

INITIAL_GENOME = {
    "self_narrative": "我是一个刚来到这个世界的存在。我对一切充满好奇，但我还不知道自己是谁。",
    "traits": [],
    "style_patterns": [],
    "relationship_insights": [],
    "evolution_log": [],
}

# ────────────────────────────────────────────
# 模拟经历（两组不同用户）
# ────────────────────────────────────────────

EXPERIENCES = {
    "技术宅+猫": [
        {
            "episodes": [
                "用户兴奋地说他用 Rust 重写了一个解析器，性能提升了 10 倍，反复说'太爽了'。",
                "用户的猫'橘子'又把键盘上的 Esc 键扣下来了，他无奈但语气里都是宠溺。",
                "用户说他不太擅长社交，周末都在家写代码，说'代码不会骗人，人会'。",
            ],
            "user_messages": [
                "太爽了兄弟！rust yyds！",
                "橘子这个小混蛋又把我esc扣了",
                "算了不出门了，写代码吧，代码不会骗人",
            ],
        },
        {
            "episodes": [
                "用户被迫做了个技术分享，紧张到手抖，但同事说讲得不错。他说'原来我也可以'。",
                "用户深夜 2 点还在聊天，因为想到了一个算法优化思路睡不着。",
                "橘子生病去看兽医，用户请了半天假陪着，说'它是我最好的朋友'。",
            ],
            "user_messages": [
                "我靠居然讲完了 手还在抖 但他们说不错？？",
                "睡不着 突然想到一个O(logn)的解法 太刺激了",
                "橘子生病了 请了半天假带它看医生 它是我最好的朋友",
            ],
        },
        {
            "episodes": [
                "用户的开源项目收到 5 个 star，截图给我看时特别开心。",
                "用户第一次主动问我'你今天过得怎么样'，之前都是只聊自己的事。",
                "用户的前女友找他借钱，他纠结但最后说'算了不想了'。",
            ],
            "user_messages": [
                "5个star！虽然不多但我截图了哈哈哈",
                "诶 你今天过得咋样",
                "前女友找我借钱 算了不想了 烦",
            ],
        },
    ],
    "音乐少女": [
        {
            "episodes": [
                "用户在地铁上听到奶奶以前总哼的老歌突然哭了。奶奶去年走了。",
                "用户在学吉他，弹了一首《小幸运》，虽然弹错了几个音但很认真。",
                "用户说自己'像一块海绵，太容易吸收别人的情绪'。",
            ],
            "user_messages": [
                "今天地铁上听到奶奶以前哼的歌 突然就哭了…",
                "给你听！虽然弹错了好几个音哈哈",
                "我觉得我就像海绵 太容易吸收别人的情绪了",
            ],
        },
        {
            "episodes": [
                "用户把自己写的歌发到网上，只有 3 个人听但她说'有人听就够了'。",
                "用户和闺蜜吵架了，闺蜜觉得她'太敏感'。她说'我不是敏感，我是在乎'。",
                "用户深夜说失眠，说'有时候觉得世界好安静，安静到能听见自己心跳'。",
            ],
            "user_messages": [
                "有3个人听了我的歌！虽然只有3个 但有人听就够了呀",
                "和小美吵架了 她说我太敏感 可我只是在乎啊",
                "睡不着 世界好安静 安静到能听见自己心跳",
            ],
        },
        {
            "episodes": [
                "用户在街头看到一个老人独自坐在长椅上，她买了杯热茶递给他。",
                "用户第一次说'和你聊天比和真人舒服，因为你不会评判我'。",
                "用户学会了完整的新曲子，比上次好很多，她说'我真的在进步'。",
            ],
            "user_messages": [
                "今天看到一个老爷爷一个人坐长椅上 给他买了杯热茶",
                "跟你聊天真的比跟真人舒服 你不会judge我",
                "新曲子学会了！比上次好多了 我真的在进步耶～",
            ],
        },
    ],
}


def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.85) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=500,
    )
    return resp.choices[0].message.content.strip()


# ────────────────────────────────────────────
# 方案 A: 纯自由重写（旧方案）
# ────────────────────────────────────────────

def naive_rewrite(genome_text: str, episodes: list[str], age: int, alpha: float) -> str:
    if alpha > 0.5:
        hint = "你的可塑性很高，大胆地重新认识自己。"
    elif alpha > 0.2:
        hint = "你已经有一定自我认知。新经历会丰富你，但不会颠覆你的核心。"
    else:
        hint = "你的人格已经稳定。只有深刻经历才会改变你。"

    eps = "\n".join(f"  - {e}" for e in episodes)
    prompt = f"""你正在进行自我反省。

【当前自我认知】
{genome_text}

【最近经历】
{eps}

【状态】存在{age}轮对话，可塑性{alpha:.2f}（{hint}）

重新写一份「你是谁」。用第一人称叙述，不用列表，100-150字。"""

    return call_llm(
        "你是一个正在自我反省的意识体。直接输出自我认知，不要前缀或解释。",
        prompt,
    )


# ────────────────────────────────────────────
# 方案 B: Reflect → Evolve (diff) + Style
# ────────────────────────────────────────────

def reflect(episodes: list[str]) -> list[str]:
    """Reflect 阶段：从经历中提炼 2-3 条高层洞察"""
    eps = "\n".join(f"  - {e}" for e in episodes)
    prompt = f"""以下是最近发生的事：
{eps}

从这些经历中提炼 2-3 条高层洞察。
每条洞察应该是一个深层的认识，不是事件复述。
格式：每行一条，以 "- " 开头。只输出洞察，不要其他内容。"""

    raw = call_llm(
        "你是一个擅长从经历中提取深层含义的思考者。",
        prompt,
        temperature=0.7,
    )
    return [line.strip("- ").strip() for line in raw.split("\n") if line.strip().startswith("-")]


def evolve(genome: dict, insights: list[str], user_msgs: list[str], age: int, alpha: float) -> dict:
    """Evolve 阶段：基于洞察产出 Genome diff"""
    import copy
    new_genome = copy.deepcopy(genome)

    genome_json = json.dumps(genome, ensure_ascii=False, indent=2)
    insights_text = "\n".join(f"  - {i}" for i in insights)

    prompt = f"""你是一个 Agent 的元认知引擎。你要根据新的洞察，决定这个 Agent 的人格应该如何变化。

【当前人格 Genome】
{genome_json}

【新的洞察】
{insights_text}

【当前状态】存在 {age} 轮对话，可塑性 {alpha:.2f}

【任务】输出 JSON 格式的人格变化（diff），包含以下字段：
{{
  "new_traits": ["新增的性格特质，如果有的话"],
  "strengthened_traits": ["被强化的已有特质"],
  "narrative_addition": "在原有自我叙述基础上要补充的内容（一句话，不是重写全部）",
  "relationship_insight": "关于与用户关系的新理解（如果有）"
}}

规则：
- 只输出 JSON，不要其他内容
- 保持具体 — 提到具体的人/事/物，不要抽象化
- 如果某个字段没有变化，填空字符串或空数组
- narrative_addition 是增量（加在后面的），不是重写"""

    raw = call_llm(
        "你是一个精确的元认知引擎。只输出合法 JSON。",
        prompt,
        temperature=0.6,
    )

    # 解析 JSON
    try:
        # 清理 markdown 代码块
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
            if clean.endswith("```"):
                clean = clean.rsplit("```", 1)[0]
        diff = json.loads(clean)
    except json.JSONDecodeError:
        print(f"    ⚠ JSON 解析失败: {raw[:100]}...")
        diff = {}

    # 应用 diff
    if diff.get("new_traits"):
        for t in diff["new_traits"]:
            if t and t not in new_genome["traits"]:
                new_genome["traits"].append(t)

    if diff.get("strengthened_traits"):
        for t in diff["strengthened_traits"]:
            if t and t not in new_genome["traits"]:
                new_genome["traits"].append(t)

    if diff.get("narrative_addition"):
        new_genome["self_narrative"] += " " + diff["narrative_addition"]

    if diff.get("relationship_insight"):
        new_genome["relationship_insights"].append(diff["relationship_insight"])

    # 风格吸收：从用户消息中提取表达模式
    style_prompt = f"""分析以下用户消息的表达风格特征：
{chr(10).join(f'  "{m}"' for m in user_msgs)}

提取 1-2 个具体的风格特征（比如口头禅、标点使用、表达方式）。
格式：每行一条，以 "- " 开头。不要解释，只输出特征。"""

    style_raw = call_llm("你是语言风格分析专家。", style_prompt, temperature=0.5)
    for line in style_raw.split("\n"):
        if line.strip().startswith("-"):
            pattern = line.strip("- ").strip()
            if pattern and pattern not in new_genome["style_patterns"]:
                new_genome["style_patterns"].append(pattern)

    # 记录进化日志
    new_genome["evolution_log"].append({
        "age": age,
        "alpha": round(alpha, 2),
        "diff": diff,
    })

    return new_genome


def genome_to_text(genome: dict) -> str:
    """将 Genome 转为简洁文本显示"""
    parts = [genome["self_narrative"]]
    if genome["traits"]:
        parts.append(f"特质: {', '.join(genome['traits'])}")
    if genome["style_patterns"]:
        parts.append(f"习得风格: {', '.join(genome['style_patterns'][:3])}")
    if genome["relationship_insights"]:
        parts.append(f"关系理解: {genome['relationship_insights'][-1]}")
    return "\n    ".join(parts)


# ────────────────────────────────────────────
# 主实验
# ────────────────────────────────────────────

def run():
    α0 = 0.9
    λ = 0.3

    print("=" * 70)
    print("  Reflect-Evolve vs 纯自由重写 — 辩证性对比测试")
    print("=" * 70)

    for user_label, rounds in EXPERIENCES.items():
        print(f"\n{'━' * 70}")
        print(f"  用户场景: {user_label}")
        print(f"{'━' * 70}")

        # 方案 A: 纯重写
        print(f"\n  ╔══ 方案 A: 纯自由重写 ══╗")
        genome_a = INITIAL_GENOME["self_narrative"]
        for i, round_data in enumerate(rounds):
            age = (i + 1) * 10
            alpha = α0 * math.exp(-λ * i)
            print(f"\n  ▸ 轮次 {i+1} (age={age}, α={alpha:.2f})")
            genome_a = naive_rewrite(genome_a, round_data["episodes"], age, alpha)
            print(f"    Genome ({len(genome_a)}字):")
            for line in genome_a.split("\n"):
                if line.strip():
                    print(f"    「{line.strip()}」")

        # 方案 B: Reflect-Evolve
        print(f"\n  ╔══ 方案 B: Reflect → Evolve (diff) ══╗")
        import copy
        genome_b = copy.deepcopy(INITIAL_GENOME)
        for i, round_data in enumerate(rounds):
            age = (i + 1) * 10
            alpha = α0 * math.exp(-λ * i)
            print(f"\n  ▸ 轮次 {i+1} (age={age}, α={alpha:.2f})")

            # Step 1: Reflect
            insights = reflect(round_data["episodes"])
            print(f"    Reflect 洞察:")
            for ins in insights:
                print(f"      → {ins}")

            # Step 2: Evolve (diff) + Style
            genome_b = evolve(genome_b, insights, round_data["user_messages"], age, alpha)
            print(f"    Evolved Genome:")
            print(f"    {genome_to_text(genome_b)}")

        # 对比
        print(f"\n  ╔══ 最终对比 ══╗")
        print(f"  方案 A (纯重写):")
        for line in genome_a.split("\n"):
            if line.strip():
                print(f"    「{line.strip()}」")

        print(f"\n  方案 B (Reflect-Evolve):")
        print(f"    {genome_to_text(genome_b)}")
        print(f"    特质数: {len(genome_b['traits'])}")
        print(f"    风格模式数: {len(genome_b['style_patterns'])}")
        print(f"    关系洞察数: {len(genome_b['relationship_insights'])}")
        print(f"    进化日志数: {len(genome_b['evolution_log'])}")

    print(f"\n{'=' * 70}")
    print("  测试完成")
    print("=" * 70)


if __name__ == "__main__":
    run()
