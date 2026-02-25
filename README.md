# 本地代码仓库问答 Agent

基于 Python 的本地代码仓库问答 Agent，支持多模型厂商（Gemini、Kimi）。通过 Function Calling/Tool Calling 机制，自动调用工具函数访问**当前工作目录**下的代码仓库，回答用户的自然语言问题。当前版本采用「**Agent 独立服务 + CLI/TUI 远程控制端**」架构，项目结构为后续**本地 RAG** 与**本地知识库**扩展预留模块。

## 功能

- 自然语言提问（支持中文）
- 自动搜索代码文件内容（`search_files`）
- 读取指定文件片段（`read_file`）
- 列出目录结构（`list_dir`）
- 支持 Gemini 与 Kimi（OpenAI 兼容）自由切换
- 基于 Function Calling/Tool Calling 的 Agent 循环
- 单轮最多 30 次有效工具调用（含重复调用保护）
- 连续重复的同参工具调用会自动复用上次结果
- `read_file` 默认读取 120 行，减少碎片化读取
- 多轮对话支持
- `agentd` 常驻服务（会话可独立于 TUI 存活）
- 远程 CLI 与 TUI（观察、遥控同一会话）

## 环境要求

- Python 3.10+
- Gemini API Key（Google AI Studio）或 Kimi API Key（Moonshot）

## 安装

在**本仓库根目录**（即包含 `repo_agent/` 包和 `pyproject.toml` 的目录）下执行：

```bash
pip install -r requirements.txt
```

或以可编辑方式安装，便于开发与在任意目录运行：

```bash
pip install -e .
```

如需使用类 opencode 的 TUI 交互界面，请安装可选依赖：

```bash
pip install -e .[tui]
```

## 配置模型与 API Key

推荐方式：在项目根目录创建 `.env`（不要提交到仓库）。
可以先复制模板：

```bash
# Linux / macOS
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

先设置模型厂商：

```bash
# Linux / macOS（gemini / kimi 二选一）
export LLM_PROVIDER=gemini

# Windows PowerShell
$env:LLM_PROVIDER="gemini"
```

### Gemini

**方式一：环境变量**

```bash
# Linux / macOS
export GEMINI_API_KEY=your_api_key_here

# Windows PowerShell
$env:GEMINI_API_KEY="your_api_key_here"

# Windows CMD
set GEMINI_API_KEY=your_api_key_here
```

**方式二：`.env` 文件**

在以下任一位置创建 `.env` 文件并写入 `GEMINI_API_KEY=your_api_key_here`：

- 运行 `python -m repo_agent` 时的**当前工作目录**（即被分析的仓库根目录）
- 本项目的**仓库根目录**（即 `repo_agent` 文件夹所在目录）

### Kimi（Moonshot）

```bash
# Linux / macOS
export LLM_PROVIDER=kimi
export MOONSHOT_API_KEY=your_api_key_here
export KIMI_MODEL_ID=kimi-k2-turbo-preview

# Windows PowerShell
$env:LLM_PROVIDER="kimi"
$env:MOONSHOT_API_KEY="your_api_key_here"
$env:KIMI_MODEL_ID="kimi-k2-turbo-preview"
```

可选：如果需要自定义 OpenAI 兼容地址，可设置 `KIMI_BASE_URL`（默认 `https://api.moonshot.cn/v1`）。

`.env` 示例：

```env
LLM_PROVIDER=kimi
MOONSHOT_API_KEY=your_kimi_api_key_here
KIMI_MODEL_ID=kimi-k2-turbo-preview
KIMI_BASE_URL=https://api.moonshot.cn/v1

# 可选：切回 Gemini 时使用
GEMINI_API_KEY=your_gemini_api_key_here
```

## 使用方法

Agent 只会访问**服务进程当前工作目录**下的文件，因此请先进入要分析的代码仓库目录再启动 `--mode service`。

1. 启动常驻服务（独立进程）

```bash
python -m repo_agent --mode service
```

默认监听 `http://127.0.0.1:8765`，可通过环境变量或参数调整：

- 环境变量：`AGENTD_HOST`、`AGENTD_PORT`、`AGENTD_TOKEN`
- 参数：`--host`、`--port`、`--token`

2. 启动 CLI（远程模式，默认模式）

```bash
python -m repo_agent
# 等同于
python -m repo_agent --mode cli
```

