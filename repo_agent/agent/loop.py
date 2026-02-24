"""Agent 主循环：支持 Gemini 与 Kimi(OpenAI 兼容) 的对话与工具调用。"""

import json
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable

from google.genai import types

from repo_agent.agent.client import AgentRuntime, create_client
from repo_agent.agent.prompts import MAX_TOOL_CALLS_PER_TURN, SYSTEM_PROMPT
from repo_agent.tools import TOOL_DECLARATIONS, TOOL_FUNCTIONS

# 限流重试配置
MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 10  # 秒
# 原始工具请求上限（用于防止重复调用导致死循环）
MAX_RAW_TOOL_CALLS_PER_TURN = 60

AgentEventHandler = Callable[[str, dict[str, Any]], None]


@dataclass
class FunctionCallRecord:
    """统一后的工具调用记录。"""

    name: str
    args: dict[str, Any]
    call_id: str | None = None


def _print_event(event_type: str, payload: dict[str, Any]) -> None:
    """默认事件输出，保持原有 CLI 体验。"""
    if event_type == "rate_limit_retry":
        attempt = payload.get("attempt", "?")
        delay = payload.get("delay_seconds", 0)
        print(f"  [限流] 第 {attempt} 次重试，等待 {delay:.0f} 秒...")
        return
    if event_type == "rate_limit_failed":
        retries = payload.get("max_retries", MAX_RETRIES)
        print(f"  [限流] 已重试 {retries} 次仍失败。")
        return
    if event_type == "tool_call":
        index = payload.get("index", "?")
        name = payload.get("name", "unknown")
        args = payload.get("args", {})
        args_display = json.dumps(args, ensure_ascii=False)
        print(f"  [工具调用 #{index}] {name}({args_display})")
        return
    if event_type == "tool_deduplicated":
        print("  [工具去重] 检测到连续重复调用，复用上一次结果。")
        return
    if event_type == "tool_result":
        preview = payload.get("preview", "")
        print(f"  [工具结果] {preview}")
        print()
        return
    if event_type == "warning":
        message = payload.get("message", "")
        print(f"  [警告] {message}")
        return


