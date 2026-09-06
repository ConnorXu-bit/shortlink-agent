"""Agent 决策层：模型决策 → 工具执行 → 生成最终回复。

LLM 客户端为可注入依赖（鸭子类型），测试中可用 stub 替换，无需真实
API 调用；本模块不感知 DeepSeek / OpenAI 之外的任何存储细节。
"""

import json
from typing import Callable, List, Optional

ExecuteTool = Callable[[str, dict], str]

DEFAULT_MAX_TURNS = 10


def trim_history(messages: List[dict], max_turns: int = DEFAULT_MAX_TURNS) -> List[dict]:
    """滑动窗口：保留最近 max_turns 轮消息，控制单次请求的 Token 成本。

    一轮对话 = 1 条 user + 1 条 assistant，因此最多保留 max_turns*2 条。
    """
    max_messages = max_turns * 2
    if len(messages) > max_messages:
        return messages[-max_messages:]
    return messages


class Agent:
    """单轮 Function Calling 决策-执行-回复循环。

    典型流程：
    1. 带 tools 调用模型，得到可能携带 tool_calls 的回复；
    2. 逐个执行工具，把结果以 role="tool" 消息回填；
    3. 再次调用模型，把工具结果合成为自然语言回复。
    """

    def __init__(
        self,
        client,
        tools: list,
        execute_tool: ExecuteTool,
        model: str = "deepseek-chat",
    ) -> None:
        self.client = client
        self.tools = tools
        self.execute_tool = execute_tool
        self.model = model

    def chat(self, messages: List[dict]) -> str:
        """处理一轮用户对话。传入的 messages 不会被修改（内部消息在副本上展开）。"""
        work = list(messages)

        response = self.client.chat.completions.create(
            model=self.model, messages=work, tools=self.tools
        )
        message = response.choices[0].message

        if not getattr(message, "tool_calls", None):
            return message.content or ""

        # 一次决策可能产生多个工具调用：assistant 消息只追加一次，
        # 再按 tool_call_id 逐条附加执行结果，保证消息配对正确。
        work.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments,
                        },
                    }
                    for tool_call in message.tool_calls
                ],
            }
        )

        for tool_call in message.tool_calls:
            try:
                arguments = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                arguments = {}
            result = self.execute_tool(tool_call.function.name, arguments)
            work.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

        final_response = self.client.chat.completions.create(
            model=self.model, messages=work
        )
        return final_response.choices[0].message.content or ""
