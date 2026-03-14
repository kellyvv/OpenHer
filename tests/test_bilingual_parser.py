"""Tests for bilingual output parser (extract_reply, _extract_monologue, _parse_modality)."""

import pytest
from agent.chat_agent import extract_reply, _parse_modality, _SECTION_RE, _TAG_MAP, ChatAgent
from agent.output_router import parse_raw_output, _extract_primary_modality


# ── Chinese section headers (existing behavior) ──

class TestChineseParsing:
    def test_extract_reply_chinese(self):
        raw = "【内心独白】她想什么呢\n【最终回复】你好啊\n【表达方式】文字"
        monologue, reply, modality = extract_reply(raw)
        assert monologue == "她想什么呢"
        assert reply == "你好啊"
        assert modality == "文字"

    def test_extract_reply_chinese_silence(self):
        raw = "【内心独白】不想说话\n【最终回复】\n【表达方式】静默"
        monologue, reply, modality = extract_reply(raw)
        assert monologue == "不想说话"
        assert reply == ""
        assert modality == "静默"

    def test_extract_monologue_chinese(self):
        raw = "【内心独白】她想什么呢"
        result = ChatAgent._extract_monologue(raw)
        assert result == "她想什么呢"

    def test_extract_monologue_no_marker(self):
        raw = "Just some raw text without markers"
        result = ChatAgent._extract_monologue(raw)
        assert result == "Just some raw text without markers"

    def test_parse_modality_chinese(self):
        assert _parse_modality("文字") == "文字"
        assert _parse_modality("语音") == "语音"
        assert _parse_modality("静默") == "静默"
        assert _parse_modality("表情") == "表情"

    def test_output_router_chinese(self):
        raw = "【内心独白】紧张\n【最终回复】嗯…你好\n【表达方式】文字"
        result = parse_raw_output(raw)
        assert result["monologue"] == "紧张"
        assert result["reply"] == "嗯…你好"
        assert result["modality"] == "文字"


# ── English section headers (fallback behavior) ──

class TestEnglishParsing:
    def test_extract_reply_english(self):
        raw = "[Inner Monologue]She's nervous\n[Final Reply]Hello there\n[Expression Mode]text"
        monologue, reply, modality = extract_reply(raw)
        assert monologue == "She's nervous"
        assert reply == "Hello there"
        assert modality == "文字"  # canonical Chinese key

    def test_extract_reply_english_silence(self):
        raw = "[Inner Monologue]Don't want to talk\n[Final Reply]\n[Expression Mode]silence"
        monologue, reply, modality = extract_reply(raw)
        assert monologue == "Don't want to talk"
        assert reply == ""
        assert modality == "静默"  # canonical Chinese key

    def test_extract_monologue_english(self):
        raw = "[Inner Monologue]She's thinking deeply"
        result = ChatAgent._extract_monologue(raw)
        assert result == "She's thinking deeply"

    def test_parse_modality_english(self):
        assert _parse_modality("text") == "文字"
        assert _parse_modality("voice") == "语音"
        assert _parse_modality("silence") == "静默"
        assert _parse_modality("emoji") == "表情"
        assert _parse_modality("photo") == "照片"
        assert _parse_modality("split") == "多条拆分"

    def test_output_router_english(self):
        raw = "[Inner Monologue]nervous\n[Final Reply]Hi there\n[Expression Mode]text"
        result = parse_raw_output(raw)
        assert result["monologue"] == "nervous"
        assert result["reply"] == "Hi there"
        assert result["modality"] == "text"  # raw text (router returns raw, chat_agent normalizes)

    def test_extract_primary_modality_english(self):
        assert _extract_primary_modality("voice message") == "语音"
        assert _extract_primary_modality("silence") == "静默"
        assert _extract_primary_modality("text") == "文字"
        assert _extract_primary_modality("emoji sticker") == "表情"


# ── Edge cases ──

class TestEdgeCases:
    def test_extract_reply_fallback_no_markers(self):
        raw = "Just a plain reply"
        monologue, reply, modality = extract_reply(raw)
        assert monologue == ""
        assert reply == "Just a plain reply"
        assert modality == "文字"

    def test_modality_canonical_return(self):
        """extract_reply should return canonical modality key, not raw text."""
        raw = "【内心独白】hmm\n【最终回复】hello\n【表达方式】voice message because feeling emotional"
        _, _, modality = extract_reply(raw)
        assert modality == "语音"  # canonical key, not raw "voice message..."

    def test_modality_unknown_defaults_to_text(self):
        assert _parse_modality("something random") == "文字"
        assert _parse_modality("") == "文字"
