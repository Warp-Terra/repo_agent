"""
RAG 工具：语义检索知识库，供 Agent 在回答前获取相关片段。

首次在本项目调用且知识库为空时，会自动构建索引后再检索，无需事先手动 build-kb。
"""

from __future__ import annotations

from pathlib import Path


def search_knowledge_base(query: str, top_k: int = 5) -> str:
    """
    在知识库中做语义检索，返回与问题最相关的代码/文档片段。

    若当前项目尚未构建索引，会先自动构建再检索（仅首次稍慢）。
    适合先理解「和这个问题相关的代码或文档在哪」，再配合 read_file 精读。

    Args:
        query: 自然语言问题或关键词，如「用户登录在哪里实现」「配置如何加载」
        top_k: 返回的最相关条数，默认 5

    Returns:
        格式化后的检索结果，包含路径、行号与内容摘要；无 RAG 依赖时返回安装提示。
    """
    try:
        from repo_agent.rag import retrieve
    except ImportError:
        return (
            "当前未安装 RAG 依赖，无法使用知识库检索。"
            "请执行：pip install 'repo-agent[rag]' 或 pipx inject repo-agent sentence-transformers numpy"
        )

    top_k = max(1, min(int(top_k), 20))
    root = Path.cwd()
    results = retrieve(query=query, top_k=top_k, project_root=root)

    # 知识库为空时尝试「轻量」自动构建，严格限制规模避免进程被系统杀掉
    if not results:
        try:
            from repo_agent.kb import build_index
            # 限制：最多 150 个文件、1500 块，避免大仓库一次性占满内存
            n = build_index(
                project_root=root,
                max_files=150,
                max_chunks=1500,
            )
            if n == 0:
                return (
                    "当前项目下没有可索引的文本文件，无法构建知识库。"
                    "请确认在包含 .py / .md 等代码或文档的项目根目录下使用。"
                )
            results = retrieve(query=query, top_k=top_k, project_root=root)
            if not results:
                return "知识库已构建但检索无结果，请换一种问法或关键词重试。"
            auto_note = (
                "（已自动完成轻量索引构建，约 150 个文件内 / 1500 块；"
                "若需完整索引请在本项目下执行：repo-agent build-kb）\n\n"
            )
        except ImportError:
            return (
                "知识库为空且无法自动构建（缺少 RAG 依赖）。"
                "请执行：pip install 'repo-agent[rag]'，然后在本项目下执行：repo-agent build-kb"
            )
    else:
        auto_note = ""

    lines = [auto_note + f"根据「{query}」检索到 {len(results)} 条相关片段："]
    for i, r in enumerate(results, 1):
        path = r.get("path") or "?"
        start = r.get("start_line")
        end = r.get("end_line")
        loc = f"{path}"
        if start is not None:
            loc += f":{start}"
            if end is not None and end != start:
                loc += f"-{end}"
        content = (r.get("content") or "").strip()
        if len(content) > 400:
            content = content[:400] + "..."
        lines.append(f"\n  [{i}] {loc}")
        lines.append(f"      {content}")

    return "\n".join(lines)
