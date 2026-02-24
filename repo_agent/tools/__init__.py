"""
工具模块：为 Agent 提供可调用的工具及函数声明。

- TOOL_FUNCTIONS: 名称 -> 可调用函数
- TOOL_DECLARATIONS: 中立声明列表（可映射到 Gemini/Kimi）
- 新增工具时在 registry 中注册，并在对应子模块中实现。
"""

from repo_agent.tools.registry import TOOL_DECLARATIONS, TOOL_FUNCTIONS

__all__ = ["TOOL_DECLARATIONS", "TOOL_FUNCTIONS"]
