"""
向量存储：持久化向量与元数据，支持语义检索。

默认使用纯 Python + NumPy 的 SimpleStore（按批落盘，内存 <100MB）。
如需 Chroma，可设 REPO_AGENT_USE_CHROMA=1 显式启用（内存占用高）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

__all__ = ["get_store_path", "VectorStore"]


# 项目内存放知识库数据的子目录名
KB_DIR_NAME = ".repo_agent_kb"


def _use_chroma() -> bool:
    """显式设 REPO_AGENT_USE_CHROMA=1 时启用 Chroma 后端（内存占用高，但支持 ANN 加速检索）。"""
    return os.environ.get("REPO_AGENT_USE_CHROMA", "").strip().lower() in ("1", "true", "yes")

_SIMPLE_EMBEDDINGS_FILE = "embeddings.npz"
_SIMPLE_META_FILE = "index_meta.json"
# 按批落盘格式：建索引时不把整库留在内存，仅保留清单与批文件
_CHUNKS_MANIFEST_FILE = "chunks_manifest.json"


def get_store_path(project_root: Path | None = None) -> Path:
    """获取当前项目下知识库向量存储的目录。"""
    root = project_root or Path.cwd()
    return root / KB_DIR_NAME


def _try_chroma_store(store_path: Path) -> Any:
    """若已安装 Chroma 则返回 Chroma 实现的 store 适配器，否则返回 None。"""
    try:
        import chromadb
    except ImportError:
        return None
    try:
        client = chromadb.PersistentClient(path=str(store_path))
        coll = client.get_or_create_collection(
            name="repo_kb",
            metadata={"description": "repo-agent 知识库向量"},
        )
        return _ChromaAdapter(client, coll)
    except Exception:
        return None


class _ChromaAdapter:
    """Chroma 后端的统一接口适配器。"""

    def __init__(self, client: Any, collection: Any) -> None:
        self._client = client
        self._collection = collection

    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None,
    ) -> None:
        meta = metadatas or [{}] * len(ids)
        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=meta,
        )

    def search(self, query_embedding: list[float], top_k: int) -> list[dict[str, Any]]:
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, 100),
            include=["documents", "metadatas", "distances"],
        )
        docs = result["documents"][0] if result["documents"] else []
        metas = result["metadatas"][0] if result["metadatas"] else []
        dists = result["distances"][0] if result["distances"] else []
        return [
            {"document": d, "metadata": m or {}, "distance": float(dist)}
            for d, m, dist in zip(docs, metas, dists)
        ]

    def count(self) -> int:
        return self._collection.count()

    def clear(self) -> None:
        self._client.delete_collection("repo_kb")
        self._collection = self._client.get_or_create_collection(
            name="repo_kb",
            metadata={"description": "repo-agent 知识库向量"},
        )


class _SimpleStore:
    """
    纯 Python + NumPy 的向量存储，无需 Chroma/C++。
    使用「按批落盘」格式：建索引时每批写入一个文件，不在内存中累积整库，避免大仓库导致内存爆满。
    检索时按批文件逐个加载、合并 top-k。
    """

    def __init__(self, store_path: Path) -> None:
        self._path = store_path
        self._path.mkdir(parents=True, exist_ok=True)
        self._emb_file = self._path / _SIMPLE_EMBEDDINGS_FILE
        self._meta_file = self._path / _SIMPLE_META_FILE
        self._manifest_file = self._path / _CHUNKS_MANIFEST_FILE
        # 按批模式：只存批文件列表与总数，不把整库放内存
        self._chunked: bool = False
        self._batch_files: list[str] = []
        self._total_count: int = 0
        # 旧格式兼容：单文件全量在内存
        self._ids: list[str] = []
        self._embeddings: Any = None
        self._documents: list[str] = []
        self._metadatas: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self._manifest_file.exists():
            try:
                with open(self._manifest_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._batch_files = data.get("batch_files") or []
                self._total_count = int(data.get("total_count") or 0)
                self._chunked = True
            except (json.JSONDecodeError, OSError):
                self._chunked = True
            return
        if not self._emb_file.exists():
            # 空库或新建：默认用按批落盘，避免 build_index 时在内存里累积整库
            self._chunked = True
            return
        try:
            import numpy as np
        except ImportError:
            raise ImportError(
                "简单向量存储需要 numpy。请安装：pip install numpy 或 pip install 'repo-agent[rag]'"
            )
        data = np.load(self._emb_file, allow_pickle=True)
        self._ids = data["ids"].tolist()
        self._embeddings = data["embeddings"]
        self._documents = data["documents"].tolist()
        with open(self._meta_file, "r", encoding="utf-8") as f:
            self._metadatas = json.load(f)
        if len(self._metadatas) != len(self._ids):
            self._metadatas = [{}] * len(self._ids)
        self._chunked = False

    def _save_chunked_manifest(self) -> None:
        with open(self._manifest_file, "w", encoding="utf-8") as f:
            json.dump(
                {"batch_files": self._batch_files, "total_count": self._total_count},
                f,
                ensure_ascii=False,
            )

    def _save(self) -> None:
        """旧格式全量写入（兼容用）。"""
        if len(self._ids) == 0:
            for f in (self._emb_file, self._meta_file):
                if f.exists():
                    f.unlink()
            return
        import numpy as np
        self._path.mkdir(parents=True, exist_ok=True)
        np.savez(
            self._emb_file,
            ids=np.array(self._ids, dtype=object),
            embeddings=np.array(self._embeddings, dtype=np.float32),
            documents=np.array(self._documents, dtype=object),
        )
        with open(self._meta_file, "w", encoding="utf-8") as f:
            json.dump(self._metadatas, f, ensure_ascii=False, indent=0)

    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None,
    ) -> None:
        import numpy as np
        meta = metadatas or [{}] * len(ids)
        arr = np.array(embeddings, dtype=np.float32)
        if self._chunked:
            # 按批落盘：只写当前批，不留在内存
            idx = len(self._batch_files)
            batch_name = f"batch_{idx}.npz"
            batch_path = self._path / batch_name
            self._path.mkdir(parents=True, exist_ok=True)
            np.savez(
                batch_path,
                ids=np.array(ids, dtype=object),
                embeddings=arr,
                documents=np.array(documents, dtype=object),
                metadatas=np.array(meta, dtype=object),
            )
            self._batch_files.append(batch_name)
            self._total_count += len(ids)
            self._save_chunked_manifest()
            return
        if self._embeddings is None:
            self._ids = list(ids)
            self._embeddings = arr
            self._documents = list(documents)
            self._metadatas = list(meta)
        else:
            self._ids.extend(ids)
            self._embeddings = np.vstack([self._embeddings, arr])
            self._documents.extend(documents)
            self._metadatas.extend(meta)
        self._save()

    def search(self, query_embedding: list[float], top_k: int) -> list[dict[str, Any]]:
        import numpy as np
        if self._chunked:
            if self._total_count == 0:
                return []
            q = np.array([query_embedding], dtype=np.float32)
            q_norm = np.linalg.norm(q)
            if q_norm < 1e-9:
                q_norm = 1e-9
            q = q / q_norm
            candidates: list[tuple[float, str, dict, float]] = []
            for batch_name in self._batch_files:
                batch_path = self._path / batch_name
                if not batch_path.exists():
                    continue
                data = np.load(batch_path, allow_pickle=True)
                embs = data["embeddings"]
                docs = data["documents"].tolist()
                metas = data["metadatas"].tolist()
                if embs.shape[0] == 0:
                    continue
                norms = np.linalg.norm(embs, axis=1, keepdims=True)
                norms[norms == 0] = 1e-9
                embs_n = embs / norms
                sim = (embs_n @ q.T).ravel()
                k = min(top_k, len(sim))
                idx = np.argsort(-sim)[:k]
                for i in idx:
                    dist = float(1 - sim[i])
                    doc = docs[i] if i < len(docs) else ""
                    meta = metas[i] if i < len(metas) else {}
                    candidates.append((sim[i], doc, meta, dist))
            if not candidates:
                return []
            candidates.sort(key=lambda x: -x[0])
            return [
                {"document": doc, "metadata": meta, "distance": dist}
                for _, doc, meta, dist in candidates[:top_k]
            ]
        if self._embeddings is None or len(self._ids) == 0:
            return []
        q = np.array([query_embedding], dtype=np.float32)
        norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1e-9
        sim = (self._embeddings / norms) @ (q.T / np.linalg.norm(q))
        sim = sim.ravel()
        k = min(top_k, len(sim))
        idx = np.argsort(-sim)[:k]
        return [
            {
                "document": self._documents[i],
                "metadata": self._metadatas[i],
                "distance": float(1 - sim[i]),
            }
            for i in idx
        ]

    def count(self) -> int:
        if self._chunked:
            return self._total_count
        return len(self._ids) if self._ids else 0

    def clear(self) -> None:
        self._chunked = True
        self._batch_files = []
        self._total_count = 0
        self._ids = []
        self._embeddings = None
        self._documents = []
        self._metadatas = []
        for f in (self._emb_file, self._meta_file, self._manifest_file):
            if f.exists():
                f.unlink()
        for p in list(self._path.glob("batch_*.npz")):
            try:
                p.unlink()
            except OSError:
                pass


class VectorStore:
    """
    向量存储封装：add 写入、search 检索。
    默认使用 SimpleStore（纯 Python + NumPy，按批落盘，内存极低）。
    设 REPO_AGENT_USE_CHROMA=1 可切换到 Chroma（ANN 加速，但内存占用高）。
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self._root = project_root or Path.cwd()
        self._path = get_store_path(self._root)
        self._backend: Any = None

    def _ensure_backend(self) -> Any:
        if self._backend is not None:
            return self._backend
        if _use_chroma():
            self._backend = _try_chroma_store(self._path)
        if self._backend is None:
            self._backend = _SimpleStore(self._path)
        return self._backend

    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        """批量写入文档片段。"""
        self._ensure_backend().add(ids, embeddings, documents, metadatas)

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """按向量相似度检索最相关的 top_k 条。"""
        return self._ensure_backend().search(query_embedding, top_k)

    def count(self) -> int:
        """当前集合中的文档条数。"""
        return self._ensure_backend().count()

    def clear(self) -> None:
        """清空当前集合（重建索引前可调用）。"""
        self._ensure_backend().clear()

    def backend_name(self) -> str:
        """返回当前后端名称，用于诊断。"""
        self._ensure_backend()
        return type(self._backend).__name__
