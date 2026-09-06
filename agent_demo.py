"""短链接 Agent 命令行入口：装配真实模型客户端/存储并启动多轮对话。"""

import os

import redis
from dotenv import load_dotenv
from openai import OpenAI

from agent import Agent, trim_history
from tools import TOOLS, ShortLinkToolbox, make_tool_dispatcher

load_dotenv()


def build_agent() -> Agent:
    """根据环境变量构建带真实依赖的 Agent（Redis + DeepSeek API）。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("请先设置环境变量 DEEPSEEK_API_KEY（参考 .env.example）。")

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
    try:
        redis_client.ping()
    except redis.ConnectionError:
        raise SystemExit("连接 Redis 失败，请确认本机 Redis 已启动。")

    toolbox = ShortLinkToolbox(redis_client)
    return Agent(
        client=client,
        tools=TOOLS,
        execute_tool=make_tool_dispatcher(toolbox),
    )


def main() -> None:
    agent = build_agent()
    print("\n🤖 短链接Agent已启动！输入 'exit' 或 'quit' 退出对话。")
    print("💡 提示：我现在能记住上下文了，你可以说'查一下刚才那个'！\n")

    history: list = []
    while True:
        user_input = input("👤 你: ")
        if user_input.strip().lower() in {"exit", "quit", "q"}:
            print("👋 再见！")
            return
        if not user_input.strip():
            continue

        history.append({"role": "user", "content": user_input})
        result = agent.chat(history)
        history.append({"role": "assistant", "content": result})
        history = trim_history(history)

        print(f"🤖 Agent: {result}\n")


if __name__ == "__main__":
    main()
