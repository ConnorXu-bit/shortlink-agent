import json
import hashlib
import secrets
import string
import os
from openai import OpenAI
import redis
from dotenv import load_dotenv

load_dotenv()  # 加载 .env 文件

# ================= 1. 初始化 DeepSeek 客户端 =================
# 建议使用环境变量，安全且避免编码错误
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    raise ValueError("请设置环境变量 DEEPSEEK_API_KEY")

    # 如果没设置环境变量，可以临时硬编码（仅本地测试），但千万不要提交到 GitHub
    #DEEPSEEK_API_KEY = "在这里填你的DeepSeek API Key"  # 或者保留环境变量方式

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
)

# ================= 2. 连接 Redis =================
redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

try:
    redis_client.ping()
    print("✅ Redis 连接成功！数据将持久化存储。")
except redis.ConnectionError:
    print("❌ 连接Redis失败，请检查Redis服务是否启动。")
    exit(1)

# ================= 3. 定义工具描述 (Tools) =================
tools = [
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
                        "description": "短码，例如 fdb2de",
                    }
                },
                "required": ["short_code"],
            },
        },
    }
]

# ================= 4. 核心 Agent 函数（支持传入历史消息） =================
def chat_with_agent(messages: list) -> str:
    """
    接收一个消息列表（包含历史对话），调用 DeepSeek 并处理工具调用。
    """
    # 第一次调用：让模型判断要不要调用工具
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,  # 直接使用传入的历史消息
        tools=tools,
    )
    
    message = response.choices[0].message
    
    # 如果模型想调用工具
    if message.tool_calls:
        for tool_call in message.tool_calls:
            args = json.loads(tool_call.function.arguments)
            print(f"🤖 模型决定调用: {tool_call.function.name}, 参数: {args}")
            
            # ---------- 生成短链接 ----------
            if tool_call.function.name == "create_short_link":
                if args.get("custom_code"):
                    short_code = args["custom_code"]
                    if redis_client.setnx(short_code, args["url"]):
                        tool_result = f"短链接生成成功！短码：{short_code}，短网址：https://short.link/{short_code}"
                    else:
                        tool_result = f"自定义短码 '{short_code}' 已被占用，请更换。"
                else:
                    generated = False
                    alphabet = string.ascii_letters + string.digits
                    for _ in range(5):
                        short_code = ''.join(secrets.choice(alphabet) for _ in range(6))
                        if redis_client.setnx(short_code, args["url"]):
                            tool_result = f"短链接生成成功！短码：{short_code}，短网址：https://short.link/{short_code}"
                            generated = True
                            break
                    if not generated:
                        tool_result = "系统繁忙，请稍后重试。"
            
            # ---------- 查询短链接 ----------
            elif tool_call.function.name == "get_original_url":
                short_code = args["short_code"]
                original_url = redis_client.get(short_code)
                if original_url:
                    tool_result = f"查询成功！短码 {short_code} 对应的原始网址是：{original_url}"
                else:
                    # 使用 SCAN 安全遍历（替代危险 KEYS *）
                    similar = []
                    cursor = '0'
                    while cursor != 0:
                        cursor, keys = redis_client.scan(cursor=cursor, match=f"*{short_code}*", count=100)
                        similar.extend(keys)
                        if len(similar) >= 5:
                            break
                    if similar:
                        tool_result = f"未找到短码 '{short_code}'，但找到相似的短码：{', '.join(similar[:5])}。请确认后重试。"
                    else:
                        tool_result = f"未找到短码 '{short_code}'，请确认短码是否正确。"
            
            else:
                tool_result = "未知工具"

            # 把模型的工具调用请求（message）和工具执行结果（tool_result）都追加到历史中
            messages.append(message)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_result,
            })
        
        # 第二次调用：让模型根据工具结果生成最终的自然语言回复
        final_response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
        )
        return final_response.choices[0].message.content
    
    # 如果模型不需要调用工具，直接返回
    return message.content

# ================= 5. 循环对话入口（含上下文记忆管理） =================
if __name__ == "__main__":
    print("\n🤖 短链接Agent已启动！输入 'exit' 或 'quit' 退出对话。")
    print("💡 提示：我现在能记住上下文了，你可以说'查一下刚才那个'！\n")
    
    # 核心改动：在循环外部维护一个全局对话历史
    conversation_history = []
    MAX_HISTORY_TURNS = 10  # 保留最近 10 轮对话（每轮包括用户和助手各一条）
    
    while True:
        user_input = input("👤 你: ")
        if user_input.lower() in ["exit", "quit", "q"]:
            print("👋 再见！")
            break
        
        if not user_input.strip():
            continue
        
        # 1. 将用户消息加入历史
        conversation_history.append({"role": "user", "content": user_input})
        
        # 2. 调用 Agent（传入完整历史）
        result = chat_with_agent(conversation_history)
        
        # 3. 将助手回复加入历史
        conversation_history.append({"role": "assistant", "content": result})
        
        # 4. 滑动窗口：如果历史太长，只保留最近的 N 轮对话（防止 Token 溢出）
        # 注：一轮对话 = 1 条 user + 1 条 assistant = 2 条消息
        # MAX_HISTORY_TURNS 轮 = MAX_HISTORY_TURNS * 2 条消息
        max_messages = MAX_HISTORY_TURNS * 2
        if len(conversation_history) > max_messages:
            # 注意：工具调用过程中可能插入 tool 角色消息，这里简单裁剪尾部保留最近的 N 条
            # 更严谨的做法是保留最近 N 条 user/assistant 对，但为了演示简洁，我们直接保留最后 max_messages 条
            conversation_history = conversation_history[-max_messages:]
        
        print(f"🤖 Agent: {result}\n")
