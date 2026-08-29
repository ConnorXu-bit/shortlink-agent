# 🤖 智能短链接 Agent

基于 **ReAct 模式** 和 **DeepSeek Function Calling** 构建的 AI 短链接助手。用户只需用自然语言对话，Agent 就能自主决策、调用工具，完成短链接的**生成**与**查询**，并支持**多轮上下文记忆**。

## ✨ 核心特性

- 🧠 **自主决策**：基于 ReAct（推理-行动）模式，Agent 能自动判断用户意图（缩短 / 查询），并调用对应工具。
- 🔧 **工具封装**：将业务逻辑（`create_short_link` / `get_original_url`）按照 OpenAI Function Calling 规范封装为标准 Tool。
- 💾 **持久化记忆**：集成 Redis，短链数据在服务重启后不丢失；对话历史采用**滑动窗口**机制，兼顾记忆长度与 Token 成本。
- 🔒 **生产级安全操作**：
  - 短码生成使用 **`secrets`** 密码级随机源，防止枚举攻击。
  - 写入 Redis 使用 **`SETNX`** 原子命令，避免高并发下的数据覆盖。
  - 模糊查询使用 **`SCAN`** 游标迭代，替代危险的 `KEYS *`，杜绝阻塞风险。
- 🗣️ **多轮对话**：支持上下文记忆，你可以说“查一下刚才那个”，Agent 能准确理解指代关系。

## 🛠️ 技术栈

| 组件 | 技术选型 |
|------|----------|
| Agent 框架 | OpenAI SDK (兼容 DeepSeek API) |
| 大模型 | DeepSeek Chat |
| 缓存/存储 | Redis |
| 随机生成 | Python `secrets` + `string` |
| 编程语言 | Python 3.10+ |

## 🚀 快速开始

### 前置条件

- Python 3.10+
- Redis 服务（本地或远程）
- DeepSeek API Key（[申请地址](https://platform.deepseek.com/)）

### 安装与运行

1. **克隆项目**
   ```bash
   git clone https://github.com/你的用户名/shortlink-agent.git
   cd shortlink-agent