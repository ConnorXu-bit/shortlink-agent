"""可编排响应的 OpenAI 客户端替身：无真实 API 也能测试 Agent 决策链路。"""

import json
import copy
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
        # 必须快照：Agent 会持续往同一个 messages 列表追加，
        # 直接存引用的话，每条记录看到的都是"最终状态"而不是"当时的模样"。
        record = dict(kwargs)
        if "messages" in record:
            record["messages"] = copy.deepcopy(record["messages"])
        self.calls.append(record)
        if not self.responses:
            raise AssertionError("模型响应序列已耗尽，请为每次 create 配置响应")
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))
        self.completions = self.chat.completions
