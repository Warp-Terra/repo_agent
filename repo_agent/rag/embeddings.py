"""
Embedding 封装：支持本地模型（sentence-transformers）与云端 API（Kimi / OpenAI）。

通过 .env 中 REPO_AGENT_EMBEDDING=kimi 或 openai 使用云端向量化；
kimi 时复用 MOONSHOT_API_KEY（与对话共用），openai 时用 OPENAI_API_KEY。
无需在本地加载 PyTorch，适合内存较小的开发机。
"""

from __future__ import annotations

import os

__all__ = ["get_embedding", "get_embeddings_batch"]

# 模块级缓存：避免每次调用都重新加载模型（PyTorch + 权重），防止内存泄漏
_LOCAL_MODEL_CACHE: object | None = None
_LOCAL_MODEL_NAME: str | None = None
# 仅警告一次：当前进程正在使用 local 向量化（占内存高）
_LOCAL_EMBEDDING_WARNED: bool = False
# 复用单例 OpenAI 客户端，避免每批请求新建 client 导致连接池/缓冲累积（数 GB 级泄漏）
_KIMI_CLIENT: object | None = None
_OPENAI_CLIENT: object | None = None


def _embedding_provider() -> str:
    """当前配置的向量化方式：local / kimi / openai。"""
    from repo_agent.config.settings import load_embedding_provider
    return load_embedding_provider()


def _is_low_memory() -> bool:
    """是否启用低内存模式（仅 local 时生效）。"""
    return os.environ.get("REPO_AGENT_LOW_MEMORY", "").strip().lower() in ("1", "true", "yes")


def _get_local_model():
    """懒加载本地 sentence-transformers 模型，全局缓存避免重复创建。"""
    global _LOCAL_MODEL_CACHE, _LOCAL_MODEL_NAME
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "使用本地 RAG 需要安装可选依赖：pip install 'repo-agent[rag]' 或 pip install sentence-transformers"
        )
    target = "paraphrase-MiniLM-L3-v2" if _is_low_memory() else "all-MiniLM-L6-v2"
    if _LOCAL_MODEL_CACHE is not None and _LOCAL_MODEL_NAME == target:
        return _LOCAL_MODEL_CACHE
    _LOCAL_MODEL_CACHE = SentenceTransformer(target)
    _LOCAL_MODEL_NAME = target
    return _LOCAL_MODEL_CACHE


def _get_kimi_client():
    """复用单例 Kimi（OpenAI 兼容）客户端，避免每批请求新建导致内存累积。"""
    global _KIMI_CLIENT
    if _KIMI_CLIENT is not None:
        return _KIMI_CLIENT
    from openai import OpenAI
    from repo_agent.config.settings import load_embedding_api_key, load_kimi_base_url
    client = OpenAI(
        api_key=load_embedding_api_key("kimi"),
        base_url=load_kimi_base_url(),
    )
    _KIMI_CLIENT = client
    return _KIMI_CLIENT


def _get_openai_client():
    """复用单例 OpenAI 客户端，避免每批请求新建导致内存累积。"""
    global _OPENAI_CLIENT
    if _OPENAI_CLIENT is not None:
        return _OPENAI_CLIENT
    from openai import OpenAI
    from repo_agent.config.settings import load_embedding_api_key
    client = OpenAI(api_key=load_embedding_api_key("openai"))
    _OPENAI_CLIENT = client
    return _OPENAI_CLIENT


def _embed_via_kimi(text: str) -> list[float]:
    """单条文本走 Kimi（Moonshot）Embedding API（OpenAI 兼容 /v1/embeddings）。"""
    from repo_agent.config.settings import KIMI_EMBEDDING_MODEL
    client = _get_kimi_client()
    r = client.embeddings.create(model=KIMI_EMBEDDING_MODEL, input=text)
    return r.data[0].embedding


def _embed_batch_via_kimi(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """批量走 Kimi Embedding API（复用单例 client，避免内存泄漏）。"""
    from repo_agent.config.settings import KIMI_EMBEDDING_MODEL
    client = _get_kimi_client()
    out: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        r = client.embeddings.create(model=KIMI_EMBEDDING_MODEL, input=batch)
        by_idx = {d.index: d.embedding for d in r.data}
        out.extend([by_idx[j] for j in range(len(batch))])
    return out


def _embed_via_openai(text: str) -> list[float]:
    """单条文本走 OpenAI Embedding API。"""
    client = _get_openai_client()
    r = client.embeddings.create(model="text-embedding-3-small", input=text)
    return r.data[0].embedding


def _embed_batch_via_openai(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """批量走 OpenAI（复用单例 client，避免内存泄漏）。"""
    client = _get_openai_client()
    out: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        r = client.embeddings.create(model="text-embedding-3-small", input=batch)
        by_idx = {d.index: d.embedding for d in r.data}
        out.extend([by_idx[j] for j in range(len(batch))])
    return out


def get_embedding(text: str) -> list[float]:
    """
    将单段文本编码为向量。

    根据 REPO_AGENT_EMBEDDING（local / kimi / openai）选择本地模型或云端 API。
    kimi 时复用 MOONSHOT_API_KEY，openai 时用 OPENAI_API_KEY。
    """
    provider = _embedding_provider()
    if provider == "local":
        model = _get_local_model()
        vec = model.encode(text, normalize_embeddings=True)
        return vec.tolist()
    if provider == "kimi":
        return _embed_via_kimi(text)
    if provider == "openai":
        return _embed_via_openai(text)
    raise ValueError(f"不支持的向量化方式：{provider}")


def get_embeddings_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """
    批量编码多段文本，适合建索引时使用。

    云端 API 时不会在本地加载任何模型，内存占用极低。
    """
    global _LOCAL_EMBEDDING_WARNED
    if not texts:
        return []
    provider = _embedding_provider()
    if provider == "local":
        if not _LOCAL_EMBEDDING_WARNED:
            _LOCAL_EMBEDDING_WARNED = True
            print(
                "[RAG] 当前使用本地 embedding 模型，内存占用约 1–2GB。"
                " 若期望使用云端 API，请在 .env 中设置 REPO_AGENT_EMBEDDING=kimi 或 openai。",
                flush=True,
            )
        model = _get_local_model()
        vecs = model.encode(texts, normalize_embeddings=True, batch_size=batch_size)
        return [v.tolist() for v in vecs]
    if provider == "kimi":
        return _embed_batch_via_kimi(texts, batch_size=batch_size)
    if provider == "openai":
        return _embed_batch_via_openai(texts, batch_size=batch_size)
    raise ValueError(f"不支持的向量化方式：{provider}")
