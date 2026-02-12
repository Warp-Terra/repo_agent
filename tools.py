"""
工具函数模块：提供本地代码仓库的只读访问能力。

包含三个工具：
- search_files: 在仓库中搜索包含指定文本的文件
- read_file: 读取指定文件的内容片段
- list_dir: 列出目录结构（限制深度 2 层）

所有路径操作都限制在项目根目录内，禁止路径逃逸。
"""

import os
import re
from pathlib import Path
from typing import Optional


# 需要跳过的目录和文件模式
SKIP_DIRS = {
    ".git", ".svn", ".hg",
    "__pycache__", ".mypy_cache", ".pytest_cache",
    "node_modules", ".venv", "venv", "env",
    ".tox", ".eggs", "dist", "build",
    ".idea", ".vscode",
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

# 单个文件最大读取大小（字节），防止读取超大文件
MAX_FILE_SIZE = 1024 * 1024  # 1 MB


def _get_project_root() -> Path:
    """获取项目根目录（当前工作目录）。"""
    return Path.cwd()


def _safe_resolve(path_str: str) -> Optional[Path]:
    """
    安全解析路径，确保路径在项目根目录内。

    Args:
        path_str: 用户提供的路径字符串

    Returns:
        解析后的绝对路径，如果路径不安全则返回 None
    """
    root = _get_project_root()
    try:
        # 将路径解析为绝对路径
        target = (root / path_str).resolve()
        # 检查是否在项目根目录内
        target.relative_to(root.resolve())
        return target
    except (ValueError, OSError):
        return None


def _is_text_file(filepath: Path) -> bool:
    """粗略判断文件是否为文本文件。"""
    if filepath.suffix.lower() in SKIP_EXTENSIONS:
        return False
    # 检查文件大小
    try:
        if filepath.stat().st_size > MAX_FILE_SIZE:
            return False
    except OSError:
        return False
    return True


def _should_skip_dir(dirname: str) -> bool:
    """判断是否应该跳过该目录。"""
    return dirname in SKIP_DIRS or dirname.startswith(".")


def search_files(query: str) -> str:
    """
    在当前项目目录中递归搜索包含指定文本的文件。

    Args:
        query: 搜索关键词（支持普通文本，大小写不敏感）

    Returns:
        匹配结果的格式化字符串，包含文件路径、行号和内容片段。
        最多返回 30 条匹配结果。
    """
    root = _get_project_root()
    results: list[str] = []
    max_results = 30
    files_scanned = 0

    # 编译搜索模式（大小写不敏感）
    try:
        pattern = re.compile(re.escape(query), re.IGNORECASE)
    except re.error:
        return f"搜索模式无效：{query}"

    for dirpath, dirnames, filenames in os.walk(root):
        # 过滤跳过的目录（原地修改 dirnames 以阻止递归进入）
        dirnames[:] = [
            d for d in dirnames
            if not _should_skip_dir(d)
        ]

        for filename in filenames:
            filepath = Path(dirpath) / filename
            if not _is_text_file(filepath):
                continue

            files_scanned += 1

            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    for line_num, line in enumerate(f, start=1):
                        if pattern.search(line):
                            # 计算相对路径
                            rel_path = filepath.relative_to(root)
                            # 截断过长的行
                            content = line.rstrip()
                            if len(content) > 200:
                                content = content[:200] + "..."
                            results.append(
                                f"  {rel_path}:{line_num}: {content}"
                            )
                            if len(results) >= max_results:
                                break
            except (OSError, UnicodeDecodeError):
                continue

            if len(results) >= max_results:
                break

        if len(results) >= max_results:
            break

    if not results:
        return f"未找到包含 \"{query}\" 的文件（已扫描 {files_scanned} 个文件）。"

    header = f"找到 {len(results)} 条匹配（已扫描 {files_scanned} 个文件）：\n"
    return header + "\n".join(results)


def read_file(path: str, start_line: int = 1, end_line: int = 50) -> str:
    """
    读取指定文件的内容片段。

    Args:
        path: 文件的相对路径（相对于项目根目录）
        start_line: 起始行号（从 1 开始，默认 1）
        end_line: 结束行号（包含，默认 50）

    Returns:
        文件内容片段，带行号标注
    """
    # 安全路径检查
    filepath = _safe_resolve(path)
    if filepath is None:
        return f"错误：路径不安全或不在项目目录内：{path}"

    if not filepath.exists():
        return f"错误：文件不存在：{path}"

    if not filepath.is_file():
        return f"错误：路径不是文件：{path}"

    if not _is_text_file(filepath):
        return f"错误：文件不是文本文件或体积过大：{path}"

    # 参数规范化
    start_line = max(1, int(start_line))
    end_line = max(start_line, int(end_line))

    # 限制单次读取不超过 200 行
    if end_line - start_line > 200:
        end_line = start_line + 200

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        return f"错误：无法读取文件 {path}：{e}"

    total_lines = len(lines)
    if start_line > total_lines:
        return f"错误：起始行 {start_line} 超出文件总行数 {total_lines}。"

    # 截取目标范围（转为 0-based 索引）
    selected = lines[start_line - 1 : end_line]

    # 带行号输出
    output_lines = []
    for i, line in enumerate(selected, start=start_line):
        output_lines.append(f"  {i:>4} | {line.rstrip()}")

    header = f"文件：{path}（第 {start_line}-{min(end_line, total_lines)} 行，共 {total_lines} 行）\n"
    return header + "\n".join(output_lines)


def list_dir(path: str = ".") -> str:
    """
    列出指定目录的结构（最深 2 层）。

    Args:
        path: 目录的相对路径（相对于项目根目录，默认为根目录）

    Returns:
        目录结构的树状表示
    """
    # 安全路径检查
    dirpath = _safe_resolve(path)
    if dirpath is None:
        return f"错误：路径不安全或不在项目目录内：{path}"

    if not dirpath.exists():
        return f"错误：目录不存在：{path}"

    if not dirpath.is_dir():
        return f"错误：路径不是目录：{path}"

    root = _get_project_root()
    output_lines: list[str] = []

    def _walk(current: Path, prefix: str, depth: int) -> None:
        """递归遍历目录，最多 2 层。"""
        if depth > 2:
            return

        try:
            entries = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name))
        except OSError:
            return

        # 分类
        dirs = [e for e in entries if e.is_dir() and not _should_skip_dir(e.name)]
        files = [e for e in entries if e.is_file()]

        items = dirs + files
        for i, item in enumerate(items):
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            if item.is_dir():
                output_lines.append(f"{prefix}{connector}{item.name}/")
                extension = "    " if is_last else "│   "
                _walk(item, prefix + extension, depth + 1)
            else:
                output_lines.append(f"{prefix}{connector}{item.name}")

    rel_display = dirpath.relative_to(root) if dirpath != root else Path(".")
    output_lines.append(f"{rel_display}/")
    _walk(dirpath, "", 1)

    if len(output_lines) == 1:
        return f"目录 {path} 为空。"

    return "\n".join(output_lines)


