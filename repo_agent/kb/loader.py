"""
文档加载器：从项目根递归加载文本文件，供知识库索引使用。

与 repo 工具一致的跳过规则，路径限制在项目根内。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

# 与 repo 工具保持一致，避免索引无关目录
SKIP_DIRS = {
    ".git", ".svn", ".hg",
    "__pycache__", ".mypy_cache", ".pytest_cache",
    "node_modules", ".venv", "venv", "env",
    ".tox", ".eggs", "dist", "build",
    ".idea", ".vscode", ".repo_agent_kb",
}

SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dll", ".exe",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".mp3", ".mp4", ".avi", ".mov",
    ".woff", ".woff2", ".ttf", ".eot",
    ".db", ".sqlite", ".sqlite3",
}

# 参与索引的扩展名（白名单）；空表示除 SKIP 外都索引
INDEX_EXTENSIONS = {
    ".py", ".md", ".txt", ".rst", ".json", ".yaml", ".yml",
    ".toml", ".cfg", ".ini", ".sh", ".bat", ".ps1",
    ".js", ".ts", ".jsx", ".tsx", ".vue", ".html", ".css",
}

MAX_FILE_SIZE = 1024 * 1024  # 1 MB


def _should_skip_dir(name: str) -> bool:
    return name in SKIP_DIRS or name.startswith(".")


def _is_indexable_file(filepath: Path) -> bool:
    if filepath.suffix.lower() in SKIP_EXTENSIONS:
        return False
    if INDEX_EXTENSIONS and filepath.suffix.lower() not in INDEX_EXTENSIONS:
        return False
    try:
        if filepath.stat().st_size > MAX_FILE_SIZE:
            return False
    except OSError:
        return False
    return True


def load_documents(
    project_root: Path | None = None,
    max_files: int | None = None,
) -> Iterator[tuple[str, str]]:
    """
    递归遍历项目目录，产出 (相对路径, 文件内容) 供索引分块。

    Args:
        project_root: 项目根目录，默认 Path.cwd()
        max_files: 最多加载文件数，达到后停止；None 表示不限制

    Yields:
        (relative_path_str, content)
    """
    root = (project_root or Path.cwd()).resolve()
    n = 0
    # followlinks=False：不跟随符号链接，避免误索引到其他盘或巨大目录
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
        for name in filenames:
            if max_files is not None and n >= max_files:
                return
            filepath = Path(dirpath) / name
            if os.path.islink(filepath):
                continue
            if not _is_indexable_file(filepath):
                continue
            try:
                text = filepath.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue
            try:
                rel = filepath.relative_to(root)
            except ValueError:
                continue
            n += 1
            yield str(rel), text
