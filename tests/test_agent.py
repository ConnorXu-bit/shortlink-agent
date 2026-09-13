"""Agent 决策链路测试：mock LLM，验证决策-执行-观察循环与消息配对。"""

import time

import fakeredis

from agent import Agent
from tools import TOOLS, ShortLinkToolbox, make_tool_dispatcher
from fakes import (
    FakeClient,
    make_message,
    make_response,
    make_tool_call,
)

URL = "https://example.com/very/long/path"


def make_agent(client, **kwargs):
    toolbox = ShortLinkToolbox(fakeredis.FakeRedis(decode_responses=True))
    agent = Agent(
        client=client,
        tools=TOOLS,
        execute_tool=make_tool_dispatcher(toolbox),
        **kwargs,
    )
    return agent, toolbox


def test_plain_reply_without_tool_call():
    response = make_response(make_message(content="我是助手，有什么可以帮你？"))
    client = FakeClient([response])
    agent, _ = make_agent(client)

    result = agent.chat([{"role": "user", "content": "你好"}])

    assert result == "我是助手，有什么可以帮你？"
    assert len(client.completions.calls) == 1


def test_tool_call_executes_and_returns_final_answer():
    first = make_response(
        make_message(
            tool_calls=[make_tool_call("create_short_link", {"url": URL})]
        )
    )
    second = make_response(make_message(content="已为您生成短链接。"))
    client = FakeClient([first, second])
    agent, toolbox = make_agent(client)

    result = agent.chat([{"role": "user", "content": "帮我缩短这个链接"}])

    assert result == "已为您生成短链接。"
    calls = client.completions.calls
    assert len(calls) == 2

    # 第二次调用时，模型应看到 tool 执行结果
    second_messages = calls[1]["messages"]
    tool_messages = [m for m in second_messages if m["role"] == "tool"]
    assert len(tool_messages) == 1
    assert "短链接生成成功" in tool_messages[0]["content"]
    assert "https://short.link/" in tool_messages[0]["content"]

    # 短码确实写入存储
    codes = toolbox.redis.keys("*")
    assert len(codes) == 1
    assert toolbox.redis.get(codes[0]) == URL


def test_chat_does_not_mutate_caller_history():
    first = make_response(
        make_message(
            tool_calls=[make_tool_call("get_original_url", {"short_code": "abc123"})]
        )
    )
    second = make_response(make_message(content="未找到该短码。"))
    client = FakeClient([first, second])
    agent, _ = make_agent(client)
    history = [{"role": "user", "content": "查一下 abc123"}]

    agent.chat(history)

    # 内部 assistant/tool 消息不应污染调用方维护的对话历史
    assert history == [{"role": "user", "content": "查一下 abc123"}]


def test_malformed_arguments_do_not_crash():
    tool_call = make_tool_call("create_short_link", {"url": URL})
    tool_call.function.arguments = "not-valid-json"
    first = make_response(make_message(tool_calls=[tool_call]))
    second = make_response(make_message(content="参数似乎有问题，请换个说法。"))
    client = FakeClient([first, second])
    agent, _ = make_agent(client)

    result = agent.chat([{"role": "user", "content": "缩短它"}])

    assert result == "参数似乎有问题，请换个说法。"
    calls = client.completions.calls
    assert len(calls) == 2
    tool_messages = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert len(tool_messages) == 1
    assert "参数错误" in tool_messages[0]["content"]


def test_multiple_tool_calls_are_paired_correctly():
    first = make_response(
        make_message(
            tool_calls=[
                make_tool_call("create_short_link", {"url": URL}, call_id="call_1"),
                make_tool_call("create_short_link", {"url": URL + "/2"}, call_id="call_2"),
            ]
        )
    )
    second = make_response(make_message(content="两个短链接都生成好了。"))
    client = FakeClient([first, second])
    agent, toolbox = make_agent(client)

    result = agent.chat([{"role": "user", "content": "缩短这两个链接"}])

    assert result == "两个短链接都生成好了。"
    second_messages = client.completions.calls[1]["messages"]
    # assistant 的工具调用消息只出现一次
    assistant_messages = [m for m in second_messages if m["role"] == "assistant" and "tool_calls" in m]
    assert len(assistant_messages) == 1
    assert len(assistant_messages[0]["tool_calls"]) == 2
    # 两条 tool 结果按 id 一一配对
    tool_messages = [m for m in second_messages if m["role"] == "tool"]
    assert {m["tool_call_id"] for m in tool_messages} == {"call_1", "call_2"}
    assert len(toolbox.redis.keys("*")) == 2


