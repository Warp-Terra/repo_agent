"""
仓库工具 repo_agent.tools.repo 的单元测试（路径安全、跳过目录、文本文件判断、公开 API）。
"""

from pathlib import Path

import pytest

from repo_agent.tools import repo


def test_should_skip_dir():
    """应跳过 .git、__pycache__、. 开头的目录等。"""
    assert repo._should_skip_dir(".git") is True
    assert repo._should_skip_dir("__pycache__") is True
    assert repo._should_skip_dir(".pytest_cache") is True
    assert repo._should_skip_dir(".venv") is True
    assert repo._should_skip_dir("node_modules") is True
    assert repo._should_skip_dir(".hidden") is True
    assert repo._should_skip_dir("src") is False
    assert repo._should_skip_dir("repo_agent") is False


def test_is_text_file_skips_extensions(tmp_path):
    """应跳过 .pyc、.png 等非文本扩展名。"""
    (tmp_path / "a.pyc").touch()
    (tmp_path / "b.png").touch()
    assert repo._is_text_file(tmp_path / "a.pyc") is False
    assert repo._is_text_file(tmp_path / "b.png") is False


def test_is_text_file_accepts_py(tmp_path):
    """应接受 .py 等文本文件。"""
    (tmp_path / "x.py").write_text("print(1)", encoding="utf-8")
    assert repo._is_text_file(tmp_path / "x.py") is True


def test_safe_resolve_within_root():
    """项目内的相对路径应解析为绝对路径。"""
    root = Path.cwd()
    # 当前目录
    got = repo._safe_resolve(".")
    assert got is not None
    assert got.resolve() == root.resolve()
    # 子路径（若存在）
    if (root / "repo_agent").is_dir():
        got = repo._safe_resolve("repo_agent")
        assert got is not None
        assert got.resolve() == (root / "repo_agent").resolve()


def test_safe_resolve_path_traversal_returns_none():
    """路径逃逸（.. 超出项目根）应返回 None。"""
    # 在项目根下，.. 会指向父目录，relative_to(root) 会失败
    assert repo._safe_resolve("..") is None
    assert repo._safe_resolve("../etc/passwd") is None
    assert repo._safe_resolve("sub/../../..") is None


def test_read_file_unsafe_path_returns_error():
    """read_file 对不安全路径应返回错误信息。"""
    out = repo.read_file("../../../etc/passwd")
    assert "错误" in out
    assert "不安全" in out or "不在项目目录内" in out


def test_read_file_nonexistent_returns_error():
    """read_file 对不存在文件应返回错误信息。"""
    out = repo.read_file("nonexistent_file_xyz_123.py")
    assert "错误" in out
    assert "不存在" in out


def test_list_dir_unsafe_path_returns_error():
    """list_dir 对不安全路径应返回错误信息。"""
    out = repo.list_dir("../../../")
    assert "错误" in out
    assert "不安全" in out or "不在项目目录内" in out


def test_list_dir_current_dir():
    """list_dir('.') 应返回当前目录的树状结构。"""
    out = repo.list_dir(".")
    assert "错误" not in out
    assert "./" in out or ".\n" in out or out.strip().startswith(".")


def test_search_files_returns_string():
    """search_files 应返回字符串（无匹配时也返回说明）。"""
    out = repo.search_files("some_nonexistent_token_xyz_12345")
    assert isinstance(out, str)
    assert "未找到" in out or "找到" in out
