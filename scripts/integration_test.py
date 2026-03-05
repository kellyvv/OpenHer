"""
Integration test for drive_satisfaction pipeline.

Tests the full Critic → parse → ChatAgent → Agent.satisfy_drive chain
WITHOUT starting the server. Uses a mock LLM to return controlled JSON.

Usage:
    PYTHONPATH=. python scripts/integration_test.py
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.genome.genome_engine import Agent, DRIVES, SIGNALS
from core.genome.drive_metabolism import DriveMetabolism
from core.genome.critic import critic_sense
from core.persona.persona_loader import PersonaLoader
from core.llm.client import LLMClient, ChatMessage


# ══════════════ Mock LLM ══════════════

class MockLLMResponse:
    def __init__(self, content):
        self.content = content

class MockLLM:
    """Returns a fixed Critic JSON response."""
    def __init__(self, critic_json: dict):
        self._response = json.dumps(critic_json, ensure_ascii=False)

    async def chat(self, messages, **kwargs):
        return MockLLMResponse(self._response)


# ══════════════ Tests ══════════════

async def test_critic_returns_4_tuple():
    """Test 1: Critic outputs drive_satisfaction as 4th element."""
    mock_json = {
        "context": {"user_emotion": 0.8, "topic_intimacy": 0.6,
                     "conversation_depth": 0.4, "user_engagement": 0.9,
                     "conflict_level": 0.0, "novelty_level": 0.3,
                     "user_vulnerability": 0.5, "time_of_day": 0.7},
        "frustration_delta": {"connection": -0.2, "novelty": 0.0,
                               "expression": 0.0, "safety": -0.1, "play": 0.0},
        "drive_satisfaction": {"connection": 0.15, "novelty": 0.0,
                                "expression": 0.05, "safety": 0.1, "play": 0.2},
        "relationship_delta": 0.1, "trust_delta": 0.05, "emotional_valence": 0.5
    }

    llm = MockLLM(mock_json)
    result = await critic_sense("你今天心情怎么样？", llm, {d: 0.5 for d in DRIVES})

    assert len(result) == 4, f"Expected 4-tuple, got {len(result)}"
    context, frust_delta, rel_delta, drive_sat = result

    assert 'connection' in drive_sat
    assert drive_sat['play'] == 0.2
    assert drive_sat['connection'] == 0.15
    print("✅ Test 1: Critic returns 4-tuple with drive_satisfaction")
    return drive_sat


async def test_satisfaction_clamp():
    """Test 2: drive_satisfaction values are clamped to [0, 0.3]."""
    mock_json = {
        "context": {f: 0.5 for f in ["user_emotion", "topic_intimacy",
                    "conversation_depth", "user_engagement", "conflict_level",
                    "novelty_level", "user_vulnerability", "time_of_day"]},
        "frustration_delta": {d: 0.0 for d in DRIVES},
        "drive_satisfaction": {"connection": 0.5, "novelty": -0.1,
                                "expression": 0.3, "safety": 0.0, "play": 0.15},
        "relationship_delta": 0.0, "trust_delta": 0.0, "emotional_valence": 0.0
    }

    llm = MockLLM(mock_json)
    _, _, _, drive_sat = await critic_sense("test", llm)

    assert drive_sat['connection'] == 0.3, f"Expected 0.3 (clamped), got {drive_sat['connection']}"
    assert drive_sat['novelty'] == 0.0, f"Expected 0.0 (clamped), got {drive_sat['novelty']}"
    assert drive_sat['expression'] == 0.3
    assert drive_sat['play'] == 0.15
    print("✅ Test 2: drive_satisfaction clamped to [0, 0.3]")


async def test_play_drive_satisfied():
    """Test 3: play drive actually decreases when satisfaction > 0."""
    agent = Agent(seed=42)
    pre_play = agent.drive_state['play']

    ctx = {f: 0.5 for f in ['user_emotion', 'topic_intimacy', 'time_of_day',
           'conversation_depth', 'user_engagement', 'conflict_level',
           'novelty_level', 'user_vulnerability', 'relationship_depth',
           'emotional_valence', 'trust_level', 'pending_foresight']}

    sat = {d: 0.0 for d in DRIVES}
    sat['play'] = 0.25  # Strong play satisfaction

    agent.step(ctx, reward=0.3, drive_satisfaction=sat)
    post_play = agent.drive_state['play']

    assert post_play < pre_play, f"play should decrease: {pre_play:.3f} → {post_play:.3f}"
    print(f"✅ Test 3: play drive satisfied ({pre_play:.3f} → {post_play:.3f})")


async def test_persona_params_loaded():
    """Test 4: All 4 personas load engine_params correctly."""
    loader = PersonaLoader('personas')
    loader.load_all()

    for pid in loader.list_ids():
        p = loader.get(pid)
        assert p.engine_params, f"{p.name} has no engine_params"
        assert 'connection_hunger_k' in p.engine_params
        assert 'phase_threshold' in p.engine_params
        assert 'temp_coeff' in p.engine_params

    print(f"✅ Test 4: All {len(loader.list_ids())} personas have engine_params")


async def test_per_persona_temperature():
    """Test 5: Different personas produce different temperatures."""
    loader = PersonaLoader('personas')
    loader.load_all()

    temps = {}
    for pid in loader.list_ids():
        p = loader.get(pid)
        m = DriveMetabolism(engine_params=p.engine_params)
        m.frustration['connection'] = 1.0  # Same frustration for all
        temps[p.name] = m.temperature()

    # Vivian (INTJ, temp=0.06) should be coldest, Luna (ENFP, temp=0.15) hottest
    assert temps['Vivian'] < temps['Iris'] < temps['Luna'], \
        f"Temperature order wrong: {temps}"
    print(f"✅ Test 5: Temperature differentiation: " +
          ' < '.join(f"{k}={v:.3f}" for k, v in sorted(temps.items(), key=lambda x: x[1])))


async def test_critic_failure_returns_zero_satisfaction():
    """Test 6: When Critic fails to parse, drive_satisfaction defaults to all zeros."""
    class FailLLM:
        async def chat(self, messages, **kwargs):
            return MockLLMResponse("this is not valid json!!!")

    _, _, _, drive_sat = await critic_sense("test", FailLLM())
    assert all(v == 0.0 for v in drive_sat.values()), f"Expected all zeros, got {drive_sat}"
    print("✅ Test 6: Critic parse failure → drive_satisfaction all zeros")


# ══════════════ Main ══════════════

async def main():
    print("=" * 60)
    print("🔬 Integration Test: drive_satisfaction pipeline")
    print("=" * 60)

    await test_critic_returns_4_tuple()
    await test_satisfaction_clamp()
    await test_play_drive_satisfied()
    await test_persona_params_loaded()
    await test_per_persona_temperature()
    await test_critic_failure_returns_zero_satisfaction()

    print()
    print("🎉 ALL 6 INTEGRATION TESTS PASSED")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
