"""
配置模块 repo_agent.config.settings 的单元测试。
"""

import os
from pathlib import Path

import pytest

from repo_agent.config import settings


def test_parse_env_file(tmp_path):
    """测试 .env 解析：注释、空行、引号、多 key。"""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\n"
        "KEY1=value1\n"
        "\n"
        "KEY2=value2\n"
        'KEY3="quoted"\n'
        "KEY4='single'\n"
        "KEY5=  spaced  \n"
        "NO_EQUAL\n",
        encoding="utf-8",
    )
    got = settings._parse_env_file(env_file)
    assert got["KEY1"] == "value1"
    assert got["KEY2"] == "value2"
    assert got["KEY3"] == "quoted"
    assert got["KEY4"] == "single"
    assert got["KEY5"] == "spaced"
    assert "NO_EQUAL" not in got


def test_parse_env_file_missing_returns_empty():
    """不存在的 .env 应返回空字典（内部会 OSError）。"""
    got = settings._parse_env_file(Path("/nonexistent/.env"))
    assert got == {}


def test_normalize_provider_kimi():
    """支持的厂商名应被标准化为小写。"""
    assert settings._normalize_provider("kimi") == "kimi"
    assert settings._normalize_provider("Kimi") == "kimi"


def test_normalize_provider_aliases():
    """moonshot / openai_compat 等别名应映射到 kimi。"""
    assert settings._normalize_provider("moonshot") == "kimi"
    assert settings._normalize_provider("openai_compat") == "kimi"
    assert settings._normalize_provider("openai-compatible") == "kimi"


def test_normalize_provider_unsupported_raises():
    """不支持的厂商（如 gemini、unknown）应抛出 ValueError。"""
    with pytest.raises(ValueError, match="不支持的 LLM_PROVIDER"):
        settings._normalize_provider("unknown")
    with pytest.raises(ValueError, match="不支持的 LLM_PROVIDER"):
        settings._normalize_provider("gemini")


def test_load_llm_provider_default(clean_env):
    """未设置 LLM_PROVIDER 时默认应为 kimi。"""
    assert settings.load_llm_provider() == "kimi"


def test_load_llm_provider_from_env(clean_env, monkeypatch):
    """应从环境变量读取 LLM_PROVIDER。"""
    monkeypatch.setenv("LLM_PROVIDER", "kimi")
    assert settings.load_llm_provider() == "kimi"


def test_load_model_id_kimi(clean_env, monkeypatch):
    """kimi 时应返回对应默认或配置的 model id。"""
    monkeypatch.setenv("LLM_PROVIDER", "kimi")
    assert "kimi" in settings.load_model_id()
    monkeypatch.setenv("KIMI_MODEL_ID", "moonshot-v1")
    assert settings.load_model_id() == "moonshot-v1"


def test_load_agentd_port_default(clean_env):
    """未设置 AGENTD_PORT 时应为默认 8765。"""
    assert settings.load_agentd_port() == 8765


def test_load_agentd_port_from_env(clean_env, monkeypatch):
    """应从环境变量解析整数端口。"""
    monkeypatch.setenv("AGENTD_PORT", "9000")
    assert settings.load_agentd_port() == 9000


def test_load_agentd_port_invalid_falls_back(clean_env, monkeypatch):
    """无效端口（非数字或越界）应回退到默认。"""
    monkeypatch.setenv("AGENTD_PORT", "not_a_number")
    assert settings.load_agentd_port() == 8765
    monkeypatch.setenv("AGENTD_PORT", "0")
    assert settings.load_agentd_port() == 8765
    monkeypatch.setenv("AGENTD_PORT", "99999")
    assert settings.load_agentd_port() == 8765
