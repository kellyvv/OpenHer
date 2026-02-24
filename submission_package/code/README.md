# Thermodynamic Persona Engine (TPE)

Anonymous submission — code for reproducibility review only.

## Files

- `genome_v8_timearrow.py` — Core TPE engine (Drive Metabolism, Thermodynamic Noise, Gravitational Memory, Hebbian Update, Actor Generation)
- `eval_v3.py` — Evaluation pipeline (225 experiments, 3 models × 5 methods × 5 scenarios × 3 seeds)

## Requirements

- Python 3.10+
- API keys for: qwen3-max (DashScope), gpt-5-mini (OpenAI), MiniMax-M2.5 (MiniMax)
- Set keys via environment variables: `DASHSCOPE_API_KEY`, `OPENAI_API_KEY`, `MINIMAX_API_KEY`

## Usage

```bash
# Run TPE agent interactively
python genome_v8_timearrow.py

# Run full evaluation suite
python eval_v3.py
```
