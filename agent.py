"""
Agent 主循环模块：实现基于 Gemini Function Calling 的代码仓库问答 Agent。

流程：
1. 用户输入问题
2. 发送给 Gemini，附带工具声明
3. 如果模型返回 function_call，执行对应工具函数
4. 将工具结果发回模型
5. 重复 3-4，直到模型返回最终文本回答
6. 打印回答，回到步骤 1
"""

import json
import re
import sys
import time
from typing import Any

from google import genai
from google.genai import types

from config import load_api_key
from tools import TOOL_DECLARATIONS, TOOL_FUNCTIONS


# ========================================
# 常量
# ========================================

MODEL_ID = "gemini-2.5-flash"

# 限流重试配置
MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 10  # 秒

SYSTEM_PROMPT = """\
你是一个本地代码仓库分析助手。

## 行为准则

- 你不能凭空猜测文件内容，必须通过工具获取真实信息。
- 如果需要了解文件内容或项目结构，必须调用工具。
- 回答必须使用中文，但代码标识符（函数名、变量名、类名等）保持英文。
- 不要假设文件存在，先通过 list_dir 或 search_files 确认。
- 优先使用 search_files 获取信息，再用 read_file 查看具体内容。
- 如果搜索结果不够，可以多次调用不同的工具来获取完整信息。
- 回答要准确、简洁，基于工具返回的真实数据。

## 工具使用策略

1. 了解项目结构 → list_dir
2. 查找特定代码 → search_files
3. 查看文件详情 → read_file
"""

# 单轮对话中最大工具调用次数（防止无限循环）
MAX_TOOL_CALLS_PER_TURN = 15


# ========================================
# 核心函数
# ========================================

