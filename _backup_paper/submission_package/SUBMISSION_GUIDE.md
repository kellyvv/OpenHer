# ARR March 2026 投稿指南（第一次投稿完整版）

## 第一步：注册 OpenReview 账号

1. 打开 https://openreview.net/register
2. 填写：
   - Email: 用你的学术邮箱（如 .edu 邮箱），没有的话 Gmail 也行
   - First Name / Last Name: 填真实姓名（系统内部可见，不会显示在审稿人面前）
   - Password: 设一个强密码
3. 点 Register → 去邮箱点确认链接
4. 登录后完善 Profile：
   - 填写 Institution（机构/学校）
   - 添加你的研究领域关键词

## 第二步：找到 ARR March 2026 提交入口

1. 登录后访问: https://openreview.net/group?id=aclweb.org/ACL/ARR
2. 找到 "ACL ARR 2026 March" 或最新的 cycle
3. 点击 "Submit" 按钮

## 第三步：填写提交表单

以下是你需要填的每一项内容（直接复制粘贴）：

---

### Title（标题）:
```
A Thermodynamic Approach to Emotional Regulation in LLM Role-Playing
```

### Abstract（摘要）:
```
Large language model (LLM) role-playing agents face a fundamental tension: maintaining consistent character identity while exhibiting emotionally diverse responses across multi-turn conversations. Existing approaches either enforce rigid persona descriptions (producing emotionally flat output) or employ self-corrective reflection (which degrades consistency). We propose the Thermodynamic Persona Engine (TPE), a physics-inspired framework that couples a frustration-driven "temperature" to behavioral signal noise, while using mass-weighted memory retrieval with temporal decay to anchor response style. In a controlled evaluation across three LLMs (225 experiments, 30 turns each, 5 scenarios), TPE achieves a 32% improvement in emotional variance on qwen3-max (Bonferroni-adjusted p = 0.008, Cliff's d = +0.75, large effect) without reducing personality consistency. We additionally report two generalizable findings: (1) Reflexion-style self-correction significantly degrades persona consistency across all models (p < 0.001 on 2/3 models), and (2) strong RLHF alignment creates a hard ceiling on prompt-level persona control—on gpt-5-mini, anti-alignment instructions trigger safety rollbacks that amplify template counselor behavior (Collapse Index 22× higher than baseline). Code and data are available at [anonymized].
```

### Paper Type（论文类型）:
```
Long Paper
```

### Subject Area / Track（研究方向/赛道）— 按优先级选：
```
第一选择: Dialogue and Interactive Systems
第二选择: NLP Applications
第三选择: Language Generation
```

### Keywords（关键词）:
```
role-playing, persona consistency, emotional regulation, LLM agents, RLHF alignment, thermodynamic metaphor, memory retrieval, multi-turn dialogue
```

### TL;DR（一句话总结）:
```
A physics-inspired framework that couples frustration-driven noise to behavioral signals, improving emotional variance in LLM role-playing by 32% without degrading persona consistency, while revealing that Reflexion degrades consistency and strong RLHF alignment creates an insurmountable prompt-control ceiling.
```

### Submission Files（上传文件）:
- **Paper PDF**: 上传 paper.pdf（你的 submission_package 文件夹里）
- **Supplementary Material**: 上传 supplementary.zip（同一文件夹里）

### Responsible NLP Research Checklist（负责任的 NLP 研究清单）:
这是 ARR 必填的 checklist，逐项回答：

| 问题 | 建议回答 |
|------|----------|
| Did you use AI assistants? | Yes — 说明用了 LLM 做 critic extraction 和 evaluation |
| Does the paper include experiments on pre-existing datasets? | No — 你的数据是自己跑的 225 次实验 |
| Does the paper include computational experiments? | Yes |
| Did you report error bars or statistical significance? | Yes — Wilcoxon test, Bonferroni correction, Cliff's d |
| Did you include the code/data for reproducibility? | Yes — supplementary material |
| Does the paper include human evaluation? | No |
| Does the paper have a limitations section? | Yes — §6.1 |
| Does the paper have an ethics statement? | Yes — §8 |

### Author Information（作者信息）:
- 填你自己的 OpenReview profile
- 如果有合作者，填他们的 OpenReview profile（他们也需要注册）
- ⚠️ 注意：ARR 要求所有作者都注册为 reviewer

## 第四步：Reviewer 注册（重要！）

ARR 从 2025 年起要求**所有作者必须注册为 reviewer**。
提交后 2 天内，你需要：
1. 在 OpenReview 上完成 "Author Registration Form"
2. 填写你的审稿专长领域（建议填：dialogue systems, LLM agents, persona, RLHF）
3. 如果被分配审稿任务，必须按时完成，否则可能影响你的论文

## 第五步：提交

1. 检查所有字段填写完毕
2. 点击 Submit
3. 你会收到一封确认邮件
4. 在 OpenReview 的 "Your Consoles" 里可以看到提交状态

## 时间线预期

| 事件 | 预计日期 |
|------|----------|
| 提交截止 | ~2026年3月15日 |
| Review 出来 | ~2026年5月中 |
| 决定是否 commit 到 EMNLP | ~2026年5-6月 |
| EMNLP notification | ~2026年8-9月 |
| EMNLP 会议 | ~2026年10-11月 |

## 注意事项

- ❌ 提交后到 review 出来之前，不能同时投其他会议
- ❌ 不要在任何公开平台（Twitter/X、个人主页）透露你是作者
- ✅ 可以挂 arXiv（ACL 允许），但建议等 review 出来再挂，避免 de-anonymization
- ✅ 提交后可以在 OpenReview 上修改论文（deadline 之前）
