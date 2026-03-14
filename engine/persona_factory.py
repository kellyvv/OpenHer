"""
PersonaFactory — SKILL-driven persona creation.

Uses LLM + SKILL pattern:
  1. Reads skills/persona_gen/SKILL.md (complete instruction set)
  2. Sends SKILL body + templates/examples as system context to LLM
  3. LLM generates SOUL.md and genesis seeds
  4. Factory only handles: file IO + vector calibration (pure computation)

API contract: user provides 6 params → factory returns complete persona.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Optional


from engine.genome.style_memory import CONTEXT_KEYS
from engine.genome.critic import critic_sense
from engine.genome.genome_engine import simulate_conversation, DRIVES
from persona.loader import PersonaLoader, Persona
from engine.state_store import StateStore
from agent.chat_agent import ChatAgent


class PersonaFactory:
    """LLM + SKILL driven persona factory."""

    def __init__(
        self,
        llm,
        persona_loader: PersonaLoader,
        genome_data_dir: str,
        state_store: StateStore,
        memory_store=None,
    ):
        self.llm = llm
        self.persona_loader = persona_loader
        self.genome_data_dir = genome_data_dir
        self.state_store = state_store
        self.memory_store = memory_store

        # Load SKILL resources
        self.skill_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "skills" / "persona_gen"
        self.skill_body = self._load_skill_body()
        self.templates = self._load_templates()
        self.examples = self._load_examples()

    # ──────────────────────────────────────────────
    # SKILL Loading
    # ──────────────────────────────────────────────

    def _load_skill_body(self) -> str:
        """Load SKILL.md body (strip frontmatter)."""
        skill_path = self.skill_dir / "SKILL.md"
        if not skill_path.exists():
            print(f"  [persona_factory] ⚠ SKILL.md not found at {skill_path}")
            return ""
        content = skill_path.read_text(encoding="utf-8")
        # Strip YAML frontmatter
        if content.startswith("---"):
            end = content.find("---", 3)
            if end != -1:
                content = content[end + 3:].strip()
        return content

    def _load_templates(self) -> dict:
        """Load template files from skills/persona_gen/templates/."""
        templates = {}
        tpl_dir = self.skill_dir / "templates"
        if tpl_dir.exists():
            for f in tpl_dir.iterdir():
                if f.suffix == ".md":
                    templates[f.stem] = f.read_text(encoding="utf-8")
        return templates

    def _load_examples(self) -> dict:
        """Load example files from skills/persona_gen/examples/."""
        examples = {}
        ex_dir = self.skill_dir / "examples"
        if ex_dir.exists():
            for f in ex_dir.iterdir():
                if f.suffix in (".md", ".json"):
                    examples[f.stem] = f.read_text(encoding="utf-8")
        return examples

    async def create_from_params(self, req: dict) -> dict:
        """
        Create a complete persona from 6 basic inputs.

        Steps:
          1. LLM generates SOUL.md → validate engine config
          2. LLM generates 72 genesis seeds → validate quality
          3. Calibrate vectors (pure computation) + write genesis file
          4. Effect validation: NN pre_warm + KNN retrieval test
          5. Effect validation: Chat test (zh + en)

        Note: CHARACTER_SHEET.md is an external visual doc, not generated here.
        """
        persona_id = req.get("persona_id") or req["name"].lower().replace(" ", "_")
        req["persona_id"] = persona_id
        validation_report = {"passed": True, "checks": {}}

        print(f"[persona_factory] Creating persona '{persona_id}' via SKILL...")

        # ── Step 1/5: Generate + Validate SOUL.md ──
        print(f"  Step 1/5: Generating SOUL.md...")
        persona_md = await self._skill_generate_persona_md(req)
        self._write_persona_md(persona_id, persona_md)

        self.persona_loader.reload(persona_id)
        persona = self.persona_loader.get(persona_id)
        if not persona:
            raise RuntimeError(f"Failed to load newly created persona: {persona_id}")

        v1 = self._validate_persona_md(persona, req)
        validation_report["checks"]["persona_md"] = v1
        if not v1["passed"]:
            validation_report["passed"] = False
        print(f"    → SOUL.md validation: {'✅ PASS' if v1['passed'] else '⚠️ WARN'} "
              f"({v1['score']}/{v1['max_score']})")
        for w in v1.get("warnings", []):
            print(f"      ⚠ {w}")

        # ── Step 2/5: Generate genesis seeds ──
        print(f"  Step 2/5: Generating genesis seeds (72 = 36zh + 36en)...")
        seeds = await self._skill_generate_genesis_seeds(req, persona_md)

        # ── Step 3/5: Calibrate vectors via Critic LLM (v2) ──
        print(f"  Step 3/5: Calibrating vectors via Critic LLM...")
        calibrated = await self._calibrate_seeds_v2(seeds)
        genesis_path = os.path.join(self.genome_data_dir, f"genesis_{persona_id}.json")
        with open(genesis_path, "w", encoding="utf-8") as f:
            json.dump(calibrated, f, ensure_ascii=False, indent=2)

        v3 = self._validate_genesis(calibrated)
        validation_report["checks"]["genesis"] = v3
        if not v3["passed"]:
            validation_report["passed"] = False
        print(f"    → Genesis validation: {'✅ PASS' if v3['passed'] else '⚠️ WARN'} "
              f"({v3['score']}/{v3['max_score']})")
        for w in v3.get("warnings", []):
            print(f"      ⚠ {w}")

        # ── Step 4/5: NN Pre-warm + KNN retrieval test ──
        print(f"  Step 4/5: NN pre-warm + KNN retrieval test...")
        v4 = self._validate_nn_and_knn(persona)
        validation_report["checks"]["nn_knn"] = v4
        if not v4["passed"]:
            validation_report["passed"] = False
        print(f"    → NN+KNN validation: {'✅ PASS' if v4['passed'] else '⚠️ WARN'} "
              f"({v4['score']}/{v4['max_score']})")
        for w in v4.get("warnings", []):
            print(f"      ⚠ {w}")

        # ── Step 5/5: Chat effect test ──
        print(f"  Step 5/5: Chat effect test (zh + en)...")
        v5 = await self._validate_chat_effect(persona)
        validation_report["checks"]["chat_effect"] = v5
        if not v5["passed"]:
            validation_report["passed"] = False
        print(f"    → Chat effect: {'✅ PASS' if v5['passed'] else '⚠️ WARN'} "
              f"({v5['score']}/{v5['max_score']})")
        for w in v5.get("warnings", []):
            print(f"      ⚠ {w}")

        # ── Final Report ──
        total_score = sum(c["score"] for c in validation_report["checks"].values())
        total_max = sum(c["max_score"] for c in validation_report["checks"].values())
        status = "ready" if validation_report["passed"] else "ready_with_warnings"
        print(f"  {'✅' if validation_report['passed'] else '⚠️'} Persona '{persona_id}' — {status} "
              f"(total: {total_score}/{total_max})")

        return {
            "persona_id": persona_id,
            "status": status,
        }

    # ──────────────────────────────────────────────
    # Validation
    # ──────────────────────────────────────────────

    REQUIRED_DRIVES = ["connection", "novelty", "expression", "safety", "play"]
    REQUIRED_ENGINE_PARAMS = [
        "baseline_lr", "elasticity", "hebbian_lr", "phase_threshold",
        "connection_hunger_k", "novelty_hunger_k", "frustration_decay",
        "hawking_gamma", "crystal_threshold", "temp_coeff", "temp_floor",
    ]
    ENGINE_PARAM_RANGES = {
        "baseline_lr":        (0.004, 0.020),
        "elasticity":         (0.02, 0.10),
        "hebbian_lr":         (0.008, 0.030),
        "phase_threshold":    (1.0, 4.0),
        "connection_hunger_k":(0.04, 0.20),
        "novelty_hunger_k":   (0.03, 0.20),
        "frustration_decay":  (0.03, 0.15),
        "hawking_gamma":      (0.0003, 0.003),
        "crystal_threshold":  (0.30, 0.65),
        "temp_coeff":         (0.03, 0.20),
        "temp_floor":         (0.005, 0.06),
    }

    def _validate_persona_md(self, persona: Persona, req: dict) -> dict:
        """
        Validate SOUL.md after generation.

        Checks:
          - drive_baseline: 5 drives present, values 0.0-1.0
          - engine_params: 11 params present, values within reasonable ranges
          - tags: bilingual (zh + en)
          - bio: bilingual
          - name/age/gender/mbti match input
        """
        score, max_score = 0, 0
        warnings = []

        # 1. Identity match
        max_score += 4
        if persona.name == req.get("name"):
            score += 1
        else:
            warnings.append(f"Name mismatch: expected '{req.get('name')}', got '{persona.name}'")
        if getattr(persona, 'mbti', '') == req.get('mbti', ''):
            score += 1
        else:
            warnings.append(f"MBTI mismatch: expected '{req.get('mbti')}', got '{getattr(persona, 'mbti', '')}'")
        if getattr(persona, 'age', None) == req.get('age'):
            score += 1
        else:
            warnings.append(f"Age mismatch: expected {req.get('age')}, got {getattr(persona, 'age', None)}")
        if getattr(persona, 'gender', '') == req.get('gender', ''):
            score += 1
        else:
            warnings.append(f"Gender mismatch")

        # 2. Drive baseline (5D)
        db = persona.drive_baseline or {}
        max_score += 5
        for d in self.REQUIRED_DRIVES:
            if d in db and 0.0 <= float(db[d]) <= 1.0:
                score += 1
            else:
                warnings.append(f"drive_baseline.{d} missing or out of range [0,1]: {db.get(d)}")

        # 3. Engine params (11)
        ep = persona.engine_params or {}
        max_score += 11
        for p in self.REQUIRED_ENGINE_PARAMS:
            if p in ep:
                val = float(ep[p])
                lo, hi = self.ENGINE_PARAM_RANGES.get(p, (0, 1))
                if lo <= val <= hi:
                    score += 1
                else:
                    score += 0.5  # present but out of range
                    warnings.append(f"engine_params.{p}={val} outside expected range [{lo}, {hi}]")
            else:
                warnings.append(f"engine_params.{p} missing")

        # 4. Tags (bilingual)
        tags = getattr(persona, 'tags', None)
        max_score += 2
        if isinstance(tags, dict):
            if tags.get('en'):
                score += 1
            else:
                warnings.append("tags.en missing")
            if tags.get('zh'):
                score += 1
            else:
                warnings.append("tags.zh missing")
        elif isinstance(tags, list) and len(tags) > 0:
            score += 1  # at least has tags
            warnings.append("tags not bilingual (dict with en/zh expected)")
        else:
            warnings.append("tags missing")

        # 5. Bio (bilingual)
        bio = getattr(persona, 'bio', '')
        max_score += 2
        if isinstance(bio, dict):
            if bio.get('en'):
                score += 1
            else:
                warnings.append("bio.en missing")
            if bio.get('zh'):
                score += 1
            else:
                warnings.append("bio.zh missing")
        elif bio:
            score += 1
            warnings.append("bio not bilingual (dict with en/zh expected)")
        else:
            warnings.append("bio missing")

        passed = score >= max_score * 0.7  # 70% pass threshold
        return {
            "passed": passed,
            "score": round(score, 1),
            "max_score": max_score,
            "warnings": warnings,
        }



    def _validate_genesis(self, seeds: list) -> dict:
        """
        Validate genesis seeds quality.

        Checks:
          - Total count ≥ 60
          - Bilingual split (both zh and en present)
          - Monologue fill rate ≥ 80%
          - All seeds have required keys
          - Vectors are 8D
        """
        score, max_score = 0, 0
        warnings = []

        # 1. Total count
        max_score += 2
        if len(seeds) >= 60:
            score += 2
        elif len(seeds) >= 40:
            score += 1
            warnings.append(f"Seed count {len(seeds)} below target 72 (acceptable ≥60)")
        else:
            warnings.append(f"Seed count {len(seeds)} critically low (expected ≥60)")

        # 2. Bilingual split
        zh = sum(1 for s in seeds if s.get("lang") == "zh")
        en = sum(1 for s in seeds if s.get("lang") == "en")
        max_score += 2
        if zh >= 25:
            score += 1
        else:
            warnings.append(f"Too few zh seeds: {zh} (expected ≥25)")
        if en >= 25:
            score += 1
        else:
            warnings.append(f"Too few en seeds: {en} (expected ≥25)")

        # 3. Monologue fill rate
        mono_count = sum(1 for s in seeds if s.get("monologue"))
        mono_rate = mono_count / max(len(seeds), 1)
        max_score += 2
        if mono_rate >= 0.80:
            score += 2
        elif mono_rate >= 0.50:
            score += 1
            warnings.append(f"Monologue fill rate {mono_rate:.0%} below 80% target")
        else:
            warnings.append(f"Monologue fill rate {mono_rate:.0%} critically low")

        # 4. Required keys
        required_keys = {"user_input", "monologue", "reply", "vector", "mass", "lang"}
        max_score += 1
        missing_keys_count = 0
        for s in seeds:
            missing = required_keys - set(s.keys())
            if missing:
                missing_keys_count += 1
        if missing_keys_count == 0:
            score += 1
        else:
            warnings.append(f"{missing_keys_count} seeds missing required keys")

        # 5. Vector dimensionality
        max_score += 1
        bad_vectors = sum(1 for s in seeds if len(s.get("vector", [])) != 8)
        if bad_vectors == 0:
            score += 1
        else:
            warnings.append(f"{bad_vectors} seeds have non-8D vectors")

        # 6. Reply not empty
        max_score += 1
        empty_replies = sum(1 for s in seeds if not s.get("reply", "").strip())
        if empty_replies == 0:
            score += 1
        else:
            warnings.append(f"{empty_replies} seeds have empty replies")

        passed = score >= max_score * 0.7
        return {
            "passed": passed,
            "score": score,
            "max_score": max_score,
            "stats": {
                "total": len(seeds),
                "zh": zh,
                "en": en,
                "monologue_rate": f"{mono_rate:.0%}",
            },
            "warnings": warnings,
        }

    # ──────────────────────────────────────────────
    # SKILL-Driven LLM Generation
    # ──────────────────────────────────────────────

    async def _skill_generate_persona_md(self, req: dict) -> str:
        """LLM reads SKILL + templates + examples → generates SOUL.md."""
        from providers.llm.client import ChatMessage

        system = self._build_system_prompt(
            task="生成 SOUL.md",
            extra_sections=[
                ("SOUL.md 格式模板", self.templates.get("SOUL_TEMPLATE", "")),
                ("示例: Iris (INFP)", self.examples.get("iris_persona", "")),
                ("示例: Luna (ENFP)", self.examples.get("luna_persona", "")),
            ]
        )

        user = (
            f"请为以下角色生成完整的 SOUL.md：\n\n"
            f"name: {req['name']}\n"
            f"name_zh: {req.get('name_zh', '')}\n"
            f"gender: {req.get('gender', 'female')}\n"
            f"age: {req.get('age', 25)}\n"
            f"mbti: {req.get('mbti', 'INFJ')}\n"
            f"bio: {req.get('bio', '')}\n\n"
            f"直接输出完整的 SOUL.md 内容（包含 --- 前后的 YAML frontmatter），不要其他解释。"
        )

        response = await self.llm.chat([
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ], max_tokens=4096)

        return self._clean_markdown_output(response.content)



    async def _skill_generate_genesis_seeds(self, req: dict, persona_md: str) -> list:
        """LLM reads SKILL + examples → generates genesis seeds in batches."""
        from providers.llm.client import ChatMessage

        all_seeds = []

        TARGET_PER_LANG = 36

        for lang, lang_label in [("zh", "中文"), ("en", "英文")]:
            lang_seeds = []
            max_retries = 3

            for attempt in range(max_retries + 1):
                need = TARGET_PER_LANG - len(lang_seeds)
                if need <= 0:
                    break

                system = self._build_system_prompt(
                    task=f"生成{lang_label} Genesis Seeds",
                    extra_sections=[
                        ("Genesis 种子示例", self.examples.get("genesis_sample", "")),
                    ]
                )

                if attempt == 0:
                    user = (
                        f"角色信息：\n{persona_md[:1500]}\n\n"
                        f"请为这个角色生成 {TARGET_PER_LANG} 个{lang_label}对话种子。\n"
                        f"覆盖 7 个场景（greeting, distress, rejection, casual, playful, intimate, confrontation），每类约 5 个。\n\n"
                        f"严格按 JSON 数组输出，每个元素包含：\n"
                        f'  {{"user_input": "...", "monologue": "...", "reply": "...", "lang": "{lang}"}}\n\n'
                        f"必须严格输出 {TARGET_PER_LANG} 个，不多不少。直接输出 JSON 数组，不要其他解释。"
                    )
                else:
                    user = (
                        f"角色信息：\n{persona_md[:1000]}\n\n"
                        f"还差 {need} 个{lang_label}对话种子，请补充生成。\n"
                        f"场景覆盖：greeting, distress, rejection, casual, playful, intimate, confrontation。\n\n"
                        f"严格按 JSON 数组输出，每个元素包含：\n"
                        f'  {{"user_input": "...", "monologue": "...", "reply": "...", "lang": "{lang}"}}\n\n'
                        f"必须严格输出 {need} 个。直接输出 JSON 数组，不要其他解释。"
                    )

                response = await self.llm.chat([
                    ChatMessage(role="system", content=system),
                    ChatMessage(role="user", content=user),
                ], max_tokens=8192)

                batch = self._parse_json_seeds(response.content, lang)
                lang_seeds.extend(batch)

                if attempt == 0:
                    print(f"    [{lang}] Round 1: {len(batch)} seeds")
                else:
                    print(f"    [{lang}] Backfill round {attempt+1}: +{len(batch)} → total {len(lang_seeds)}")

            # Trim to exactly TARGET if over
            lang_seeds = lang_seeds[:TARGET_PER_LANG]

            if len(lang_seeds) < TARGET_PER_LANG:
                print(f"    ⚠ [{lang}] Only {len(lang_seeds)}/{TARGET_PER_LANG} after {max_retries} retries")

            all_seeds.extend(lang_seeds)

        print(f"    Total: {len(all_seeds)} seeds (target: {TARGET_PER_LANG * 2})")
        return all_seeds

    # ──────────────────────────────────────────────
    # System Prompt Builder
    # ──────────────────────────────────────────────

    def _build_system_prompt(self, task: str, extra_sections: list = None) -> str:
        """Build system prompt: SKILL body + relevant templates/examples."""
        parts = [
            f"# 任务：{task}\n",
            self.skill_body,
        ]

        if extra_sections:
            for title, content in extra_sections:
                if content:
                    parts.append(f"\n\n---\n## 参考：{title}\n\n{content}")

        return "\n".join(parts)

    # ──────────────────────────────────────────────
    # Level 2: Create from SOUL.md File
    # ──────────────────────────────────────────────

    async def create_from_file(self, persona_id: str, persona_md: str) -> dict:
        """Create persona from uploaded SOUL.md file."""
        # Write SOUL.md directly
        self._write_persona_md(persona_id, persona_md)
        self.persona_loader.reload(persona_id)

        persona = self.persona_loader.get(persona_id)
        if not persona:
            raise RuntimeError(f"Failed to load uploaded persona: {persona_id}")

        # Generate genesis seeds via SKILL
        req = {
            "persona_id": persona_id,
            "name": persona.name,
            "name_zh": getattr(persona, 'name_zh', ''),
            "gender": getattr(persona, 'gender', 'female'),
            "age": getattr(persona, 'age', 25),
            "mbti": getattr(persona, 'mbti', ''),
            "bio": getattr(persona, 'bio', ''),
        }

        seeds = await self._skill_generate_genesis_seeds(req, persona_md)
        calibrated = await self._calibrate_seeds_v2(seeds)
        genesis_path = os.path.join(self.genome_data_dir, f"genesis_{persona_id}.json")
        with open(genesis_path, "w", encoding="utf-8") as f:
            json.dump(calibrated, f, ensure_ascii=False, indent=2)

        return {
            "persona_id": persona_id,
            "status": "ready",
            "genesis_count": len(calibrated),
            "engine_params": persona.engine_params or {},
            "drive_baseline": persona.drive_baseline or {},
        }

    # ──────────────────────────────────────────────
    # Vector Calibration v2 — Critic LLM per-seed
    # ──────────────────────────────────────────────

    async def _calibrate_seeds_v2(self, seeds: list) -> list:
        """
        Assign 8D context vectors via Critic LLM (same as calibrate_genesis_v2.py).

        Each seed gets a unique vector by running user_input through critic_sense(),
        the exact same pipeline used at runtime.

        Output format: {user_input, monologue, reply, vector(8D), mass, lang}
        """
        frustration = {d: 0.0 for d in DRIVES}
        calibrated = []
        unique_vecs = set()

        for i, seed in enumerate(seeds):
            user_input = seed.get("user_input", "")
            if not user_input:
                continue

            try:
                context, _, _, _ = await critic_sense(
                    stimulus=user_input,
                    llm=self.llm,
                    frustration=frustration,
                    user_profile="",
                    episode_summary="",
                )
                vector = [round(context.get(k, 0.0), 4) for k in CONTEXT_KEYS]
            except Exception as e:
                # Fallback: jittered neutral vector so fallback seeds remain distinguishable
                import random
                vector = [round(0.5 + random.uniform(-0.15, 0.15), 4) for _ in CONTEXT_KEYS]
                print(f"      ⚠ Critic failed for seed {i+1}, using jittered fallback: {e}")

            unique_vecs.add(str(vector))
            calibrated.append({
                "user_input": user_input,
                "monologue": seed.get("monologue", ""),
                "reply": seed.get("reply", ""),
                "vector": vector,
                "mass": 1.0,
                "lang": seed.get("lang", "zh"),
            })

        print(f"    Calibrated {len(calibrated)} seeds, {len(unique_vecs)} unique vectors")
        return calibrated

    # ──────────────────────────────────────────────
    # Effect Validation
    # ──────────────────────────────────────────────

    def _validate_nn_and_knn(self, persona) -> dict:
        """
        Effect validation: NN pre-warm + KNN retrieval test.

        1. Create temporary ChatAgent → run pre_warm (60 steps)
        2. Check W1/W2 weights diverged from initialization
        3. Test KNN retrieval across 3 scenarios → verify diverse results
        """
        import numpy as np
        score, max_score = 0, 0
        warnings = []

        try:
            # 1. Create temporary agent and pre-warm
            test_agent = ChatAgent(
                persona=persona,
                llm=self.llm,
                user_id="__test_prewarm__",
                user_name="tester",
                memory_store=self.memory_store,
                genome_data_dir=self.genome_data_dir,
                evermemos=None,
            )

            # Capture W1/W2 before pre-warm
            w1_before = np.array(test_agent.agent.W1).copy()
            w2_before = np.array(test_agent.agent.W2).copy()

            # Pre-warm (60 steps)
            test_agent.pre_warm()

            # 2. Check W1/W2 divergence
            w1_after = np.array(test_agent.agent.W1)
            w2_after = np.array(test_agent.agent.W2)
            w1_delta = float(np.mean(np.abs(w1_after - w1_before)))
            w2_delta = float(np.mean(np.abs(w2_after - w2_before)))

            max_score += 2
            if w1_delta > 1e-6:
                score += 1
                print(f"      W1 Δ={w1_delta:.6f} (shaped ✓)")
            else:
                warnings.append(f"W1 unchanged after pre-warm (Δ={w1_delta:.8f})")

            if w2_delta > 1e-6:
                score += 1
                print(f"      W2 Δ={w2_delta:.6f} (shaped ✓)")
            else:
                warnings.append(f"W2 unchanged after pre-warm (Δ={w2_delta:.8f})")

            # Check drive_state reset to baseline
            max_score += 1
            drives_ok = True
            for d in DRIVES:
                current = test_agent.agent.drive_state.get(d, 0)
                baseline = test_agent.agent.drive_baseline.get(d, 0)
                if abs(current - baseline) > 0.01:
                    drives_ok = False
                    warnings.append(f"drive_state.{d}={current:.3f} != baseline {baseline:.3f}")
            if drives_ok:
                score += 1

            # 3. KNN retrieval diversity test
            style_mem = test_agent.style_memory
            test_contexts = [
                {"intimacy": 0.1, "trust": 0.2, "emotional_valence": 0.5,
                 "emotional_arousal": 0.3, "conversation_depth": 0.1,
                 "dominance": 0.5, "novelty": 0.3, "conflict_level": 0.1},
                {"intimacy": 0.8, "trust": 0.9, "emotional_valence": 0.9,
                 "emotional_arousal": 0.7, "conversation_depth": 0.8,
                 "dominance": 0.3, "novelty": 0.5, "conflict_level": 0.0},
                {"intimacy": 0.3, "trust": 0.2, "emotional_valence": 0.1,
                 "emotional_arousal": 0.9, "conversation_depth": 0.5,
                 "dominance": 0.8, "novelty": 0.2, "conflict_level": 0.9},
            ]

            max_score += 2
            all_top1_replies = []
            for ctx in test_contexts:
                results = style_mem.retrieve(ctx, top_k=3)
                if results:
                    all_top1_replies.append(results[0].get("reply", ""))

            if len(all_top1_replies) == 3:
                score += 1  # KNN returned results
                # Check diversity: top-1 should differ across scenarios
                if len(set(all_top1_replies)) >= 2:
                    score += 1
                    print(f"      KNN diversity: {len(set(all_top1_replies))}/3 unique top-1 replies ✓")
                else:
                    warnings.append("KNN returns same seed for all scenarios (vector flatness)")
            else:
                warnings.append(f"KNN retrieval failed: only {len(all_top1_replies)}/3 returned")

        except Exception as e:
            warnings.append(f"NN+KNN test error: {str(e)[:100]}")

        passed = score >= max_score * 0.6
        return {
            "passed": passed,
            "score": score,
            "max_score": max_score,
            "warnings": warnings,
        }

    async def _validate_chat_effect(self, persona) -> dict:
        """
        Effect validation: chat test.

        Sends 2 test messages (zh + en) to a temporary ChatAgent.
        Checks: reply is non-empty, monologue exists, reply length > 10 chars.
        """
        score, max_score = 0, 0
        warnings = []
        samples = []

        test_messages = [
            ("zh", "你好啊，最近在忙什么？"),
            ("en", "Hey, what are you up to these days?"),
        ]

        try:
            test_agent = ChatAgent(
                persona=persona,
                llm=self.llm,
                user_id="__test_chat__",
                user_name="tester",
                memory_store=self.memory_store,
                genome_data_dir=self.genome_data_dir,
                evermemos=None,
            )
            # Pre-warm for realistic responses
            test_agent.pre_warm()

            for lang, msg in test_messages:
                result = await test_agent.chat(msg)
                reply = result.get("reply", "")
                monologue = ""
                if test_agent._last_action:
                    monologue = test_agent._last_action.get("monologue", "")

                # Check reply
                max_score += 2
                if reply and len(reply) > 10:
                    score += 1
                    print(f"      [{lang}] reply ({len(reply)} chars): {reply[:60]}...")
                else:
                    warnings.append(f"[{lang}] reply too short or empty: '{reply[:30]}'")

                if monologue and len(monologue) > 5:
                    score += 1
                    print(f"      [{lang}] monologue: {monologue[:50]}...")
                else:
                    warnings.append(f"[{lang}] monologue missing or too short")

                samples.append({
                    "lang": lang,
                    "input": msg,
                    "reply": reply[:100],
                    "monologue": monologue[:80],
                })

        except Exception as e:
            warnings.append(f"Chat test error: {str(e)[:100]}")

        passed = score >= max_score * 0.5
        return {
            "passed": passed,
            "score": score,
            "max_score": max_score,
            "samples": samples,
            "warnings": warnings,
        }

    # ──────────────────────────────────────────────
    # File IO
    # ──────────────────────────────────────────────

    def _write_persona_md(self, persona_id: str, content: str):
        """Write SOUL.md to persona directory."""
        persona_dir = os.path.join(self.persona_loader.personas_dir, persona_id)
        os.makedirs(persona_dir, exist_ok=True)
        path = os.path.join(persona_dir, "SOUL.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"    ✓ Written {path}")



    def delete_persona(self, persona_id: str):
        """Delete persona directory and genesis file."""
        persona_dir = os.path.join(self.persona_loader.personas_dir, persona_id)
        if os.path.exists(persona_dir):
            shutil.rmtree(persona_dir)

        genesis_path = os.path.join(self.genome_data_dir, f"genesis_{persona_id}.json")
        if os.path.exists(genesis_path):
            os.remove(genesis_path)

    # ──────────────────────────────────────────────
    # Parsing Helpers
    # ──────────────────────────────────────────────

    def _clean_markdown_output(self, content: str) -> str:
        """Strip markdown code block wrappers if present."""
        content = content.strip()
        if content.startswith("```"):
            # Remove first line (```markdown or ```)
            lines = content.split("\n")
            lines = lines[1:]  # remove opening ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]  # remove closing ```
            content = "\n".join(lines)
        return content.strip()

    def _parse_json_seeds(self, content: str, default_lang: str) -> list:
        """Parse LLM output as JSON array of seeds."""
        content = content.strip()

        # Strip markdown code block
        if content.startswith("```"):
            lines = content.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)

        # Try to find JSON array
        start = content.find("[")
        end = content.rfind("]")
        if start != -1 and end != -1:
            content = content[start:end + 1]

        try:
            seeds = json.loads(content)
            if isinstance(seeds, list):
                # Ensure each seed has lang
                for s in seeds:
                    if "lang" not in s:
                        s["lang"] = default_lang
                return seeds
        except json.JSONDecodeError as e:
            print(f"    ⚠ JSON parse failed: {e}")
            # Try line-by-line parsing
            seeds = []
            for line in content.split("\n"):
                line = line.strip().rstrip(",")
                if line.startswith("{"):
                    try:
                        seed = json.loads(line)
                        if "lang" not in seed:
                            seed["lang"] = default_lang
                        seeds.append(seed)
                    except:
                        pass
            return seeds

        return []
