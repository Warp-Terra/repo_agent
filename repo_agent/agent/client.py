"""模型客户端创建：支持 Gemini 与 Kimi。"""

from dataclasses import dataclass
from typing import Any

from google import genai

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
    """根据配置创建对应厂商客户端。"""
    provider = load_llm_provider()
    model_id = load_model_id(provider)

    if provider == "gemini":
        api_key = load_provider_api_key("gemini")
        return AgentRuntime(
            provider=provider,
            model_id=model_id,
            client=genai.Client(api_key=api_key),
        )

    if provider == "kimi":
        # 延迟导入，避免仅使用 Gemini 时强依赖 openai 包。
        from openai import OpenAI

        api_key = load_provider_api_key("kimi")
        base_url = load_kimi_base_url()
        return AgentRuntime(
            provider=provider,
            model_id=model_id,
            client=OpenAI(api_key=api_key, base_url=base_url),
        )

    raise ValueError(f"不支持的模型厂商：{provider}")
