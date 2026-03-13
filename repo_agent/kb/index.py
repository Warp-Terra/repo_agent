"""
知识库索引：对 loader 产出的文档分块、向量化并写入 rag.store。

采用流式按批处理，每批最多 STREAM_BATCH_CHUNKS 块即写入存储并释放内存，
避免整仓一次性载入导致 MemoryError。
REPO_AGENT_LOW_MEMORY=1 时减小批大小，降低 16GB 内存/无 GPU 机器负载。
"""

from __future__ import annotations

import os
from pathlib import Path

from repo_agent.kb.loader import load_documents
from repo_agent.rag.embeddings import get_embeddings_batch
from repo_agent.rag.store import VectorStore

# 每块最大行数，避免单块过大
CHUNK_MAX_LINES = 50
# 块之间重叠行数（便于上下文连贯）
CHUNK_OVERLAP_LINES = 5


def _is_low_memory() -> bool:
    return os.environ.get("REPO_AGENT_LOW_MEMORY", "").strip().lower() in ("1", "true", "yes")


# 流式写入：每积累这么多块就向量化并写入存储，然后清空，控制内存
STREAM_BATCH_CHUNKS = 100 if _is_low_memory() else 400
# 向量化时每批送入模型的条数
EMBED_BATCH_SIZE = 8 if _is_low_memory() else 32
# 单文件最多保留的块数，防止误读大文件或异常文件占满内存
MAX_CHUNKS_PER_FILE = 500

__all__ = ["build_index"]


def _chunk_text(content: str, path: str) -> list[tuple[str, int, int]]:
    """
    按行分块，返回 (块文本, 起始行, 结束行) 列表。
    """
    lines = content.splitlines()
    if not lines:
        return [(content, 1, 1)]
    chunks = []
    start = 1
    while start <= len(lines):
        end = min(start + CHUNK_MAX_LINES, len(lines))
        block = "\n".join(lines[start - 1 : end])
        if block.strip():
            chunks.append((block, start, end))
            
        if end >= len(lines):
            break
            
        start = end - CHUNK_OVERLAP_LINES + 1
        if start >= end:
            start = end + 1
    if not chunks:
        return [(content, 1, len(lines))]
    return chunks


def _flush_batch(
    store: VectorStore,
    batch_ids: list[str],
    batch_documents: list[str],
    batch_metadatas: list[dict],
) -> None:
    """将当前一批块向量化并写入存储，调用方随后应清空这批列表以释放内存。"""
    if not batch_ids:
        return
    embeddings = get_embeddings_batch(batch_documents, batch_size=EMBED_BATCH_SIZE)
    for i in range(0, len(batch_ids), EMBED_BATCH_SIZE):
        store.add(
            ids=batch_ids[i : i + EMBED_BATCH_SIZE],
            embeddings=embeddings[i : i + EMBED_BATCH_SIZE],
            documents=batch_documents[i : i + EMBED_BATCH_SIZE],
            metadatas=batch_metadatas[i : i + EMBED_BATCH_SIZE],
        )


def build_index(
    project_root: Path | None = None,
    max_files: int | None = None,
    max_chunks: int | None = None,
    store: VectorStore | None = None,
) -> int:
    """
    从当前项目加载文档，分块、向量化后写入向量存储。
    会先清空已有索引再写入。采用流式按批处理，内存占用与项目总大小解耦。

    Args:
        project_root: 项目根目录，默认 Path.cwd()
        max_files: 最多索引文件数，None 表示不限制
        max_chunks: 最多索引块数，达到后即停止；None 表示不限制
        store: 外部已初始化的 VectorStore，传入则复用，避免重复创建后端实例

    Returns:
        写入的文档块数量。
    """
    root = project_root or Path.cwd()
    if store is None:
        store = VectorStore(project_root=root)
    store.clear()

    batch_ids: list[str] = []
    batch_documents: list[str] = []
    batch_metadatas: list[dict] = []
    total_count = 0

    for rel_path, content in load_documents(project_root=root, max_files=max_files):
        if max_chunks is not None and total_count >= max_chunks:
            break
        file_chunks = _chunk_text(content, rel_path)
        if len(file_chunks) > MAX_CHUNKS_PER_FILE:
            file_chunks = file_chunks[:MAX_CHUNKS_PER_FILE]
        for chunk_text, start_line, end_line in file_chunks:
            if max_chunks is not None and total_count >= max_chunks:
                break
            chunk_id = f"{rel_path}:{start_line}:{end_line}"
            batch_ids.append(chunk_id)
            batch_documents.append(chunk_text)
            batch_metadatas.append({
                "path": rel_path,
                "start_line": start_line,
                "end_line": end_line,
            })
            total_count += 1

            # 流式写入：每批 STREAM_BATCH_CHUNKS 块就写入并清空，避免整仓进内存
            if len(batch_ids) >= STREAM_BATCH_CHUNKS:
                _flush_batch(store, batch_ids, batch_documents, batch_metadatas)
                batch_ids.clear()
                batch_documents.clear()
                batch_metadatas.clear()

    _flush_batch(store, batch_ids, batch_documents, batch_metadatas)
    return total_count
