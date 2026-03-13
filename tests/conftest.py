"""
pytest 共享配置与 fixture。
"""

import os

import pytest


@pytest.fixture(autouse=True)
def _reset_config_cache(monkeypatch):
    """每个测试后清除配置模块的 .env 缓存，避免测试间污染。"""
    import repo_agent.config.settings as settings

    monkeypatch.setattr(settings, "_DOTENV_CACHE", None)
    yield
    monkeypatch.setattr(settings, "_DOTENV_CACHE", None)


@pytest.fixture
def clean_env(monkeypatch):
    """清除与 LLM/Agent 相关的环境变量并忽略 .env，便于测试默认值或仅环境变量。"""
    import repo_agent.config.settings as settings

    keys = [
        "LLM_PROVIDER",
        "MOONSHOT_API_KEY", "KIMI_API_KEY", "OPENAI_API_KEY",
        "KIMI_MODEL_ID", "LLM_MODEL_ID", "KIMI_BASE_URL", "OPENAI_BASE_URL",
        "AGENTD_HOST", "AGENTD_PORT", "AGENTD_TOKEN",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    # 测试期间不读取真实 .env，避免本地配置影响断言
    monkeypatch.setattr(settings, "_load_dotenv_values", lambda: {})
    yield
