# Thermodynamic Persona Engine (TPE) — Supplementary Materials

## Directory Structure

```
submission/
├── code/                          # Source code
│   ├── eval_v3.py                 # Main evaluation pipeline (225 experiments)
│   ├── eval_v3_stats.py           # Statistical analysis & report generation
│   ├── genome_v8_timearrow.py     # TPE core: Drive Metabolism + Thermal Noise
│   ├── style_memory.py            # Gravitational Memory + Hawking Radiation
│   └── minimax_robustness_check.py # Appendix C robustness analysis
│
├── data/
│   ├── eval_scenarios_en.json     # 5 dialogue scenarios (30 turns each)
│   ├── eval_results/              # 226 experiment result JSONs
│   │   └── {model}_{scenario}_{method}_{seed}.json
│   └── memory_db/
│       └── genesis_bank.json      # Initial memory bank (innate persona)
│
└── latex/                         # Paper source
    ├── main.tex                   # Root document
    ├── appendix.tex               # Appendices A–C
    ├── references.bib             # Bibliography
    ├── acl.sty                    # ACL style file
    ├── acl_natbib.bst             # Bibliography style
    ├── main.bbl                   # Compiled bibliography
    ├── sections/                  # Paper sections (7 files)
    ├── tables/                    # LaTeX tables (10 files)
    └── figures/                   # Figures (5 files)
```

## Models Evaluated

| Model | Alignment Level | API Endpoint |
|-------|----------------|--------------|
| qwen3-max | Low-medium | DashScope |
| gpt-5-mini | High (RLHF+RLAIF) | OpenAI |
| MiniMax-M2.5 | Medium | MiniMax |

## Experiment Matrix

- **3 models** × **5 scenarios** × **5 methods** × **3 seeds** = **225 experiments**
- Each experiment: 30-turn dialogue with inter-turn time delays
- Seeds: 42, 316, 777

## Reproducing Results

```bash
# Install dependencies (stdlib only — no pip install needed)
# Requires: Python 3.8+

# Set API keys
export DASHSCOPE_API_KEY=your_key
export OPENAI_API_KEY=your_key
export MINIMAX_API_KEY=your_key

# Dry run (test connectivity)
python code/eval_v3.py --dry-run

# Run full matrix
python code/eval_v3.py --full

# Generate statistical report
python code/eval_v3_stats.py

# Appendix C robustness check
python code/minimax_robustness_check.py
```
