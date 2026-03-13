"""模型客户端创建：Kimi（OpenAI 兼容）。"""

from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from repo_agent.config import (
    load_kimi_base_url,
    load_llm_provider,
    load_model_id,
    load_provider_api_key,
)


@dataclass
class AgentRuntime:
    """统一的运行时对象，封装厂商、模型与底层客户端。"""

    provider: str
    model_id: str
    client: Any


def create_client() -> AgentRuntime:
    """根据配置创建 Kimi（OpenAI 兼容）客户端。"""
    provider = load_llm_provider()
    model_id = load_model_id(provider)
    api_key = load_provider_api_key("kimi")
    base_url = load_kimi_base_url()
    return AgentRuntime(
        provider=provider,
        model_id=model_id,
        client=OpenAI(api_key=api_key, base_url=base_url),
    )
