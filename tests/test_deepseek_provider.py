from providers import api_config, config, registry
from providers.llm.deepseek import DeepSeekLLMProvider


def test_deepseek_provider_defaults():
    assert DeepSeekLLMProvider.PROVIDER_NAME == "deepseek"
    assert DeepSeekLLMProvider.DEFAULT_BASE_URL == "https://api.deepseek.com"
    assert DeepSeekLLMProvider.DEFAULT_API_KEY_ENV == "DEEPSEEK_API_KEY"
    assert DeepSeekLLMProvider.DEFAULT_MODEL == "deepseek-v4-pro"


def test_registry_creates_deepseek_provider(monkeypatch):
    monkeypatch.setattr(
        registry,
        "get_llm_provider_config",
        lambda: {
            "active_provider": "deepseek",
            "model": "deepseek-v4-pro",
            "temperature": 0.92,
            "max_tokens": 1024,
            "providers": {
                "deepseek": {
                    "base_url": "https://api.deepseek.com",
                    "api_key_env": "DEEPSEEK_API_KEY",
                    "default_model": "deepseek-v4-pro",
                }
            },
        },
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    provider = registry.get_llm(provider="deepseek")

    assert isinstance(provider, DeepSeekLLMProvider)
    assert provider.model == "deepseek-v4-pro"


def test_api_config_reads_utf8_yaml(monkeypatch, tmp_path):
    config_path = tmp_path / "api.yaml"
    config_path.write_text(
        "llm:\n  provider: deepseek  # 中文注释\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(api_config, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(api_config, "_config", None)
    monkeypatch.delenv("DEFAULT_PROVIDER", raising=False)

    assert api_config.get_llm_config()["provider"] == "deepseek"


def test_registry_config_reads_utf8_yaml(monkeypatch, tmp_path):
    config_path = tmp_path / "api.yaml"
    config_path.write_text(
        "llm:\n  provider: deepseek  # 中文注释\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "_CONFIG_PATH", config_path)
    monkeypatch.setattr(config, "_config", None)
    monkeypatch.delenv("DEFAULT_PROVIDER", raising=False)

    assert config.get_llm_provider_config()["active_provider"] == "deepseek"
