"""工具层：Tool Schema 定义与 Redis 驱动的短链接业务操作。

与 Agent 决策层解耦：模型只感知 JSON Schema，真实副作用集中在
本模块，便于独立测试与替换存储实现。
"""

import secrets
import string
from typing import Callable, Optional

SHORT_CODE_LENGTH = 6
CODE_ALPHABET = string.ascii_letters + string.digits
MAX_COLLISION_RETRIES = 5
SCAN_COUNT = 100
MAX_SIMILAR_RESULTS = 5
BASE_SHORT_URL = "https://short.link"


def generate_short_code(length: int = SHORT_CODE_LENGTH) -> str:
    """使用 secrets（密码学安全随机源）生成短码。"""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_short_link",
            "description": "将长网址转换为短链接。当用户需要缩短网址、生成短链接时调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "需要缩短的长网址，必须是完整的URL格式",
                    },
                    "custom_code": {
                        "type": "string",
                        "description": "自定义短码，可选。用户指定的话用这个，否则系统自动生成",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_original_url",
            "description": "根据短码查询原始长网址。当用户询问某个短链接对应什么网址时调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "short_code": {
                        "type": "string",
                        "description": "短码，例如 aB3xK9",
                    }
                },
                "required": ["short_code"],
            },
        },
    },
]


class ShortLinkToolbox:
    """短链接业务：生成、原子写入、精确/模糊查询。

    redis_client 采用鸭子类型（实现 setnx/get/scan 即可），生产环境
    传入 redis.Redis，测试中可注入 fakeredis 或内存替身。
    """

    def __init__(
        self,
        redis_client,
        code_length: int = SHORT_CODE_LENGTH,
        max_retries: int = MAX_COLLISION_RETRIES,
    ) -> None:
        self.redis = redis_client
        self.code_length = code_length
        self.max_retries = max_retries

    def create_short_link(self, url: str, custom_code: Optional[str] = None) -> str:
        """创建短链接。

        自定义短码冲突时直接提示换码；自动生成时使用 SETNX 原子写入，
        冲突则重试，最多 max_retries 次。
        """
        if custom_code:
            if self._try_store(custom_code, url):
                return self._ok_message(custom_code)
            return f"自定义短码 '{custom_code}' 已被占用，请更换。"

        for _ in range(self.max_retries):
            code = generate_short_code(self.code_length)
            if self._try_store(code, url):
                return self._ok_message(code)
        return "系统繁忙，请稍后重试。"

    def get_original_url(self, short_code: str) -> str:
        """精确查询；未命中时用 SCAN 给出相似短码建议。"""
        original = self.redis.get(short_code)
        if original:
            return f"查询成功！短码 {short_code} 对应的原始网址是：{original}"

        similar = self._find_similar(short_code)
        if similar:
            joined = ", ".join(similar)
            return (
                f"未找到短码 '{short_code}'，但找到相似的短码：{joined}。"
                "请确认后重试。"
            )
        return f"未找到短码 '{short_code}'，请确认短码是否正确。"

    def _try_store(self, code: str, url: str) -> bool:
        return bool(self.redis.setnx(code, url))

    @staticmethod
    def _ok_message(code: str) -> str:
        return f"短链接生成成功！短码：{code}，短网址：{BASE_SHORT_URL}/{code}"

    def _find_similar(self, short_code: str) -> list:
        """用 SCAN 游标迭代模糊匹配，避免阻塞式 KEYS *。"""
        similar = []
        cursor = 0
        while True:
            cursor, keys = self.redis.scan(
                cursor=cursor, match=f"*{short_code}*", count=SCAN_COUNT
            )
            similar.extend(keys)
            if cursor == 0 or len(similar) >= MAX_SIMILAR_RESULTS:
                break
        return similar[:MAX_SIMILAR_RESULTS]


def make_tool_dispatcher(toolbox: ShortLinkToolbox) -> Callable[[str, dict], str]:
    """把工具名映射到具体方法；未知工具与参数错误以消息形式回传模型。"""
    handlers = {
        "create_short_link": toolbox.create_short_link,
        "get_original_url": toolbox.get_original_url,
    }

    def dispatch(name: str, arguments: dict) -> str:
        handler = handlers.get(name)
        if handler is None:
            return f"未知工具：{name}"
        try:
            return handler(**arguments)
        except TypeError:
            return f"工具 {name} 参数错误：{arguments}，请检查后重试。"

    return dispatch