# ========================================
# 工具注册表：供 agent.py 使用
# ========================================

# 工具函数映射（名称 -> 可调用函数）
TOOL_FUNCTIONS = {
    "search_files": search_files,
    "read_file": read_file,
    "list_dir": list_dir,
}

# Gemini Function Declarations（使用 google-genai SDK 格式）
TOOL_DECLARATIONS = [
    {
        "name": "search_files",
        "description": (
            "在当前代码仓库中递归搜索包含指定文本的文件。"
            "返回匹配的文件路径、行号和内容片段。"
            "适合用于查找函数定义、类定义、特定字符串、import 语句等。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "要搜索的文本关键词，例如函数名、类名、变量名或任意字符串",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_file",
        "description": (
            "读取指定文件的内容片段。"
            "需要提供文件的相对路径（相对于项目根目录）以及可选的起止行号。"
            "用于查看文件具体内容、理解代码逻辑。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件的相对路径，例如 'src/main.py' 或 'README.md'",
                },
                "start_line": {
                    "type": "integer",
                    "description": "起始行号（从 1 开始，默认 1）",
                },
                "end_line": {
                    "type": "integer",
                    "description": "结束行号（包含该行，默认 50）",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_dir",
        "description": (
            "列出指定目录的文件和子目录结构（最深 2 层）。"
            "用于了解项目结构、发现文件。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要列出的目录的相对路径，默认为项目根目录 '.'",
                },
            },
            "required": [],
        },
    },
]
