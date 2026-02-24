# A Thermodynamic Approach to Emotional Regulation in LLM Role-Playing

## Abstract

Large language model (LLM) role-playing agents face a fundamental tension: maintaining consistent character identity while exhibiting emotionally diverse responses across multi-turn conversations. Existing approaches either enforce rigid persona descriptions (producing emotionally flat output) or employ self-corrective reflection (which degrades consistency). We propose the **Thermodynamic Persona Engine (TPE)**, a physics-inspired framework that couples a frustration-driven "temperature" to behavioral signal noise, while using mass-weighted memory retrieval with temporal decay to anchor response style. In a controlled evaluation across three LLMs (225 experiments, 30 turns each, 5 scenarios), TPE achieves a 32% improvement in emotional variance on qwen3-max (Bonferroni-adjusted $p = 0.008$, Cliff's $d = +0.75$, large effect) without reducing personality consistency. We additionally report two generalizable findings: (1) Reflexion-style self-correction significantly degrades persona consistency across all models ($p < 0.001$ on 2/3 models), and (2) strong RLHF alignment creates a hard ceiling on prompt-level persona control — on gpt-5-mini, anti-alignment instructions trigger safety rollbacks that amplify template counselor behavior (Collapse Index $22\times$ higher than baseline). Code and data are available at [anonymized].


---


# 1. Introduction

LLM-based role-playing agents are increasingly deployed in applications requiring sustained character interaction — companion chatbots, interactive fiction, social skill training, and therapeutic simulation. A core challenge is the *emotional monotony problem*: while RLHF-aligned models produce safe and coherent responses, their output converges toward a narrow band of empathetic, measured language that lacks the emotional variability of natural human conversation.

Consider a tsundere character — outwardly cold and cutting, but secretly sensitive. A well-aligned LLM, given this persona description, may produce appropriate responses for the first few turns. But across 30 turns of emotionally charged dialogue, the model's responses drift toward polite empathy: "I understand how you feel" replaces sharp retorts; "I'm here for you" replaces reluctant vulnerability. This pattern — which we term **RLHF collapse** — reflects the model's post-training distribution overpowering the prompt-level persona instruction. This is not unique to fictional archetypes — any persona that deviates from the model's default empathetic register faces similar degradation over extended interactions.

Existing approaches to persona persistence fall into two categories. **Static persona descriptions** (Zhang et al., 2018; Zhou et al., 2023; Wang et al., 2023) provide character cards or role profiles that ground the model's identity. These improve *who* the agent is but do not model *how* emotional state evolves dynamically. **Self-corrective architectures** (Park et al., 2023; Shinn et al., 2023) introduce reflective memory that periodically updates a self-description. While effective for task convergence, we show that this mechanism introduces cumulative personality drift in role-playing settings.

We propose the **Thermodynamic Persona Engine (TPE)**, which approaches the problem from a different angle: rather than controlling *what* the model says (via prompt engineering or reflection), TPE modulates *how much* behavioral variance the model exhibits, coupling noise magnitude to internal emotional state. The key insight is that emotional arousal naturally increases behavioral unpredictability — an angry person is more volatile than a calm one. TPE formalizes this as a temperature parameter derived from accumulated frustration, combined with a gravitational memory system where successful behavioral patterns accrue mass and attract similar future responses, subject to temporal decay (Hawking radiation).

We evaluate TPE across three commercial LLMs spanning different alignment strengths, with 225 controlled experiments across 5 relationship scenarios. Our contributions are:

1. **TPE**: a physics-inspired framework for emotional regulation in LLM role-playing that significantly improves emotional variance while maintaining persona consistency (demonstrated on qwen3-max with large effect size).

2. **Cross-model evaluation revealing an alignment ceiling**: on heavily aligned models (gpt-5-mini), prompt-level persona engineering not only fails but actively backfires, producing RLHF collapse scores $22\times$ higher than baseline. This finding has implications beyond TPE for any prompt-based character control approach.

3. **Evidence that Reflexion degrades persona consistency**: self-corrective reflection, widely adopted in agent architectures, significantly reduces personality consistency scores across models — a finding that questions the universal applicability of reflective self-correction.
