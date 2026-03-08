"""
Unified Provider Architecture — core/providers/

按能力分层，一个供应商一个文件。

  llm/       → LLM 对话 (dashscope, openai, deepseek, moonshot, ollama)
  speech/    → 语音 (tts/, asr/, live/)
  memory/    → 记忆 (soulmem 常驻, evermemos 可选)
"""
