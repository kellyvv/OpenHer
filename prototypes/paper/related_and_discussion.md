# 2. Related Work

Our work intersects three research areas: persona-consistent dialogue generation, self-evolving agent architectures, and the side effects of RLHF alignment on open-ended generation.

## 2.1 Persona-Consistent Dialogue

Maintaining a consistent character identity across multi-turn conversations has been studied extensively. Early approaches encode persona as fixed textual descriptions — PersonaChat (Zhang et al., 2018) introduced persona-conditioned dialogue where models receive a set of personality sentences. Subsequent work improved consistency through mutual persona perception (Liu et al., 2020), persona-augmented knowledge (Majumder et al., 2020), and contrastive learning of persona representations (Cao et al., 2022).

More recent systems scale persona control to LLMs. CharacterGLM (Zhou et al., 2023) fine-tunes models on large-scale character dialogue datasets. LIGHT (Urbanek et al., 2019) situates characters in grounded fantasy environments. RoleLLM (Wang et al., 2023) uses role-profile extraction and context-based instruction tuning. CharacterLLM (Shao et al., 2023) trains agents on historical character biographies.

These approaches focus on *who* the character is (knowledge, identity, backstory) but largely treat emotional expression as a byproduct of persona grounding. They do not model *how* emotional state evolves dynamically across turns — an agent may be consistent in personality but monotonous in expression. TPE complements these methods by operating on the behavioral signal layer rather than the identity layer.

## 2.2 Self-Evolving Agent Architectures

Generative Agents (Park et al., 2023) introduced the paradigm of long-term memory, reflection, and planning for believable character simulation. Their reflection mechanism — periodically summarizing memories into higher-level observations — directly inspires Reflexion (Shinn et al., 2023), which applies similar self-correction to task-solving: agents reflect on failures and adjust strategies through a verbal reinforcement loop.

Promptbreeder (Fernando et al., 2023) takes self-evolution further by mutating both task prompts and the mutation operators themselves. CAMEL (Li et al., 2023) explores multi-agent role-playing through inception prompting. MemGPT (Packer et al., 2023) introduces hierarchical memory management for LLMs, enabling virtual context management beyond the model's native window.

Our system differs from these architectures in two key respects. First, TPE's memory is organized by *behavioral similarity* in continuous signal space, not by semantic content or temporal recency. This means retrieval is driven by "how did I behave in emotionally similar situations?" rather than "what happened recently?" Second, our experimental results (Section 5.5) demonstrate that Reflexion-style self-correction, while effective for task convergence, actively degrades persona consistency — a finding that questions the universal applicability of reflective self-correction across agent types.

## 2.3 RLHF Side Effects on Open-Ended Generation

RLHF (Ouyang et al., 2022) and its variants (DPO, RLAIF) have become the standard post-training paradigm for instruction-following LLMs. While highly effective for safety and helpfulness, alignment training introduces well-documented side effects.

Mode collapse is a recognized concern: aligned models converge toward a narrow distribution of "helpful assistant" responses (Kirk et al., 2023). Perez et al. (2022) demonstrate sycophancy — aligned models tend to agree with users rather than maintain consistent positions. The "alignment tax" (Askell et al., 2021) describes capability degradation from overly conservative training.

In role-playing contexts, these effects manifest as what we term "RLHF collapse" — the agent abandons its designated persona to produce safe, empathetic, counselor-style responses. Our results on gpt-5-mini (Section 5.2) provide empirical evidence of this phenomenon: a heavily aligned model systematically overrides persona instructions with template therapeutic language, achieving Collapse Index scores 22× higher than less-aligned models.

TPE combines behavioral context modulation (few-shot memory examples shaped by gravitational retrieval) with prompt-level persona instruction. The behavioral context provides an additional control channel beyond prompt engineering alone: even when the prompt-level instruction is partially overridden by alignment, the few-shot examples still shape the distribution of generated text. However, this dual-channel approach is not sufficient to overcome strong alignment, as the gpt-5-mini failure demonstrates (Section 5.2).


