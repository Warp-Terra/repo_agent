"""
知识库模块：本地知识库的构建与管理。

- loader: 文档加载（按扩展名过滤）
- index: 索引构建（分块、向量化、写入 rag.store）
"""

from repo_agent.kb.index import build_index
from repo_agent.kb.loader import load_documents

__all__ = ["load_documents", "build_index"]