def _emit_event(
    event_handler: AgentEventHandler | None,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """分发 Agent 事件；未提供处理器时走默认控制台输出。"""
    if event_handler is None:
        _print_event(event_type, payload)
        return
    try:
        event_handler(event_type, payload)
    except Exception:
        # 事件回调不应影响主流程
        pass


def _call_with_retry(
    request_fn: Callable[[], Any],
    event_handler: AgentEventHandler | None = None,
) -> Any:
    """
    带自动重试的 API 调用封装。
    遇到 429 限流错误时，从错误信息中提取等待时间并自动重试。
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return request_fn()
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                delay = DEFAULT_RETRY_DELAY
                match = re.search(r"retry\s+in\s+([\d.]+)s", error_msg, re.IGNORECASE)
                if match:
                    delay = min(float(match.group(1)), 60)
                if attempt < MAX_RETRIES:
                    _emit_event(
                        event_handler,
                        "rate_limit_retry",
                        {"attempt": attempt, "delay_seconds": delay},
                    )
                    time.sleep(delay)
                    continue
                _emit_event(
                    event_handler,
                    "rate_limit_failed",
                    {"max_retries": MAX_RETRIES},
                )
            raise


def build_tools(provider: str) -> Any:
    """根据不同厂商构建工具声明。"""
    if provider == "gemini":
        declarations = [
            types.FunctionDeclaration(
                name=d["name"],
                description=d["description"],
                parameters_json_schema=d["parameters"],
            )
            for d in TOOL_DECLARATIONS
        ]
        return [types.Tool(function_declarations=declarations)]

    if provider == "kimi":
        return [
            {
                "type": "function",
                "function": {
                    "name": d["name"],
                    "description": d["description"],
                    "parameters": d["parameters"],
                },
            }
            for d in TOOL_DECLARATIONS
        ]

    raise ValueError(f"不支持的模型厂商：{provider}")


def _append_user_message(provider: str, history: list[Any], user_input: str) -> None:
    """向历史中追加用户消息。"""
    if provider == "gemini":
        history.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_input)],
            )
        )
        return

    if provider == "kimi":
        history.append({"role": "user", "content": user_input})
        return

    raise ValueError(f"不支持的模型厂商：{provider}")


def _invoke_gemini(
    runtime: AgentRuntime,
    history: list[Any],
    tools: list[types.Tool],
    event_handler: AgentEventHandler | None = None,
) -> tuple[str, list[FunctionCallRecord], Any]:
    """执行一轮 Gemini 调用，并归一化返回结构。"""
    response = _call_with_retry(
        lambda: runtime.client.models.generate_content(
            model=runtime.model_id,
            contents=history,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=tools,
            ),
        ),
        event_handler=event_handler,
    )

    candidate = response.candidates[0]
    function_calls = [
        FunctionCallRecord(
            name=fc.name,
            args=dict(fc.args) if fc.args else {},
        )
        for fc in (response.function_calls or [])
    ]
    return (response.text or "", function_calls, candidate.content)


def _invoke_kimi(
    runtime: AgentRuntime,
    history: list[Any],
    tools: list[dict[str, Any]],
    event_handler: AgentEventHandler | None = None,
) -> tuple[str, list[FunctionCallRecord], dict[str, Any]]:
    """执行一轮 Kimi(OpenAI 兼容)调用，并归一化返回结构。"""
    response = _call_with_retry(
        lambda: runtime.client.chat.completions.create(
            model=runtime.model_id,
            messages=history,
            tools=tools,
            tool_choice="auto",
            temperature=0.0,
        ),
        event_handler=event_handler,
    )

    message = response.choices[0].message
    tool_calls = message.tool_calls or []

    normalized_calls: list[FunctionCallRecord] = []
    serialized_tool_calls: list[dict[str, Any]] = []
    for call in tool_calls:
        args_text = call.function.arguments or "{}"
        try:
            args = json.loads(args_text) if args_text else {}
        except json.JSONDecodeError:
            args = {}

        normalized_calls.append(
            FunctionCallRecord(
                name=call.function.name,
                args=args,
                call_id=call.id,
            )
        )
        serialized_tool_calls.append(
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": args_text,
                },
            }
        )

    assistant_payload: dict[str, Any] = {
        "role": "assistant",
        "content": message.content or "",
    }
    if serialized_tool_calls:
        assistant_payload["tool_calls"] = serialized_tool_calls

    return (message.content or "", normalized_calls, assistant_payload)


def _invoke_model_turn(
    runtime: AgentRuntime,
    history: list[Any],
    tools: Any,
    event_handler: AgentEventHandler | None = None,
) -> tuple[str, list[FunctionCallRecord], Any]:
    """统一的一轮模型调用入口。"""
    if runtime.provider == "gemini":
        return _invoke_gemini(runtime, history, tools, event_handler=event_handler)
    if runtime.provider == "kimi":
        return _invoke_kimi(runtime, history, tools, event_handler=event_handler)
    raise ValueError(f"不支持的模型厂商：{runtime.provider}")


def _append_tool_results(
    provider: str,
    history: list[Any],
    tool_results: list[tuple[FunctionCallRecord, str]],
) -> None:
    """将工具执行结果追加到对话历史。"""
    if provider == "gemini":
        parts = [
            types.Part.from_function_response(
                name=fc.name,
                response={"result": result},
            )
            for fc, result in tool_results
        ]
        history.append(types.Content(role="tool", parts=parts))
        return

    if provider == "kimi":
        for fc, result in tool_results:
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": fc.call_id or "",
                    "content": result,
                }
            )
        return

    raise ValueError(f"不支持的模型厂商：{provider}")


def _append_assistant_text(provider: str, history: list[Any], text: str) -> None:
    """将最终 assistant 文本追加到历史。"""
    if provider == "gemini":
        history.append(
            types.Content(
                role="assistant",
                parts=[types.Part.from_text(text=text)],
            )
        )
        return

    if provider == "kimi":
        history.append({"role": "assistant", "content": text})
        return

    raise ValueError(f"不支持的模型厂商：{provider}")


def _execute_tool(name: str, args: dict[str, Any]) -> str:
    """执行工具函数并返回结果字符串。"""
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return f"错误：未知的工具函数 '{name}'"
    try:
        return str(func(**args))
    except Exception as e:
        return f"工具执行出错：{type(e).__name__}: {e}"


def _build_tool_signature(name: str, args: dict[str, Any]) -> str:
    """构造工具调用签名，用于重复调用识别。"""
    try:
        args_key = json.dumps(args, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except TypeError:
        args_key = str(args)
    return f"{name}|{args_key}"


def _build_tool_cap_answer(
    tool_call_count: int,
    max_calls: int,
    tool_result_previews: list[str],
    raw_tool_call_count: int | None = None,
    raw_limit: int | None = None,
) -> str:
    """构造达到工具调用上限时的本地兜底回答，避免额外 API 请求。"""
    if raw_tool_call_count is not None and raw_limit is not None and raw_tool_call_count >= raw_limit:
        lines = [
            f"本轮检测到工具请求过多（原始请求 {raw_tool_call_count}/{raw_limit}），可能存在重复调用循环，已停止继续调用模型。",
        ]
    else:
        lines = [
            f"本轮已达到工具调用上限（有效调用 {tool_call_count}/{max_calls}），为降低请求次数已停止继续调用模型。",
        ]

    if tool_result_previews:
        lines.append("已获取信息摘要：")
        lines.extend(f"- {preview}" for preview in tool_result_previews)
    lines.append("如需更精确结果，请缩小提问范围后重试。")
    return "\n".join(lines)


def _get_role(message: Any) -> str:
    """获取历史消息角色。"""
    if hasattr(message, "role"):
        return str(getattr(message, "role"))
    if isinstance(message, dict):
        return str(message.get("role", ""))
    return ""


def agent_turn(
    runtime: AgentRuntime,
    tools: Any,
    history: list[Any],
    user_input: str,
    event_handler: AgentEventHandler | None = None,
) -> str:
    """
    执行一轮完整的 Agent 交互（从用户输入到最终回答）。

    Returns:
        Agent 的最终文本回答
    """
    _append_user_message(runtime.provider, history, user_input)

    # 有效调用次数：不统计“连续重复 tool+args 且复用缓存”的情况
    tool_call_count = 0
    # 原始请求次数：统计模型发起的所有 tool call，用于循环保护
    raw_tool_call_count = 0
    tool_result_cache: dict[str, str] = {}
    last_tool_signature: str | None = None
    tool_result_previews: list[str] = []

    while True:
        response_text, function_calls, assistant_payload = _invoke_model_turn(
            runtime,
            history,
            tools,
            event_handler=event_handler,
        )
        history.append(assistant_payload)

        if not function_calls:
            return response_text or "(模型未返回文本内容)"

        tool_results: list[tuple[FunctionCallRecord, str]] = []
        for fc in function_calls:
            raw_tool_call_count += 1
            if runtime.provider == "kimi" and not fc.call_id:
                fc.call_id = f"call_{raw_tool_call_count}"

            _emit_event(
                event_handler,
                "tool_call",
                {"index": raw_tool_call_count, "name": fc.name, "args": fc.args},
            )

            signature = _build_tool_signature(fc.name, fc.args)
            is_consecutive_duplicate = (
                signature == last_tool_signature and signature in tool_result_cache
            )

            if is_consecutive_duplicate:
                result = tool_result_cache[signature]
                _emit_event(
                    event_handler,
                    "tool_deduplicated",
                    {"name": fc.name, "args": fc.args},
                )
            else:
                tool_call_count += 1
                result = _execute_tool(fc.name, fc.args)
                tool_result_cache[signature] = result

            result_preview = result[:200] + "..." if len(result) > 200 else result
            _emit_event(
                event_handler,
                "tool_result",
                {"name": fc.name, "preview": result_preview},
            )
            tool_result_previews.append(f"{fc.name}: {result_preview}")
            tool_results.append((fc, result))
            last_tool_signature = signature

        _append_tool_results(runtime.provider, history, tool_results)

        if tool_call_count >= MAX_TOOL_CALLS_PER_TURN:
            _emit_event(
                event_handler,
                "warning",
                {"message": f"已达到单轮最大有效工具调用次数 ({MAX_TOOL_CALLS_PER_TURN})，强制结束。"},
            )
            local_answer = _build_tool_cap_answer(
                tool_call_count=tool_call_count,
                max_calls=MAX_TOOL_CALLS_PER_TURN,
                tool_result_previews=tool_result_previews[-5:],
            )
            _append_assistant_text(runtime.provider, history, local_answer)
            return local_answer

        if raw_tool_call_count >= MAX_RAW_TOOL_CALLS_PER_TURN:
            _emit_event(
                event_handler,
                "warning",
                {
                    "message": (
                        f"原始工具请求次数过多 ({raw_tool_call_count}/{MAX_RAW_TOOL_CALLS_PER_TURN})，"
                        "疑似重复循环，强制结束。"
                    )
                },
            )
            local_answer = _build_tool_cap_answer(
                tool_call_count=tool_call_count,
                max_calls=MAX_TOOL_CALLS_PER_TURN,
                tool_result_previews=tool_result_previews[-5:],
                raw_tool_call_count=raw_tool_call_count,
                raw_limit=MAX_RAW_TOOL_CALLS_PER_TURN,
            )
            _append_assistant_text(runtime.provider, history, local_answer)
            return local_answer


def main() -> None:
    """主函数：初始化并运行交互循环。"""
    print("=" * 60)
    print("  本地代码仓库问答 Agent")
    print("=" * 60)
    print()

    try:
        runtime = create_client()
    except ValueError as e:
        print(f"初始化失败：{e}")
        sys.exit(1)

    print(f"  提供商: {runtime.provider}")
    print(f"  模型: {runtime.model_id}")
    print("  输入问题开始对话，Ctrl+C 退出")
    print()

    tools = build_tools(runtime.provider)
    history: list[Any] = []

    print("Agent 已就绪。请输入您的问题：\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n再见！")
            break

        if not user_input:
            continue

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
            answer = agent_turn(runtime, tools, history, user_input)
            print(f"Agent: {answer}")
        except Exception as e:
            print(f"Agent 错误：{type(e).__name__}: {e}")
            if history and _get_role(history[-1]) == "user":
                history.pop()
        print()


if __name__ == "__main__":
    main()
