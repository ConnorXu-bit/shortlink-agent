# 🤖 智能短链接 Agent

> 基于 **ReAct 推理-行动范式** 和 **DeepSeek Function Calling** 构建的智能对话式短链接助手。用户通过自然语言即可完成链接缩短、查询与管理，Agent 自主决策并调用后端工具执行真实业务操作。

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![DeepSeek](https://img.shields.io/badge/DeepSeek-API-4A6CF7.svg)](https://platform.deepseek.com/)
[![Redis](https://img.shields.io/badge/Redis-Persistent-DC382D.svg)](https://redis.io/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🧠 **ReAct 自主决策** | 基于推理-行动-观察循环，Agent 自动识别用户意图（缩短/查询），动态选择并调用对应工具 |
| 🔧 **标准化工具封装** | 业务逻辑严格遵循 OpenAI Function Calling 规范封装为 Tool，实现决策层与执行层解耦 |
| 💾 **持久化记忆系统** | Redis 存储短链数据，服务重启不丢失；对话历史采用滑动窗口机制，兼顾记忆长度与 Token 成本 |
| 🔒 **生产级安全设计** | 使用 `secrets` 密码级随机源生成短码；`SETNX` 原子命令写入，杜绝高并发覆盖风险 |
| 🔍 **安全模糊查询** | 使用 Redis `SCAN` 游标迭代替代危险的 `KEYS *`，即使在百万级数据下也能安全遍历 |
| 🗣️ **多轮上下文对话** | 支持跨轮次的指代理解，用户说“查一下刚才那个”，Agent 能准确解析并响应 |
| 🧪 **可测试架构** | 存储与 LLM 客户端均可注入：pytest + fakeredis + mock 模型响应，全链路测试无需真实 API 与 Redis |

---

## 🛠️ 技术栈

| 层级 | 技术选型 |
|------|----------|
| Agent 框架 | OpenAI SDK（兼容 DeepSeek API） |
| 大模型 | DeepSeek Chat |
| 存储层 | Redis（内存数据库） |
| 随机生成 | Python `secrets` + `string` |
| 环境管理 | `python-dotenv` |
| 编程语言 | Python 3.10+ |
| 测试 | pytest + fakeredis（mock LLM，不产生真实 API 调用） |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      用户（自然语言交互）                      │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Agent 决策层                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  1. 意图识别：用户输入 → 模型推理                     │   │
│  │  2. 工具选择：判断是否需要调用工具 & 选择具体工具      │   │
│  │  3. 参数提取：从自然语言中提取结构化参数               │   │
│  │  4. 结果合成：将工具执行结果转化为自然语言回复         │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    工具执行层                               │
│  ┌─────────────────┐          ┌─────────────────────────┐  │
│  │ create_short_link │          │ get_original_url         │  │
│  │ • secrets 随机生成 │          │ • Redis GET 精确查询     │  │
│  │ • SETNX 原子写入   │          │ • SCAN 安全模糊匹配      │  │
│  └─────────────────┘          └─────────────────────────┘  │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      存储层                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Redis（持久化存储）                      │   │
│  │   Key: 短码（如 aB3xK9）                            │   │
│  │   Value: 原始长网址                                  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 前置条件

- Python 3.10+
- Redis 服务（本地或远程）
- DeepSeek API Key（[申请地址](https://platform.deepseek.com/)）

### 安装步骤

**1. 克隆项目**
```bash
git clone https://github.com/ConnorXu-bit/shortlink-agent.git
cd shortlink-agent
```

**2. 安装依赖**
```bash
pip install -r requirements.txt
```

**3. 配置环境变量**
```bash
cp .env.example .env
# 编辑 .env 文件，填入你的 DEEPSEEK_API_KEY
```

**4. 启动 Redis**
```bash
# macOS
brew services start redis
# 或
redis-server

# Linux
sudo systemctl start redis

# Windows（在 Redis 安装目录执行）
redis-server
```

**5. 运行 Agent**
```bash
python agent_demo.py
```

---

## 💬 交互示例

```text
🤖 短链接 Agent 已启动！输入 'exit' 或 'quit' 退出对话。
💡 提示：我现在能记住上下文了，你可以说'查一下刚才那个'！

👤 你: 帮我缩短 https://www.example.com/very/long/path
🤖 模型决定调用: create_short_link, 参数: {'url': 'https://www.example.com/very/long/path'}
🤖 Agent: 已为您生成短链接：https://short.link/aB3xK9

👤 你: 查一下刚才那个
🤖 模型决定调用: get_original_url, 参数: {'short_code': 'aB3xK9'}
🤖 Agent: 查询成功！短码 aB3xK9 对应的原始网址是：https://www.example.com/very/long/path

👤 你: exit
👋 再见！
```

---

## 📁 项目结构

```
shortlink-agent/
├── agent_demo.py          # CLI 入口：装配真实依赖并启动多轮对话
├── agent.py               # Agent 决策层：Function Calling 循环 + 滑动窗口
├── tools.py               # 工具层：Tool Schema + Redis 短链接业务
├── tests/                 # pytest 测试（fakeredis + mock LLM）
├── requirements.txt       # 运行时依赖清单
├── requirements-dev.txt   # 测试依赖清单
├── pytest.ini             # pytest 配置
├── .github/workflows/ci.yml  # GitHub Actions 自动测试
├── .env.example           # 环境变量模板
├── .gitignore             # Git 忽略规则
└── README.md              # 项目文档
```

---

## 🔬 关键技术决策与深度解析

### 1. 为什么使用 `SETNX` 而非 `EXISTS` + `SET`？

在 `create_short_link` 工具中，短码写入 Redis 的操作使用了 `SETNX`（SET if Not eXists）原子命令。

```python
# ✅ 生产级方案：原子操作
if redis_client.setnx(short_code, url):
    # 写入成功
else:
    # 短码已被占用
```

**对比传统方案**（`EXISTS` + `SET`，分两步）：
```python
# ❌ 存在并发隐患
if not redis_client.exists(short_code):   # 步骤1：检查
    redis_client.set(short_code, url)     # 步骤2：写入
```

在步骤1和步骤2之间，若另一个并发请求生成相同短码并抢先写入，本请求会**覆盖**掉已有数据，造成数据污染。

**`SETNX` 的优势**：检查与写入合并为一个原子操作，在高并发场景下天然保证数据一致性，这是分布式系统设计中的基本素养。

---

### 2. 为什么用 `SCAN` 替代 `KEYS *`？

在 `get_original_url` 工具中，当精确查询失败时，需要提供相似的短码推荐。此处采用了 `SCAN` 游标迭代：

```python
cursor = '0'
while cursor != 0:
    cursor, keys = redis_client.scan(cursor=cursor, match=f"*{short_code}*", count=100)
    similar.extend(keys)
    if len(similar) >= 5:
        break
```

**`KEYS *` 的问题**：
- 执行 `KEYS *` 会**阻塞** Redis 主线程，直到扫描完所有 key。
- 在百万级数据下，可能阻塞数秒，导致**所有其他请求超时**，引发“慢查询雪崩”。

**`SCAN` 的优势**：
- 分批返回，每次仅阻塞毫秒级时间。
- 非阻塞遍历，不影响 Redis 处理其他正常请求。
- 配合 `count` 参数控制单次遍历量，找到 5 个候选后立即 `break`，避免无效遍历。

---

### 3. 为什么使用 `secrets` 而非 `random` 生成短码？

```python
import secrets
import string

alphabet = string.ascii_letters + string.digits  # 62个字符
short_code = ''.join(secrets.choice(alphabet) for _ in range(6))  # 6位，空间 62^6 ≈ 568亿
```

**`random` 的问题**：`random` 模块生成的是**伪随机数**，其种子可被预测，存在被暴力枚举的风险。

**`secrets` 的优势**：Python 标准库中的 `secrets` 模块专为**密码学安全**场景设计，生成的随机数不可预测，能有效防止攻击者通过遍历猜测有效短码。

---

### 4. 滑动窗口内存管理

为避免长对话超出模型 Token 上限，代码实现了滑动窗口机制：

```python
# agent.py：按“轮”裁剪，每轮 = 1 条 user + 1 条 assistant
history = trim_history(history)   # 默认保留最近 10 轮（20 条消息）
```

保留最近 10 轮对话，既能维持上下文的连续性，又能有效控制 API 调用成本。

---

## 🧪 运行测试

项目内置自动化测试，无需真实 Redis 与 DeepSeek API：

- `tests/test_tools.py`：短链接生成、SETNX 原子写入、冲突重试、SCAN 模糊查询建议
- `tests/test_agent.py`：mock 模型返回的 `tool_calls`，验证“决策 → 工具执行 → 回复”链路与消息配对
- `tests/test_memory.py`：滑动窗口对长对话的裁剪行为

```bash
pip install -r requirements-dev.txt
pytest -v
```

CI（`.github/workflows/ci.yml`）会在 push / PR 时于 Python 3.10 / 3.12 / 3.14 上自动运行上述测试。

---

## 🔮 未来迭代方向

- [ ] **RAG 知识增强**：接入向量数据库（如 Chroma/Milvus），支持用户上传文档并进行语义检索
- [ ] **批量处理 Skill**：自动提取文本中所有 URL 并批量缩短，提升效率
- [ ] **双层存储架构**：引入 PostgreSQL（SQLAlchemy）做持久化主库，Redis 做缓存层
- [ ] **微服务拆分**：将短链接服务独立为 FastAPI 微服务，Agent 通过 HTTP/gRPC 调用，实现决策层与执行层物理隔离
- [ ] **Web 界面**：基于 Gradio 或 Streamlit 构建对话 UI，替代命令行交互

---

## 📄 License

MIT License

---

## 🙋 关于作者

**Connor Xu** | 前数学教师 · AI 应用开发者

- GitHub: [ConnorXu-bit](https://github.com/ConnorXu-bit)

> 从数学课堂到 AI 工程，我始终相信：**清晰的逻辑是解决问题的最好工具。** 数学训练了我严谨的推理能力，而 AI 让我有能力将这些推理转化为可用的系统。

---

## ⭐ 如果这个项目对你有帮助

欢迎 Star ⭐ 和 Fork，你的支持是我持续迭代的动力！
