# 3. Method

## 3.1 Overview

We propose the **Thermodynamic Persona Engine (TPE)**, a physics-inspired framework for regulating emotional expression in LLM-based role-playing agents over multi-turn conversations. TPE consists of three components operating at each turn:

1. **Drive Metabolism** — a frustration-satiation system that maintains internal emotional state across turns
2. **Thermodynamic Noise** — Gaussian perturbation of behavioral signals proportional to internal frustration
3. **Gravitational Memory** — a memory retrieval system where frequently reinforced experiences attract stylistically similar future behavior, with temporal decay via Hawking radiation

The system operates a per-turn pipeline:

```
Time Metabolism → Critic → Drive Metabolism → Crystallization Gate → Thermal Noise → Gravitational Retrieval → Actor
```

**Why physics-inspired formulations?** We do not claim physical reality; rather, we use thermodynamic and gravitational metaphors as an *inductive bias* that provides two specific advantages over generic decay-noise-threshold designs: (1) the temperature metaphor naturally couples noise magnitude to emotional arousal — higher frustration produces higher temperature, which produces larger behavioral fluctuations, echoing how emotional intensity amplifies unpredictability in human behavior; (2) the gravitational mass metaphor provides a single mechanism that simultaneously handles recency, frequency, and retrieval relevance — recently crystallized, frequently reinforced memories "curve" the style space around them, making the agent gravitate toward proven response patterns. An equivalent system could be built from separate heuristic rules for noise scheduling, memory decay, and retrieval weighting, but the physics framing provides a more interpretable narrative for understanding system behavior — e.g., "the agent's temperature rose after a conflict" is immediately meaningful to designers.

**Scope of evaluation.** Our ablation study (Section 3.6) demonstrates that each component is necessary — removing thermal noise or Hawking mass degrades different quality dimensions. However, it does not establish that the *physics-specific coupling* (e.g., $\sigma \propto F$) outperforms an equivalently complex non-physics design (e.g., fixed-schedule noise). Disentangling the contribution of the physics formulation from the general benefit of having noise and memory at all remains an open question for future work.

## 3.2 Drive Metabolism

The agent maintains a frustration vector $\mathbf{f} \in \mathbb{R}^5_{\geq 0}$ over five drive dimensions: *connection, novelty, expression, safety, play*. Between interactions, two time-dependent processes operate:

**Frustration Decay.** All frustration values decay exponentially with elapsed time:

$$f_d(t) \leftarrow f_d(t_{\text{prev}}) \cdot e^{-\lambda \Delta t}$$

where $\lambda = 0.08 \text{ h}^{-1}$ (half-life ≈ 8.7 hours) and $\Delta t = t - t_{\text{prev}}$ in hours. This models the common observation that emotional intensity dissipates over time.

**Hunger Accumulation.** Two drives grow linearly with time:

$$f_\text{connection}(t) \leftarrow f_\text{connection}(t) + \kappa_c \cdot \Delta t$$
$$f_\text{novelty}(t) \leftarrow f_\text{novelty}(t) + \kappa_n \cdot \Delta t$$

where $\kappa_c = 0.15 \text{ h}^{-1}$ and $\kappa_n = 0.05 \text{ h}^{-1}$. This creates a "loneliness accumulation" effect when the agent is idle.

**Stimulus Processing.** Upon receiving user input, a critic module (implemented as an LLM call) extracts three interpersonal dimensions from the Interpersonal Circumplex: *affiliation* $a \in [0,1]$, *dominance* $d \in [0,1]$, and *entropy* $e \in [0,1]$. These update the 5-dimensional frustration vector $\mathbf{f}$ via fixed algebraic rules (e.g., high affiliation reduces connection frustration; high dominance increases safety frustration; full mapping in Appendix A). All values are clamped to $[0, 5]$.

The total frustration $F = \sum_d f_d$ serves as the system's "temperature" for the noise component.

