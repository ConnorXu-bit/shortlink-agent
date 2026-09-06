"""可编排响应的 OpenAI 客户端替身：无真实 API 也能测试 Agent 决策链路。"""

import json
from types import SimpleNamespace


def make_tool_call(name, arguments, call_id="call_1"):
    """构造与 OpenAI 响应同构的 tool_call 对象。"""
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def make_message(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def make_response(message):
    """包装为 response.choices[0].message 形状。"""
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeCompletions:
    """记录每次 create 调用，并按配置顺序返回预设响应。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("模型响应序列已耗尽，请为每次 create 配置响应")
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))
        self.completions = self.chat.completions
