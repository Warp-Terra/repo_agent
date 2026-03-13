"""
检索器：基于 embeddings + store 的语义检索。

供 Agent 工具 search_knowledge_base 或预注入上下文使用。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from repo_agent.rag.embeddings import get_embedding
from repo_agent.rag.store import VectorStore

__all__ = ["retrieve", "Retriever"]


def retrieve(
    query: str,
    top_k: int = 5,
    project_root: Path | None = None,
) -> list[dict[str, Any]]:
    """
    根据自然语言问题检索最相关的文档片段。

    Args:
        query: 用户问题或检索关键词
        top_k: 返回条数
        project_root: 项目根目录，用于定位 .repo_agent_kb，默认 cwd

    Returns:
        列表，每项含 content、path、start_line、end_line 等；
        若知识库为空或未建索引则返回空列表。
    """
    store = VectorStore(project_root=project_root)
    try:
        n = store.count()
    except Exception:
        return []
    if n == 0:
        return []

    embedding = get_embedding(query)
    hits = store.search(query_embedding=embedding, top_k=top_k)
    out = []
    for h in hits:
        meta = h.get("metadata") or {}
        out.append({
            "content": h.get("document") or "",
            "path": meta.get("path", ""),
            "start_line": meta.get("start_line"),
            "end_line": meta.get("end_line"),
            "distance": h.get("distance"),
        })
    return out


class Retriever:
    """检索器封装，可复用同一 store 实例。"""

    def __init__(self, project_root: Path | None = None) -> None:
        self._store = VectorStore(project_root=project_root)

    def retrieve(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """语义检索。若索引为空返回空列表。"""
        try:
            if self._store.count() == 0:
                return []
        except Exception:
            return []
        embedding = get_embedding(query)
        hits = self._store.search(query_embedding=embedding, top_k=top_k)
        return [
            {
                "content": h.get("document") or "",
                "path": (h.get("metadata") or {}).get("path", ""),
                "start_line": (h.get("metadata") or {}).get("start_line"),
                "end_line": (h.get("metadata") or {}).get("end_line"),
                "distance": h.get("distance"),
            }
            for h in hits
        ]
