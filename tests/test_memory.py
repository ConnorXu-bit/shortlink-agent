"""对话记忆测试：滑动窗口裁剪行为。"""

from agent import trim_history


def make_messages(count):
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": str(i)}
        for i in range(count)
    ]


def test_short_history_is_unchanged():
    messages = make_messages(6)
    assert trim_history(messages) == messages


def test_long_history_keeps_last_rounds():
    messages = make_messages(30)
    trimmed = trim_history(messages, max_turns=10)
    assert trimmed == messages[-20:]


def test_window_keeps_complete_user_assistant_pairs():
    messages = make_messages(26)
    trimmed = trim_history(messages, max_turns=10)
    assert len(trimmed) == 20
    assert trimmed[0]["role"] == "user"
    assert trimmed[-1]["role"] == "assistant"
