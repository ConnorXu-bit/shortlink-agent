"""Agent 决策层：模型决策 → 工具执行 → 观察回填 → 再次决策，直到给出最终回复。

LLM 客户端为可注入依赖（鸭子类型），测试中可用 stub 替换，无需真实
API 调用；本模块不感知 DeepSeek / OpenAI 之外的任何存储细节。
"""

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional

ExecuteTool = Callable[[str, dict], str]

DEFAULT_MAX_TURNS = 10
DEFAULT_MAX_TOOL_ROUNDS = 5
DEFAULT_MAX_PARALLEL_TOOLS = 4


def trim_history(messages: List[dict], max_turns: int = DEFAULT_MAX_TURNS) -> List[dict]:
    """滑动窗口：保留最近 max_turns 轮消息，控制单次请求的 Token 成本。

    一轮对话 = 1 条 user + 1 条 assistant，因此最多保留 max_turns*2 条。
    """
    max_messages = max_turns * 2
    if len(messages) > max_messages:
        return messages[-max_messages:]
    return messages


class Agent:
    """Function Calling 决策-执行-观察循环。

    每轮循环：
    1. 带 tools 调用模型，得到可能携带 tool_calls 的回复；
    2. 逐个执行工具，把结果以 role="tool" 消息回填；
    3. 带着执行结果再次调用模型——模型可能继续请求工具，也可能直接给出回复。

    循环在「模型不再请求工具」时结束；若达到 max_tool_rounds 仍在请求工具，
    则摘掉 tools 再问一次，强制模型用自然语言收尾，避免调用链不收敛。
    """

    def __init__(
        self,
        client,
        tools: list,
        execute_tool: ExecuteTool,
        model: str = "deepseek-chat",
        max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
    ) -> None:
        self.client = client
        self.tools = tools
        self.execute_tool = execute_tool
        self.model = model
        self.max_tool_rounds = max_tool_rounds

    def chat(self, messages: List[dict]) -> str:
        """处理一轮用户对话，内部可能发生多轮工具调用。

        传入的 messages 不会被修改（所有中间消息都追加在副本上）。
        """
        work = list(messages)

        for _ in range(self.max_tool_rounds):
            message = self._create(work, with_tools=True)

            tool_calls = getattr(message, "tool_calls", None)
            if not tool_calls:
                return message.content or ""

            # 一次决策可能产生多个工具调用：assistant 消息只追加一次，
            # 再按 tool_call_id 逐条附加执行结果，保证消息配对正确。
            work.append(self._assistant_message(message))
            work.extend(self._run_tool_calls(tool_calls))

        # 达到轮数上限仍在请求工具：摘掉 tools 强制收尾，避免死循环和空回复。
        return self._create(work, with_tools=False).content or ""

    def _create(self, messages: List[dict], with_tools: bool):
        """调用一次模型。with_tools=False 时模型无法再请求工具。"""
        kwargs = {"model": self.model, "messages": messages}
        if with_tools:
            kwargs["tools"] = self.tools
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message

    @staticmethod
    def _assistant_message(message) -> dict:
        """把模型的工具调用决定转换成可回填进 messages 的 assistant 消息。"""
        return {
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

    def _run_tool_calls(self, tool_calls: list) -> List[dict]:
        """执行一批工具调用，返回与之一一配对的 role="tool" 消息。

        同一轮里的多个工具调用彼此独立（协议上互不依赖），而且都是 I/O 密集
        （Redis 往返），因此并发执行；用 map 保证回填顺序与 tool_calls 一致。
        """
        if not tool_calls:
            return []
        workers = min(len(tool_calls), DEFAULT_MAX_PARALLEL_TOOLS)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(self._run_one_tool, tool_calls))

    def _run_one_tool(self, tool_call) -> dict:
        try:
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            arguments = {}
        result = self.execute_tool(tool_call.function.name, arguments)
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": result,
        }
