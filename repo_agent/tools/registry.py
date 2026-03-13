"""
工具注册表：统一管理工具函数与函数声明。

新增工具时：
1. 在对应子模块（如 repo.py、rag.py）中实现函数
2. 在本模块的 TOOL_FUNCTIONS 与 TOOL_DECLARATIONS 中注册
"""

from repo_agent.tools import repo, rag as rag_tools

# 工具函数映射（名称 -> 可调用函数）
TOOL_FUNCTIONS = {
    "search_files": repo.search_files,
    "read_file": repo.read_file,
    "list_dir": repo.list_dir,
    "search_knowledge_base": rag_tools.search_knowledge_base,
}

# 中立函数声明（可映射到 OpenAI tools 格式）
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
                    "description": "结束行号（包含该行，默认 120）",
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
    {
        "name": "search_knowledge_base",
        "description": (
            "在知识库中做语义检索，返回与问题最相关的代码或文档片段（路径、行号、内容摘要）。"
            "适合先了解「和这个问题相关的部分在哪」，再配合 read_file 精读。"
            "首次调用时若索引为空会自动构建，无需用户手动执行 build-kb；可直接使用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "自然语言问题或关键词，如「用户登录在哪里实现」「配置如何加载」",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回的最相关条数，默认 5，建议 3～10",
                },
            },
            "required": ["query"],
        },
    },
]
