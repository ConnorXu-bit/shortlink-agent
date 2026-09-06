"""工具层测试：生成、原子写入、冲突重试与查询建议。"""

from tools import (
    BASE_SHORT_URL,
    SHORT_CODE_LENGTH,
    ShortLinkToolbox,
    make_tool_dispatcher,
)

URL = "https://example.com/very/long/path"
OTHER_URL = "https://other.example.com/page"


def test_auto_generate_stores_code(toolbox):
    message = toolbox.create_short_link(URL)

    assert f"短网址：{BASE_SHORT_URL}/" in message
    code = message.rsplit("/", 1)[-1]
    assert len(code) == SHORT_CODE_LENGTH
    assert toolbox.redis.get(code) == URL


def test_custom_code_success(toolbox):
    message = toolbox.create_short_link(URL, custom_code="abc123")

    assert "abc123" in message
    assert toolbox.redis.get("abc123") == URL


def test_custom_code_conflict_keeps_original_data(toolbox):
    toolbox.redis.set("abc123", OTHER_URL)

    message = toolbox.create_short_link(URL, custom_code="abc123")

    assert "已被占用" in message
    assert toolbox.redis.get("abc123") == OTHER_URL


def test_collision_retry_then_success(toolbox, monkeypatch):
    toolbox.redis.set("AAAAAA", OTHER_URL)
    codes = iter(["AAAAAA", "BBBBBB"])
    monkeypatch.setattr("tools.generate_short_code", lambda length: next(codes))

    message = toolbox.create_short_link(URL)

    assert "BBBBBB" in message
    assert toolbox.redis.get("BBBBBB") == URL
    assert toolbox.redis.get("AAAAAA") == OTHER_URL


def test_exhaust_retries_reports_busy(toolbox, monkeypatch):
    toolbox.redis.set("AAAAAA", OTHER_URL)
    monkeypatch.setattr("tools.generate_short_code", lambda length: "AAAAAA")

    message = toolbox.create_short_link(URL)

    assert message == "系统繁忙，请稍后重试。"


def test_get_exact_match(toolbox):
    toolbox.redis.set("abc123", URL)

    message = toolbox.get_original_url("abc123")

    assert f"对应的原始网址是：{URL}" in message


def test_get_miss_with_similar_suggestions(toolbox):
    toolbox.redis.set("ab12345", URL)
    toolbox.redis.set("ab12346", OTHER_URL)

    message = toolbox.get_original_url("ab1234")

    assert "未找到短码 'ab1234'" in message
    assert "ab12345" in message
    assert "ab12346" in message


def test_get_miss_without_similar(toolbox):
    message = toolbox.get_original_url("nope00")

    assert message == "未找到短码 'nope00'，请确认短码是否正确。"


def test_dispatcher_unknown_tool(toolbox):
    result = make_tool_dispatcher(toolbox)("mystery_tool", {})

    assert result == "未知工具：mystery_tool"


def test_dispatcher_bad_arguments_reports_error(toolbox):
    result = make_tool_dispatcher(toolbox)("create_short_link", {})

    assert "参数错误" in result
