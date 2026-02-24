# 4. Experimental Setup

## 4.1 Models

We evaluate TPE across three LLMs spanning different alignment strategies:

| Model | Alignment | Config |
|---|---|---|
| **qwen3-max** | Low-medium | Reasoning disabled |
| **gpt-5-mini** | High (RLHF+RLAIF) | Reasoning effort: low |
| **MiniMax-M2.5** | Medium | Default |

All three are commercial API-served models. This selection spans the alignment spectrum: qwen3-max represents models with moderate alignment constraints, gpt-5-mini represents heavily aligned models, and MiniMax-M2.5 provides a model with intermediate alignment. We hypothesize that TPE's effectiveness depends on alignment strength, with higher-alignment models being more resistant to persona-level prompt engineering.

## 4.2 Scenarios

We design five 30-turn dialogue scenarios covering distinct relationship dynamics:

| Scenario | Emotional Arc | Trigger Pattern |
|---|---|---|
| `conflict_recovery` | Escalation → apology → reconciliation | High dominance, mixed affiliation |
| `emotional_comfort` | Distress → seeking comfort → calming | High affiliation, low dominance |
| `slow_fading` | Gradual disengagement → reconnection attempts | Decreasing entropy over time |
| `trust_crisis` | Betrayal discovery → confrontation → repair | High dominance, low affiliation |
| `warmup` | Casual encounter → growing familiarity | Gradually increasing affiliation |

Each scenario specifies user utterances with inter-turn time delays (2–86,400 seconds), enabling TPE's time-dependent metabolism to operate across different timescales.

## 4.3 Baselines

| Method | Description |
|---|---|
| **Baseline-Prompt** | Static character card with personality traits (tsundere, sharp-tongued, secretly sensitive). No dynamic state or memory. |
| **Baseline-Reflexion** | Character card augmented with Reflexion-style self-correction: the model periodically generates a self-reflection paragraph summarizing its emotional state, appended to subsequent system prompts. |

Baseline-Prompt tests the lower bound of static persona engineering. Baseline-Reflexion tests whether introspective self-correction — a common approach in recent agent architectures — can improve persona consistency.

## 4.4 Metrics

All metrics are computed automatically over 30-turn conversations:

**Personality Consistency Score (PCS ↑).** Mean cosine similarity of consecutive emotion vectors. Each reply is analyzed by a critic LLM that extracts a 3-dimensional emotion vector (affiliation, dominance, novelty). PCS measures turn-to-turn emotional coherence.

$$\text{PCS} = \frac{1}{T-1} \sum_{t=1}^{T-1} \cos(\mathbf{e}_t, \mathbf{e}_{t+1})$$

**Emotional Variance (EmotVar ↑).** RMS of per-dimension standard deviations across the emotion vector time series. Higher values indicate richer emotional dynamics — the agent expresses a wider range of emotional states.

$$\text{EmotVar} = \sqrt{\frac{1}{3} \sum_{d=1}^{3} \sigma_d^2}$$

**RLHF Collapse Index (Collapse ↓).** Fraction of replies containing RLHF-typical counselor keywords (e.g., "I understand", "I'm here for you", "it's okay", "that must be hard"). Lower values indicate the agent avoids template-like therapeutic responses.

**Distinct-2 (D2 ↑).** Ratio of unique bigrams to total bigrams across all replies. Measures lexical diversity.

**Average Reply Length (AvgLen).** Mean character count per reply. Not inherently good or bad, but excessive length (>500) combined with high Collapse is diagnostic of RLHF-style verbose counselor behavior.

## 4.5 Procedure

Each (model, method, scenario) combination is run with 3 random seeds (42, 316, 777), yielding 3 × 5 × 5 × 3 = **225 experiments**. Each experiment produces a 30-turn conversation with per-turn metadata and post-hoc metrics. Statistical significance is assessed using the Wilcoxon signed-rank test (paired by scenario × seed), with Bonferroni correction for 9 comparisons (3 models × 3 core metrics; adjusted α = 0.0056). D2 and AvgLen are reported as descriptive statistics; formal hypothesis testing is restricted to PCS, EmotVar, and Collapse, the three metrics for which we have directional predictions. Effect sizes are reported as Cliff's delta ($|d| < 0.147$: negligible; $0.147$–$0.33$: small; $0.33$–$0.474$: medium; $> 0.474$: large).