def test_unknown_tool_result_flows_back_to_model():
    first = make_response(
        make_message(tool_calls=[make_tool_call("mystery_tool", {})])
    )
    second = make_response(make_message(content="我不认识这个工具。"))
    client = FakeClient([first, second])
    agent, _ = make_agent(client)

    result = agent.chat([{"role": "user", "content": "调用一下 mystery"}])

    assert result == "我不认识这个工具。"
    tool_messages = [
        m for m in client.completions.calls[1]["messages"] if m["role"] == "tool"
    ]
    assert tool_messages[0]["content"] == "未知工具：mystery_tool"


def test_loop_continues_across_multiple_tool_rounds():
    """模型连续两轮请求工具时，要一直循环到它自己给出最终回复。"""
    first = make_response(
        make_message(
            tool_calls=[make_tool_call("create_short_link", {"url": URL}, call_id="call_1")]
        )
    )
    second = make_response(
        make_message(
            tool_calls=[
                make_tool_call("get_original_url", {"short_code": "abc123"}, call_id="call_2")
            ]
        )
    )
    third = make_response(make_message(content="链路结束，这是最终回复。"))
    client = FakeClient([first, second, third])
    agent, toolbox = make_agent(client)

    result = agent.chat([{"role": "user", "content": "先缩短再查回来"}])

    assert result == "链路结束，这是最终回复。"
    calls = client.completions.calls
    assert len(calls) == 3
    # 每一轮都要带 tools，模型才有机会决定是否继续调用
    assert all("tools" in c for c in calls)
    # 上下文是逐轮累积的：第 2 次调用只看到第 1 轮结果，第 3 次才看到两轮
    second_round_tools = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert {m["tool_call_id"] for m in second_round_tools} == {"call_1"}
    third_round_tools = [m for m in calls[2]["messages"] if m["role"] == "tool"]
    assert {m["tool_call_id"] for m in third_round_tools} == {"call_1", "call_2"}
    # 第一轮的工具副作用真实落库
    assert len(toolbox.redis.keys("*")) == 1


def test_loop_stops_at_max_rounds_and_forces_final_answer():
    """模型不收敛时要被轮数上限截停，且最后一次调用不再提供工具。"""
    first = make_response(
        make_message(
            tool_calls=[make_tool_call("create_short_link", {"url": URL}, call_id="call_1")]
        )
    )
    second = make_response(
        make_message(
            tool_calls=[
                make_tool_call("create_short_link", {"url": URL + "/2"}, call_id="call_2")
            ]
        )
    )
    third = make_response(make_message(content="达到上限后的收尾回复。"))
    client = FakeClient([first, second, third])
    agent, _ = make_agent(client, max_tool_rounds=2)

    result = agent.chat([{"role": "user", "content": "不停地缩短"}])

    assert result == "达到上限后的收尾回复。"
    calls = client.completions.calls
    assert len(calls) == 3              # 2 轮执行 + 1 次强制收尾
    assert "tools" in calls[0] and "tools" in calls[1]
    assert "tools" not in calls[2]      # 收尾调用不再给模型工具，逼它用自然语言回答


def test_tool_calls_in_one_round_run_concurrently():
    """同一轮的多个工具调用互相独立，应当并发执行而不是排队。"""
    first = make_response(
        make_message(
            tool_calls=[
                make_tool_call("create_short_link", {"url": f"{URL}/{i}"}, call_id=f"call_{i}")
                for i in range(3)
            ]
        )
    )
    second = make_response(make_message(content="三个都好了。"))
    client = FakeClient([first, second])

    def slow_execute(name, arguments):
        time.sleep(0.3)          # 模拟一次 Redis 网络往返
        return "ok"

    agent = Agent(client=client, tools=TOOLS, execute_tool=slow_execute)

    started = time.perf_counter()
    agent.chat([{"role": "user", "content": "缩短这三个链接"}])
    elapsed = time.perf_counter() - started

    # 串行需要约 0.9 秒，并发约 0.3 秒；留足余量避免 CI 上偶发波动
    assert elapsed < 0.6
    tool_messages = [m for m in client.completions.calls[1]["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_messages] == ["call_0", "call_1", "call_2"]