**Signal Generation.** A genome weight matrix $\mathbf{W} \in \mathbb{R}^{5 \times 8}$, initialized per-agent and updated via a Hebbian-like correlation rule ($\Delta w_{ij} \propto f_i \cdot s_j$ after each reward event; details in Appendix A), maps the 5-dimensional drive state to the 8-dimensional behavioral signal vector $\mathbf{s}$. This mapping is the bridge between the internal frustration dynamics (Section 3.2) and the observable behavioral signals perturbed by noise (Section 3.3).

## 3.3 Thermodynamic Noise

Given the base signal vector $\mathbf{s} \in [0,1]^8$ (*directness, vulnerability, playfulness, initiative, depth, warmth, defiance, curiosity*) from Section 3.2, TPE adds Gaussian noise:

$$\tilde{s}_i = \text{clip}(s_i + \epsilon_i, 0, 1), \quad \epsilon_i \sim \mathcal{N}(0, \sigma^2)$$

where $\sigma = 0.05 \cdot F$ and $F$ is the total frustration. When the agent is calm ($F \approx 0$), signals remain near their base values. Under high frustration, signals fluctuate more widely, producing less predictable emotional expression. This coupling is the core mechanism: **emotional arousal directly increases behavioral variance**.

## 3.4 Gravitational Memory with Hawking Radiation

TPE maintains a memory pool $\mathcal{M}$ of past response patterns, each stored as an 8-dimensional signal vector with associated monologue, reply text, and a scalar mass $m \geq 1$.

**Crystallization.** After each turn, if the reward signal (frustration reduction) exceeds a threshold ($r > 0.3$), the previous turn's signals and response are crystallized into memory:
- If a memory within L2 distance < 0.15 (empirically set) exists, its mass is incremented by 1.0 and its content is updated (gravitational thickening).
- Otherwise, a new memory is created with initial mass $m = 2.0$.

**Hawking Radiation.** Memory mass decays with time since last use:

$$m_\text{eff}(t) = 1.0 + (m_\text{raw} - 1.0) \cdot e^{-\gamma \Delta t}$$

where $\gamma = 0.005 \text{ h}^{-1}$ (half-life ≈ 5.8 days). The base mass 1.0 is preserved (innate "genetic" memories never fully evaporate). Recently reinforced memories retain their full mass; long-unused memories decay toward baseline.

**Gravitational Retrieval.** At each turn, the top-$k$ ($k=3$) most relevant memories are retrieved using mass-weighted distance:

$$d_\text{eff}(\mathbf{q}, \mathbf{m}_i) = \frac{\|\mathbf{q} - \mathbf{v}_i\|_2}{\sqrt{m_{\text{eff},i}}}$$

where $\mathbf{q}$ is the current (noise-perturbed) signal vector and $\mathbf{v}_i$ is memory $i$'s stored vector. Higher-mass memories "curve" the style space, attracting the agent toward behavioral patterns that have been consistently successful.

The retrieved memories are formatted as few-shot examples in the actor prompt, providing concrete behavioral anchors for the LLM's generation.

## 3.5 Actor Generation

The final response is generated by an LLM conditioned on: (1) the few-shot memory examples, and (2) a system prompt that instructs the model to prioritize character-consistent emotional expression over default assistant behavior patterns. Specifically, the prompt directs the LLM to continue the emotional intensity, word choices, and response style from the retrieved memory examples, treating them as behavioral anchors rather than informational context. The exact prompt wording is provided in Appendix B. The implications and limitations of this anti-alignment instruction are discussed in Section 5.2.

The actor outputs a structured response with an inner monologue (used for crystallization) and a final reply (presented to the user).

## 3.6 Ablation Design

To isolate component contributions, we evaluate two ablation variants alongside the full system:

| Variant | Thermal Noise | Hawking Mass | Description |
|---|---|---|---|
| **TPE-Full** | ✓ | ✓ | Complete system |
| **TPE-NoThermal** | ✗ | ✓ | No frustration-coupled noise; base signals used directly |
| **TPE-NoHawking** | ✓ | ✗ | Mass decay disabled ($\gamma = 0$); all memories retain their accumulated mass |