3. 启动 TUI（远程模式，双栏：聊天区 + 工具日志区）

```bash
python -m repo_agent --mode tui
# 或兼容旧参数
python -m repo_agent --tui
```

如需连接非默认地址，可追加：

```bash
python -m repo_agent --mode cli --endpoint http://127.0.0.1:9000
python -m repo_agent --mode tui --endpoint http://127.0.0.1:9000
```

4. 可选：保留旧单进程本地模式

```bash
python -m repo_agent --mode local
```

## 交互示例

```
You: 这个项目的目录结构是什么？
  [工具调用 #1] list_dir({"path": "."})
  [工具结果] ./
  ├── repo_agent/
  ├── pyproject.toml
  ├── README.md
  ...

Agent: 这个项目包含以下文件：...

You: 找一下所有包含 "def " 的文件
  [工具调用 #1] search_files({"query": "def "})
  [工具结果] 找到 15 条匹配...

Agent: 项目中定义了以下函数：...
```

## 内置命令

| 命令 | 说明 |
|------|------|
| `/clear`、`/reset` | 清除对话历史 |
| `/status` | 查看会话状态（busy/pending 等） |
| `/cancel` | 取消等待中的任务（不强制中断当前执行） |
| `/quit`、`/exit`、`/q` | 退出程序 |
| `/help` | 显示帮助 |
| `Ctrl+C` | 退出程序 |

TUI 额外快捷键：

| 快捷键 | 说明 |
|------|------|
| `Ctrl+L` | 清空会话与日志 |
| `Ctrl+K` | 取消等待中的任务 |

## 项目结构

```
repo_agent/
├── repo_agent/              # 主包
│   ├── __init__.py
│   ├── __main__.py          # 入口：service / cli / tui / local
│   ├── config/              # 配置
│   │   ├── __init__.py
│   │   └── settings.py      # API Key + agentd 地址/token
│   ├── agent/               # Agent 核心
│   │   ├── __init__.py
│   │   ├── client.py        # 多厂商客户端（Gemini/Kimi）
│   │   ├── prompts.py       # 系统提示与常量
│   │   └── loop.py          # 主循环与工具调度
│   ├── daemon/              # 常驻服务端
│   │   ├── __init__.py
│   │   ├── app.py           # HTTP API
│   │   ├── models.py        # 事件/任务模型
│   │   └── session_manager.py
│   ├── remote/              # 远程客户端 SDK
│   │   ├── __init__.py
│   │   └── client.py
│   ├── cli/                 # 远程 CLI
│   │   ├── __init__.py
│   │   └── remote.py
│   ├── tools/               # 工具
│   │   ├── __init__.py
│   │   ├── registry.py      # 工具注册表（声明 + 函数）
│   │   └── repo.py          # 仓库工具：search_files, read_file, list_dir
│   ├── ui/                  # 远程 TUI 交互层
│   │   ├── __init__.py
│   │   └── tui.py
│   ├── rag/                 # RAG 预留（本地检索增强）
│   │   ├── __init__.py
│   │   ├── embeddings.py    # 本地 Embedding
│   │   ├── store.py         # 向量存储
│   │   └── retriever.py     # 检索器
│   └── kb/                  # 知识库预留
│       ├── __init__.py
│       ├── loader.py        # 文档加载
│       └── index.py         # 索引构建
├── requirements.txt
├── pyproject.toml           # 包配置，支持 pip install -e .
├── .gitignore
└── README.md
```

## 扩展说明

- **新增工具**：在 `repo_agent/tools/` 下实现函数，并在 `registry.py` 中注册名称与函数声明（会自动适配 Gemini/Kimi）。
- **本地 RAG**：在 `rag/` 中实现 `embeddings`、`store`、`retriever`，可新增工具（如 `search_knowledge_base`）或作为上下文注入。
- **本地知识库**：在 `kb/` 中实现 `loader` 与 `index`，对文档分块、向量化后写入 `rag.store`。

## 安全说明

- 所有文件操作均为只读
- 路径限制在当前工作目录内，禁止路径逃逸
- 不执行任何 shell 命令
- 不写入任何文件
- `agentd` 默认本机监听（`127.0.0.1`）
- 如需额外保护，可配置 `AGENTD_TOKEN` 启用请求鉴权
- `.env` 已在 `.gitignore` 中，默认不会被提交
- 提交前请确认仓库中没有明文密钥（如 `sk-`、`AIza`）
