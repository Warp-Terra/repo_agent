"""
RAG 模块：本地检索增强生成。

- embeddings: 本地 Embedding（sentence-transformers）
- store: 向量存储（Chroma）
- retriever: 检索器，供 Agent 工具或上下文注入使用
"""

from repo_agent.rag.embeddings import get_embedding, get_embeddings_batch
from repo_agent.rag.retriever import Retriever, retrieve
from repo_agent.rag.store import VectorStore, get_store_path

__all__ = [
    "get_embedding",
    "get_embeddings_batch",
    "VectorStore",
    "get_store_path",
    "retrieve",
    "Retriever",
]
