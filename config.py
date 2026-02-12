"""
配置模块：读取 Gemini API Key。

支持两种方式：
1. 环境变量 GEMINI_API_KEY
2. 项目根目录下的 .env 文件（GEMINI_API_KEY=xxx）
"""

import os
from pathlib import Path


def load_api_key() -> str:
    """
    读取 Gemini API Key。
    优先从环境变量读取，其次从 .env 文件读取。

    Returns:
        API Key 字符串

    Raises:
        ValueError: 未找到 API Key 时抛出
    """
    # 1. 尝试从环境变量读取
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        return api_key

    # 2. 尝试从 .env 文件读取
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                if line.startswith("GEMINI_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if api_key:
                        return api_key

    raise ValueError(
        "未找到 GEMINI_API_KEY。\n"
        "请通过以下方式之一设置：\n"
        "  1. 设置环境变量：export GEMINI_API_KEY=your_key\n"
        "  2. 在 repo_agent/ 目录下创建 .env 文件，写入：GEMINI_API_KEY=your_key"
    )