def _call_with_retry(client: genai.Client, **kwargs) -> Any:
    """
    带自动重试的 API 调用封装。
    遇到 429 限流错误时，从错误信息中提取等待时间并自动重试。

    Args:
        client: Gemini 客户端
        **kwargs: 传给 generate_content 的参数

    Returns:
        API 响应对象
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return client.models.generate_content(**kwargs)
        except Exception as e:
            error_msg = str(e)
            # 检查是否为限流错误（429）
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                # 尝试从错误信息中提取等待时间
                delay = DEFAULT_RETRY_DELAY
                match = re.search(r"retry\s+in\s+([\d.]+)s", error_msg, re.IGNORECASE)
                if match:
                    delay = float(match.group(1))
                    delay = min(delay, 60)  # 最多等 60 秒

                if attempt < MAX_RETRIES:
                    print(f"  [限流] 第 {attempt} 次重试，等待 {delay:.0f} 秒...")
                    time.sleep(delay)
                    continue
                else:
                    print(f"  [限流] 已重试 {MAX_RETRIES} 次仍失败。")
            raise


def create_client() -> genai.Client:
    """创建 Gemini API 客户端。"""
    api_key = load_api_key()
    return genai.Client(api_key=api_key)


def build_tools() -> list[types.Tool]:
    """根据工具声明构建 Gemini Tool 对象。"""
    declarations = []
    for decl in TOOL_DECLARATIONS:
        fd = types.FunctionDeclaration(
            name=decl["name"],
            description=decl["description"],
            parameters_json_schema=decl["parameters"],
        )
        declarations.append(fd)
    return [types.Tool(function_declarations=declarations)]


def execute_tool(name: str, args: dict[str, Any]) -> str:
    """
    执行工具函数并返回结果字符串。

    Args:
        name: 工具函数名称
        args: 工具函数参数

    Returns:
        工具执行结果的字符串表示
    """
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return f"错误：未知的工具函数 '{name}'"

    try:
        result = func(**args)
        return str(result)
    except Exception as e:
        return f"工具执行出错：{type(e).__name__}: {e}"


def agent_turn(
    client: genai.Client,
    tools: list[types.Tool],
    history: list[types.Content],
    user_input: str,
) -> str:
    """
    执行一轮完整的 Agent 交互（从用户输入到最终回答）。

    Args:
        client: Gemini 客户端
        tools: 工具列表
        history: 对话历史（会被原地修改）
        user_input: 用户输入文本

    Returns:
        Agent 的最终文本回答
    """
    # 1. 将用户消息加入历史
    user_content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=user_input)],
    )
    history.append(user_content)

    # 2. 循环调用模型，直到得到文本回答
    tool_call_count = 0

    while True:
        # 调用模型（带限流重试）
        response = _call_with_retry(
            client,
            model=MODEL_ID,
            contents=history,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=tools,
            ),
        )

        # 获取模型回复的 Content
        candidate = response.candidates[0]
        model_content = candidate.content

        # 将模型回复加入历史
        history.append(model_content)

        # 检查是否包含 function call
        function_calls = response.function_calls
        if not function_calls:
            # 没有 function call，返回文本回答
            return response.text or "(模型未返回文本内容)"

        # 3. 执行所有 function call
        tool_response_parts = []
        for fc in function_calls:
            func_name = fc.name
            func_args = dict(fc.args) if fc.args else {}
            tool_call_count += 1

            # 打印工具调用日志
            args_display = json.dumps(func_args, ensure_ascii=False)
            print(f"  [工具调用 #{tool_call_count}] {func_name}({args_display})")

            # 执行工具
            result = execute_tool(func_name, func_args)

            # 打印结果摘要（截断过长的结果）
            result_preview = result[:200] + "..." if len(result) > 200 else result
            print(f"  [工具结果] {result_preview}")
            print()

            # 构建 function response part
            tool_response_parts.append(
                types.Part.from_function_response(
                    name=func_name,
                    response={"result": result},
                )
            )

        # 4. 将工具结果加入历史
        tool_content = types.Content(
            role="tool",
            parts=tool_response_parts,
        )
        history.append(tool_content)

        # 5. 检查是否超过最大工具调用次数
        if tool_call_count >= MAX_TOOL_CALLS_PER_TURN:
            print(f"  [警告] 已达到单轮最大工具调用次数 ({MAX_TOOL_CALLS_PER_TURN})，强制结束。")
            # 再调用一次模型让它总结
            history.append(types.Content(
                role="user",
                parts=[types.Part.from_text(
                    text="请根据已获取的信息直接回答问题，不要再调用工具。"
                )],
            ))
            final_response = _call_with_retry(
                client,
                model=MODEL_ID,
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                ),
            )
            final_content = final_response.candidates[0].content
            history.append(final_content)
            return final_response.text or "(模型未返回文本内容)"

        # 继续循环，让模型处理工具结果


def main() -> None:
    """主函数：初始化并运行交互循环。"""
    print("=" * 60)
    print("  本地代码仓库问答 Agent")
    print(f"  模型: {MODEL_ID}")
    print("  输入问题开始对话，Ctrl+C 退出")
    print("=" * 60)
    print()

    # 初始化
    try:
        client = create_client()
    except ValueError as e:
        print(f"初始化失败：{e}")
        sys.exit(1)

    tools = build_tools()
    history: list[types.Content] = []

    print("Agent 已就绪。请输入您的问题：\n")

    # 交互循环
    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n再见！")
            break

        if not user_input:
            continue

        # 特殊命令
        if user_input.lower() in ("/quit", "/exit", "/q"):
            print("\n再见！")
            break
        if user_input.lower() in ("/clear", "/reset"):
            history.clear()
            print("对话历史已清除。\n")
            continue
        if user_input.lower() == "/help":
            print("可用命令：")
            print("  /clear  - 清除对话历史")
            print("  /quit   - 退出程序")
            print("  /help   - 显示帮助")
            print()
            continue

        print()
        try:
            answer = agent_turn(client, tools, history, user_input)
            print(f"Agent: {answer}")
        except Exception as e:
            print(f"Agent 错误：{type(e).__name__}: {e}")
            # 出错时移除最后的用户消息，避免历史污染
            if history and history[-1].role == "user":
                history.pop()
        print()


if __name__ == "__main__":
    main()
