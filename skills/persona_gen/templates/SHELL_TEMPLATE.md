---
persona_id: {{PERSONA_ID}}
version: 1.0
last_updated: {{DATE}}

archetype: {{ARCHETYPE}}

anchors:
  zh: "{{ANCHORS_ZH}}"
  en: "{{ANCHORS_EN}}"

negative:
  zh: "{{NEGATIVE_ZH}}"
  en: "{{NEGATIVE_EN}}"

dormant_keywords:
  zh: "{{DORMANT_ZH}}"
  en: "{{DORMANT_EN}}"

visual_anchors:
  - {{VISUAL_ANCHOR_1}}
  - {{VISUAL_ANCHOR_2}}
  - {{VISUAL_ANCHOR_3}}
  - {{VISUAL_ANCHOR_4}}
  - {{VISUAL_ANCHOR_5}}

# ═══ Image Generation ═══
image:
  prompt_base: >
    {{IMAGE_PROMPT_BASE}}
  style: realistic
  negative_prompt: ""

# ═══ Voice ═══
voice:
  voice_preset: "{{VOICE_PRESET}}"
  base_instructions: "{{VOICE_INSTRUCTIONS}}"
  description: "{{VOICE_DESCRIPTION}}"
  provider: dashscope
  emotion_enabled: true
---

# {{NAME_ZH}} / {{NAME}} · 角色定稿 — {{MBTI}} · {{AGE}}岁

> **定位**：{{POSITIONING}}

## 一、面部定稿

{{FACE_DESCRIPTION}}

## 二、发型定稿

{{HAIRSTYLE_DESCRIPTION}}

## 三、身形与比例定稿

{{BODY_DESCRIPTION}}

## 四、站姿与仪态定稿

{{POSTURE_DESCRIPTION}}

## 五、穿搭定稿

{{OUTFIT_DESCRIPTION}}

## 六、整体气质定稿

{{OVERALL_VIBE}}