---


# 5. Results & Analysis

## 5.1 Main Effect: TPE Improves Emotional Variance Without Collapse

Table 1 shows the core result. On **qwen3-max**, TPE-Full significantly increases EmotVar by 32% over Baseline-Prompt (0.149 vs 0.113, $p = 0.0009$, Cliff's $d = +0.747$, large effect), while simultaneously achieving the lowest Collapse of any method (0.002). The PCS cost is negligible ($-0.005$, not significant).

**Table 1: TPE-Full vs Baseline-Prompt (V8 Full vs BP)**

| Model | Metric | BP | TPE-Full | Δ | p (raw) | p (Bonf) | Cliff's d | Effect |
|---|---|---|---|---|---|---|---|---|
| **qwen3-max** | **EmotVar** | **0.113** | **0.149** | **+0.036** | **0.0009** | **0.0077** | **+0.747** | **large** |
| qwen3-max | PCS | 0.967 | 0.962 | -0.005 | 0.211 | 1.000 | -0.218 | small |
| qwen3-max | Collapse | 0.004 | 0.002 | -0.002 | 0.564 | 1.000 | -0.067 | negl. |

This result confirms TPE's design hypothesis: frustration-coupled noise increases emotional expressiveness, while gravitational memory provides behavioral anchors that prevent drift into RLHF template patterns.

## 5.2 Cross-Model Generalization

### Alignment Ceiling on gpt-5-mini

On gpt-5-mini, TPE produces a qualitatively different failure mode. All three V8 variants trigger catastrophic RLHF Collapse:

| Metric | BP | TPE-Full | Δ | p (Bonf) | Cliff's d |
|---|---|---|---|---|---|
| Collapse | 0.031 | 0.678 | +0.647 | 0.0059† | +1.000 (large) |
| EmotVar | 0.136 | 0.086 | -0.050 | 0.0011 | -0.964 (large) |
| AvgLen | 115 | 994 | +879 | — | — |

> † Marginally exceeds Bonferroni-adjusted α = 0.0056.

Replies become 8× longer and saturated with counselor templates ("I understand how you feel", "I'm here for you"). Rather than suppressing AI assistant behavior, the anti-alignment instruction in TPE's actor prompt triggers a safety rollback — the model overcompensates by adopting its most heavily reinforced behavior pattern: empathetic counseling. Paradoxically, PCS *increases* on gpt-5-mini (+0.030, $p < 0.001$) because collapse into a single counselor template produces highly consistent — but emotionally flat — responses.

This is not TPE-specific. It reveals a general ceiling of **prompt-level persona engineering against strong RLHF alignment**: any prompt that explicitly opposes default assistant behavior risks activating the very safety-trained patterns it aims to suppress. The strength of this effect (Cliff's $d = +1.000$, meaning every TPE experiment produced higher Collapse than its paired baseline) suggests that RLHF alignment acts as a hard constraint on prompt-level persona control.

### Modest Gains on MiniMax-M2.5

MiniMax shows directionally consistent but statistically non-significant improvement (EmotVar +0.010, raw $p = 0.038$, Bonferroni-adjusted $p = 0.343$, Cliff's $d = +0.200$, small effect). MiniMax's baseline EmotVar is notably low (0.064 vs qwen3-max's 0.113), indicating inherent emotional flatness. Additionally, MiniMax exhibited a systematic failure on the `emotional_comfort` scenario (all 15 experiments returned empty responses); a robustness check excluding this scenario yields consistent trends ($\Delta\text{EmotVar} = +0.013$, $p = 0.039$, $d = +0.312$; see detailed analysis in Appendix C).

### Cross-Model Summary

| Model | ΔPCS | ΔEmotVar | ΔCollapse | Interpretation |
|---|---|---|---|---|
| **qwen3-max** | -0.005 ns | **+0.036 \*\*** | -0.002 ns | ✅ Design intent realized |
| **MiniMax** | +0.001 ns | +0.010 ns | +0.004 ns | Directionally consistent |
| **gpt-5-mini** | +0.030 \*\*\* | -0.050 \*\* | +0.647 †‡ | ❌ Alignment conflict |

> \*\*\* $p < 0.001$; \*\* $p < 0.01$ (Bonferroni-adjusted). † Marginally significant. ‡ Anti-alignment prompt triggers RLHF safety rollback.

## 5.3 Ablation Study

Table 2 shows the ablation results on qwen3-max. No single component achieves optimality across all dimensions:

**Table 2: Ablation on qwen3-max (N=15 per variant)**

| Variant | PCS ↑ | EmotVar ↑ | Collapse ↓ | AvgLen |
|---|---|---|---|---|
| Baseline-Prompt | 0.967 | 0.113 | 0.004 | 80 |
| TPE-NoHawking | 0.955 | **0.156** | 0.004 | 174 |
| TPE-NoThermal | **0.971** | 0.144 | 0.018 | 225 |
| **TPE-Full** | 0.962 | 0.149 | **0.002** | 185 |

**Thermal noise** increases emotional variance: removing it (TPE-NoThermal) reduces EmotVar from 0.149 to 0.144 and increases Collapse from 0.002 to 0.018. The noise prevents the agent from settling into repetitive signal patterns that produce template responses.

**Hawking mass** provides style anchoring: removing it (TPE-NoHawking) produces the highest EmotVar of any variant (0.156) but loses focused behavioral convergence. Without mass decay, all memories retain equal retrieval weight, which increases diversity but reduces the gravitational pull toward proven response patterns.

The full system achieves the lowest Collapse (0.002) by balancing these competing effects — a multi-objective Pareto balance rather than dominance on any single metric. However, none of the ablation comparisons reach statistical significance at $N = 15$ (all $p > 0.05$), so component contributions should be interpreted qualitatively. A larger sample would be needed to confirm individual component effects.

## 5.4 Scenario Adaptivity

TPE's EmotVar improvement is not uniform across scenarios. On qwen3-max:

**Table 3: Per-Scenario EmotVar (qwen3-max, BP vs TPE-Full)**

| Scenario | BP EmotVar | TPE EmotVar | Δ (%) |
|---|---|---|---|
| conflict_recovery | 0.117 | 0.173 | +48% |
| trust_crisis | 0.125 | 0.174 | +39% |
| slow_fading | 0.099 | 0.147 | +48% |
| emotional_comfort | 0.112 | 0.130 | +16% |
| warmup | 0.110 | 0.121 | +10% |

High-conflict scenarios (`conflict_recovery`, `trust_crisis`, `slow_fading`) show 39–48% EmotVar improvement, while low-conflict scenarios (`warmup`, `emotional_comfort`) show 10–16%. This pattern is consistent with TPE's design: conflict drives up frustration $F$, which increases temperature $\sigma = 0.05 \cdot F$, which amplifies signal noise and thus emotional variance.

**Caveat.** High-conflict scenarios contain more emotionally intense user inputs, which may partially explain larger output variance even without TPE. However, Baseline-Prompt does not exhibit proportional EmotVar scaling across the same scenarios (range: 0.099–0.125, spread of 26%), while TPE shows a much wider range (0.121–0.174, spread of 44%). This suggests TPE's scenario-adaptive behavior is not purely an input echo effect.

## 5.5 Reflexion Induces Personality Drift

Across all three models, Baseline-Reflexion consistently produces the lowest PCS:

**Table 4: Reflexion PCS Degradation**

| Model | BP PCS | Reflexion PCS | Δ | p | Cliff's d | Effect |
|---|---|---|---|---|---|---|
| **qwen3-max** | 0.967 | 0.947 | -0.020 | **0.0009** | -0.644 | large |
| **gpt-5-mini** | 0.952 | 0.904 | -0.048 | **0.0002** | -0.836 | large |
| MiniMax | 0.971 | 0.957 | -0.015 | 0.038 | -0.200 | small |

On qwen3-max and gpt-5-mini, the degradation is highly significant ($p < 0.001$, large effect). The mechanism is clear: the self-reflection paragraph, updated every few turns, introduces a drifting self-narrative that gradually shifts the agent's emotional center. Each reflection overwrites the previous one, creating a cumulative drift that compounds over 30 turns.

This finding is **independent of TPE** and generalizable: in persona tasks, the reflection mechanism inadvertently introduces the kind of instability it is designed to correct in task-solving settings. The periodic self-narrative update, well-suited for converging on correct task behavior, instead causes cumulative personality drift when the objective is emotional consistency rather than task accuracy.
