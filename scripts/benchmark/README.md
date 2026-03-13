# LLM Benchmark Scripts

Three-layer persona engine test suite for evaluating LLM providers.

## Test Layers

| Layer | What It Tests | Key Metric |
|-------|--------------|------------|
| **Layer 1** — Persona Quality | MBTI consistency, persona differentiation, format compliance | 5-turn cold start Q&A |
| **Layer 2** — Metabolism + Reward | Drive frustration release after 4h offline | MaxReward per persona |
| **Layer 3** — Hebbian Persistence | Memory crystallization + cross-session recall | Crystal count + persist check |

## Scripts

| Script | Provider | Layers | Notes |
|--------|----------|--------|-------|
| `test_gemini_personas.py` | Gemini | Layer 1 only | Original 3-script format |
| `test_metabolism_reward.py` | Gemini | Layer 2 only | |
| `test_hebbian_persistence.py` | Gemini | Layer 3 only | |
| `test_openai_personas.py` | OpenAI | Layer 1-3 | Combined format |
| `test_claude_personas.py` | Claude | Layer 1-3 | Combined format |

## Adding a New Model

```bash
# From the combined script, sed-replace provider and model:
sed 's/PROVIDER = "claude"/PROVIDER = "your_provider"/' test_claude_personas.py \
  | sed 's/MODEL = "claude-haiku-4-5-20251001"/MODEL = "your-model-id"/' \
  > test_yourmodel_personas.py

# Run:
cd /path/to/openher
.venv/bin/python3 scripts/benchmark/test_yourmodel_personas.py
```

## Results

Raw metrics and comparison reports are saved in `docs/benchmark/`:
- `raw_metrics.md` — All numerical data
- `llm_comparison_report.md` — 3-model analysis with audit
- `gemini_persona_analysis.md` — Detailed Gemini per-turn analysis
