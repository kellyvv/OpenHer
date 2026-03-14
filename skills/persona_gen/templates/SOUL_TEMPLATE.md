---
# ═══ Identity (注入 prompt — 仅事实身份) ═══
name: {{NAME}}
name_zh: {{NAME_ZH}}
gender: {{GENDER}}
age: {{AGE}}

# ═══ Display (仅 UI 展示，不注入 prompt) ═══
mbti: {{MBTI}}
tags:
  en: [{{TAGS_EN}}]
  zh: [{{TAGS_ZH}}]
bio:
  en: >
    {{BIO_EN}}
  zh: >
    {{BIO_ZH}}

# ═══ Engine (传给 Genome 引擎) ═══
genome_seed:
  drive_baseline:
    connection: {{CONNECTION}}   # 🔗 Bond (E↑ / I↓) — desire to connect
    novelty: {{NOVELTY}}         # ✨ Novelty (N↑ / S↓) — curiosity for new ideas
    expression: {{EXPRESSION}}   # 💬 Expression (F↑ / T↓) — urge to communicate
    safety: {{SAFETY}}           # 🛡️ Safety (J↑ / P↓) — need for control/defense
    play: {{PLAY}}               # 🎭 Play (P↑ / J↓) — playfulness & spontaneity
  engine_params:
    baseline_lr: {{BASELINE_LR}}
    elasticity: {{ELASTICITY}}
    hebbian_lr: {{HEBBIAN_LR}}
    phase_threshold: {{PHASE_THRESHOLD}}
    connection_hunger_k: {{CONNECTION_HUNGER_K}}
    novelty_hunger_k: {{NOVELTY_HUNGER_K}}
    frustration_decay: {{FRUSTRATION_DECAY}}
    hawking_gamma: {{HAWKING_GAMMA}}
    crystal_threshold: {{CRYSTAL_THRESHOLD}}
    temp_coeff: {{TEMP_COEFF}}
    temp_floor: {{TEMP_FLOOR}}
---
