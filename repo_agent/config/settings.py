"""配置模块：读取模型厂商、模型 ID 与 API Key。"""

import os
from pathlib import Path

SUPPORTED_PROVIDERS = {"kimi"}
DEFAULT_PROVIDER = "kimi"
DEFAULT_MODEL_IDS = {
    "kimi": "kimi-k2-turbo-preview",
}
DEFAULT_KIMI_BASE_URL = "https://api.moonshot.cn/v1"
DEFAULT_AGENTD_HOST = "127.0.0.1"
DEFAULT_AGENTD_PORT = 8765

_DOTENV_CACHE: dict[str, str] | None = None


def _parse_env_file(path: Path) -> dict[str, str]:
    """解析 .env 文件中的 KEY=VALUE 配置。"""
    values: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or not line or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and value:
                    values[key] = value
    except OSError:
        return {}
    return values


def _load_dotenv_values() -> dict[str, str]:
    """
    加载 .env 配置。
    优先级：当前工作目录 > 包所在项目根目录。
    """
    global _DOTENV_CACHE
    if _DOTENV_CACHE is not None:
        return _DOTENV_CACHE

    merged: dict[str, str] = {}
    bases = (Path(__file__).resolve().parent.parent.parent, Path.cwd())
    for base in bases:
        env_path = base / ".env"
        if env_path.exists():
            merged.update(_parse_env_file(env_path))
    _DOTENV_CACHE = merged
    return merged


def _get_config_value(keys: list[str]) -> str | None:
    """按优先级读取配置值：环境变量 > .env。"""
    for key in keys:
        value = os.environ.get(key)
        if value:
            return value

    dotenv_values = _load_dotenv_values()
    for key in keys:
        value = dotenv_values.get(key)
        if value:
            return value
    return None


def _normalize_provider(value: str) -> str:
    """标准化厂商标识。"""
    provider = value.strip().lower()
    aliases = {
        "moonshot": "kimi",
        "openai_compat": "kimi",
        "openai-compatible": "kimi",
    }
    provider = aliases.get(provider, provider)
    if provider not in SUPPORTED_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_PROVIDERS))
        raise ValueError(f"不支持的 LLM_PROVIDER: {provider}，可选值：{supported}")
    return provider


def load_llm_provider() -> str:
    """读取当前模型厂商，默认 kimi。"""
    raw = _get_config_value(["LLM_PROVIDER"]) or DEFAULT_PROVIDER
    return _normalize_provider(raw)


def load_model_id(provider: str | None = None) -> str:
    """读取当前厂商对应的模型 ID。"""
    resolved_provider = provider or load_llm_provider()
    if resolved_provider == "kimi":
        return _get_config_value(["KIMI_MODEL_ID", "LLM_MODEL_ID"]) or DEFAULT_MODEL_IDS["kimi"]
    raise ValueError(f"未知厂商：{resolved_provider}")


def load_provider_api_key(provider: str | None = None) -> str:
    """读取厂商 API Key。"""
    resolved_provider = provider or load_llm_provider()
    if resolved_provider == "kimi":
        key = _get_config_value(["MOONSHOT_API_KEY", "KIMI_API_KEY", "OPENAI_API_KEY"])
        if key:
            return key
        raise ValueError(
            "未找到 Kimi API Key。\n"
            "请设置 MOONSHOT_API_KEY（推荐），或 KIMI_API_KEY / OPENAI_API_KEY"
        )
    raise ValueError(f"未知厂商：{resolved_provider}")


def load_kimi_base_url() -> str:
    """读取 Kimi OpenAI 兼容接口地址。"""
    return _get_config_value(["KIMI_BASE_URL", "OPENAI_BASE_URL"]) or DEFAULT_KIMI_BASE_URL


def load_api_key() -> str:
    """兼容旧接口：读取 Kimi API Key。"""
    return load_provider_api_key("kimi")


def load_agentd_host() -> str:
    """读取 Agent 服务监听主机。"""
    return _get_config_value(["AGENTD_HOST"]) or DEFAULT_AGENTD_HOST


def load_agentd_port() -> int:
    """读取 Agent 服务监听端口。"""
    raw = _get_config_value(["AGENTD_PORT"])
    if raw is None:
        return DEFAULT_AGENTD_PORT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_AGENTD_PORT
    if value <= 0 or value > 65535:
        return DEFAULT_AGENTD_PORT
    return value


def load_agentd_token() -> str | None:
    """读取 Agent 服务访问令牌。"""
    token = _get_config_value(["AGENTD_TOKEN"])
    if not token:
        return None
    return token


# RAG 向量化：local（本地模型）| kimi | openai，默认 kimi（云端 API，不占本地内存）
EMBEDDING_PROVIDERS = {"local", "kimi", "openai"}
DEFAULT_EMBEDDING_PROVIDER = "kimi"

# Kimi 向量化模型名（Moonshot 兼容 OpenAI /v1/embeddings 接口）
KIMI_EMBEDDING_MODEL = "moonshot-v1-embedding"


def load_embedding_provider() -> str:
    """读取 RAG 向量化方式：local / kimi（Moonshot-v1-embedding）/ openai。"""
    raw = _get_config_value(["REPO_AGENT_EMBEDDING", "REPO_AGENT_EMBEDDING_PROVIDER"])
    if not raw:
        return DEFAULT_EMBEDDING_PROVIDER
    p = raw.strip().lower()
    if p not in EMBEDDING_PROVIDERS:
        return DEFAULT_EMBEDDING_PROVIDER
    return p


def load_embedding_api_key(provider: str) -> str:
    """读取云端 Embedding 所用 API Key（kimi 用 MOONSHOT_API_KEY，openai 用 OPENAI_API_KEY）。"""
    if provider == "kimi":
        key = _get_config_value(["MOONSHOT_API_KEY", "KIMI_API_KEY", "OPENAI_API_KEY"])
        if key:
            return key
        raise ValueError(
            "未找到 MOONSHOT_API_KEY。使用 Kimi 向量化时请在 .env 中设置 MOONSHOT_API_KEY（与对话共用即可）。"
        )
    if provider == "openai":
        key = _get_config_value(["OPENAI_API_KEY"])
        if key:
            return key
        raise ValueError(
            "未找到 OPENAI_API_KEY。使用云端向量化时请在 .env 中设置 OPENAI_API_KEY。"
        )
    raise ValueError(f"本地向量化无需 API Key：{provider}")