---


# 6. Discussion

## 6.1 Summary of Findings

We presented the Thermodynamic Persona Engine (TPE), a physics-inspired framework that couples emotional arousal to behavioral variance through three mechanisms: drive metabolism, thermodynamic noise, and gravitational memory with Hawking radiation.

Our key findings are:

1. **TPE significantly improves emotional variance on qwen3-max** (EmotVar +32%, $p = 0.0077$, Cliff's $d = +0.747$) without degrading personality consistency, demonstrating that richer emotional expression and persona stability are not inherently in tension.

2. **Reflexion-style self-correction degrades persona consistency** across all three models (significant on qwen3-max and gpt-5-mini with large effect sizes). This is a finding independent of TPE that has implications for the broader agent architecture community.

3. **Strong RLHF alignment creates a hard ceiling for prompt-level persona engineering.** On gpt-5-mini, TPE's anti-alignment instruction triggers a safety rollback that amplifies the very behavior it aims to suppress. This suggests that persona control for heavily aligned models requires architectural interventions beyond prompt engineering — potentially at the fine-tuning or decoding level.

## 6.2 Limitations

**Automated metrics only.** All evaluation is automated: PCS uses LLM-based emotion extraction, EmotVar measures statistical dispersion, and Collapse relies on keyword matching. Human evaluation — even a small-scale study with 50 samples annotated by 2 raters — would substantially strengthen the claims. In particular, keyword-based Collapse detection may miss subtle template patterns or produce false positives on genuinely warm responses.

**Limited model coverage.** Three API-served models do not constitute a comprehensive alignment survey. Notably absent are open-weight models where alignment strength can be controlled (e.g., comparing base vs. RLHF checkpoints of the same model). Such experiments would provide stronger evidence for the alignment ceiling hypothesis.

**MiniMax data quality.** MiniMax-M2.5 exhibited systematic failure on the `emotional_comfort` scenario (all 15 experiments returned empty responses), inflating variance in remaining results. While robustness checks excluding this scenario show consistent trends, the data is insufficient for strong claims about TPE's effectiveness on this model.

**Ablation scope.** Our ablation demonstrates component necessity (removing thermal noise or Hawking mass degrades different quality dimensions) but does not establish physics-specificity. A controlled comparison against equivalently complex non-physics alternatives (e.g., fixed-schedule noise, recency-only memory weighting) would be needed to isolate the specific contribution of the physics-inspired coupling.

**Small $N$ for secondary findings.** With $N = 15$ per cell, the primary finding (qwen3-max EmotVar) is well-powered, but secondary findings (ablation contrasts, MiniMax trends) are underpowered. Increasing to $N = 45$ or more would improve confidence in cross-model and component-level effects.

**Single persona archetype.** All experiments use a single tsundere persona. Generalization to other character types (e.g., calm mentor, playful child, formal professional) remains untested and is a clear direction for future work.

**Critic reliability.** PCS and EmotVar depend on LLM-based emotion extraction (the critic module), which may introduce measurement noise. We did not assess inter-rater reliability of the critic across repeated evaluations of identical inputs. If the critic produces inconsistent scores for the same reply, all downstream metrics inherit this variance.

## 6.3 Future Work

Three directions emerge from these limitations:

1. **Alignment-aware persona control.** The gpt-5-mini failure motivates architectures that operate below the alignment layer — potentially combining TPE's behavioral modulation with model-specific fine-tuning or controlled decoding strategies (e.g., contrastive decoding against the model's default distribution).

2. **Physics-specificity ablation.** Comparing TPE's frustration-coupled noise against fixed-variance noise, and gravitational retrieval against recency-weighted retrieval, would disentangle the physics framing from the general benefit of noise and memory.

3. **Multi-persona evaluation.** Extending the scenario suite to diverse character archetypes would test whether TPE's mechanisms generalize beyond emotionally volatile personas. We hypothesize that the temperature-frustration coupling may be less effective for inherently calm characters, where frustration rarely accumulates.
