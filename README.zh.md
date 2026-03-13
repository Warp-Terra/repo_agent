# 本地代码仓库问答 Agent

[English](./README.en.md) | [中文](./README.zh.md) | [首页](./README.md)

基于 Python 的本地代码仓库问答 Agent，使用 Kimi（Moonshot）付费 API（当前版本 **0.3.0**）。通过 Function Calling/Tool Calling 机制，自动调用工具函数访问**当前工作目录**下的代码仓库，回答用户的自然语言问题；采用「**自动托管 Agent 子进程 + TUI 交互端**」架构，项目结构为后续**本地 RAG** 与**本地知识库**扩展预留模块。

## 功能

- 自然语言提问（支持中文）
- 自动搜索代码文件内容（`search_files`）
- 读取指定文件片段（`read_file`）
- 列出目录结构（`list_dir`）
- **语义检索知识库**（`search_knowledge_base`，需先安装可选依赖并执行 `build-kb`）
- 使用 Kimi（OpenAI 兼容）API
- 基于 Function Calling/Tool Calling 的 Agent 循环
- 单轮最多 30 次有效工具调用（含重复调用保护）
- 连续重复的同参工具调用会自动复用上次结果
- `read_file` 默认读取 120 行，减少碎片化读取
- 多轮对话支持
- agent 与 TUI 分离运行（agent 为独立子进程）
- 自动托管启动（启动 `repo-agent` 后自动拉起 agent 并进入 TUI）

## 环境要求

- Python 3.10+
- Kimi API Key（Moonshot，付费 API）

## 安装

建议先创建虚拟环境，再安装依赖，避免与系统 Python 混用。

**1. 创建并激活虚拟环境**

```bash
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

**2. 在项目根目录安装**

```bash
# 方式一：可编辑安装（推荐），核心依赖由 pyproject.toml 提供
pip install -e .

# 方式二：先装 requirements.txt 再可编辑安装（含 pytest，便于开发与测试）
pip install -r requirements.txt
pip install -e .
```

`textual` 已作为基础依赖内置，无需额外安装 TUI 扩展包。  
安装后可直接使用 `repo-agent` 命令（等价于 `python -m repo_agent`）。

### 开发与测试

```bash
pytest tests -v
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

在 `.env` 中配置 Kimi（Moonshot）：

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

`.env` 示例（完整模板见项目根目录 `.env.example`）：

```env
# Kimi（Moonshot）配置
LLM_PROVIDER=kimi
MOONSHOT_API_KEY=your_kimi_api_key_here
KIMI_MODEL_ID=kimi-k2-turbo-preview
KIMI_BASE_URL=https://api.moonshot.cn/v1

# RAG 向量化（可选）：local（默认）| openai；Kimi 无 Embedding API
# REPO_AGENT_EMBEDDING=openai   # 需配置 OPENAI_API_KEY

# Agent 服务配置（可选）
AGENTD_HOST=127.0.0.1
AGENTD_PORT=8765
AGENTD_TOKEN=
```

## 使用方法

Agent 只会访问**repo-agent 启动时的当前工作目录**下的文件，因此请先进入要分析的代码仓库目录再启动。

启动方式（自动托管模式）：

```bash
repo-agent
# 或
python -m repo_agent
```

说明：当前版本不再提供 `--mode service/cli/tui/local` 运行模式参数。

当前行为如下：

1. 自动启动一个独立的 agent 服务子进程（HTTP daemon）。
2. 自动打开 TUI，并连接该子进程。
3. 退出 TUI 后，主进程会自动关闭该 agent 子进程。

可选参数：

- `--host` / `--port`：指定托管 agent 的监听地址（默认 `127.0.0.1:8765`）。
- `--token`：指定访问令牌（请求头 `X-Agent-Token`）。
- `--session-id`：TUI 启动后附着到指定会话。
- `--max-events`：每个会话保留的最大事件数（默认 `2000`）。
- `--startup-timeout`：等待 agent 启动超时时间（秒，默认 `15`）。

环境变量（可选）：

- `AGENTD_HOST`：默认监听地址（默认 `127.0.0.1`）。
- `AGENTD_PORT`：默认监听端口（默认 `8765`）。
- `AGENTD_TOKEN`：服务访问令牌（等价于启动参数 `--token`）。
- `REPO_AGENTD_ACCESS_LOG`：是否输出 HTTP 访问日志（`1/true/yes/on` 表示开启，默认关闭）。

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
| `/clear` | 清除对话历史 |
| `/status` | 查看会话状态（busy/pending 等） |
| `/cancel` | 取消等待中的任务（不强制中断当前执行） |
| `/quit` | 退出程序 |
| `/help` | 显示帮助 |
| `Ctrl+C` | 退出程序 |

TUI 额外快捷键：

| 快捷键 | 说明 |
|------|------|
| `Ctrl+L` | 清空会话与日志 |
| `Ctrl+K` | 取消等待中的任务 |

命令补全：
- 在输入框键入 `/` 后会显示命令候选。
- 使用 `↑` / `↓` 选择候选命令，输入框会同步自动补全。
- 使用 `Tab` 补全当前候选。
- `Enter` 在未补全时会先补全一次；再次按 `Enter` 才会执行命令。

## 项目结构

```
repo_agent/
├── repo_agent/              # 主包
│   ├── __init__.py
│   ├── __main__.py          # 入口：自动托管 agent + TUI
│   ├── config/              # 配置
│   │   ├── __init__.py
│   │   └── settings.py      # API Key + agentd 地址/token
│   ├── agent/               # Agent 核心
│   │   ├── __init__.py
│   │   ├── client.py        # Kimi 客户端（OpenAI 兼容）
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
│   ├── tools/               # 工具
│   │   ├── __init__.py
│   │   ├── registry.py      # 工具注册表（声明 + 函数）
│   │   ├── repo.py          # 仓库工具：search_files, read_file, list_dir
│   │   └── rag.py           # RAG 工具：search_knowledge_base
│   ├── ui/                  # 远程 TUI 交互层
│   │   ├── __init__.py
│   │   └── tui.py
│   ├── rag/                 # RAG（本地检索增强）
│   │   ├── __init__.py
│   │   ├── embeddings.py    # 本地 Embedding（sentence-transformers）
│   │   ├── store.py         # 向量存储（Chroma）
│   │   └── retriever.py     # 检索器
│   └── kb/                  # 知识库
│       ├── __init__.py
│       ├── loader.py        # 文档加载
│       └── index.py         # 索引构建（分块、向量化、写入 store）
├── requirements.txt         # 可选，含 pytest，用于开发/测试
├── pyproject.toml           # 包配置与依赖，支持 pip install -e .
├── .env.example             # 环境变量模板，复制为 .env 后填写
├── .gitignore
└── README.md
```

## RAG 与知识库（可选）

启用语义检索需安装可选依赖并构建索引：

```bash
pip install -e ".[rag]"
repo-agent build-kb
```

若使用 **pipx** 安装，可只注入 RAG 所需部分依赖（无需 Chroma 的 C++ 构建环境）：

```bash
# 仅安装 sentence-transformers + numpy，使用内置简单向量存储（适合 Windows）
pipx inject repo-agent sentence-transformers numpy
repo-agent build-kb
```

- **何时需要 build-kb**：每个项目只需在**第一次**想用语义检索时构建一次；之后在该项目下启动 Agent 会自动使用已有索引。也可不手动执行——**首次调用 `search_knowledge_base` 时若发现索引为空，会自动做「轻量」构建（约 150 文件/1500 块）再检索**，避免大仓库一次性占满内存导致进程被系统杀掉。
- **build-kb 的作用**：在当前工作目录递归加载文本文件（.py、.md、.txt 等），分块后向量化并写入项目下的 `.repo_agent_kb/`。索引按项目隔离，换目录启动 Agent 即自动用该目录的索引。**大项目（数千文件）建议在终端单独执行 `repo-agent build-kb` 做完整索引，避免在 Agent 内首次自动构建时占用过多内存。**
- **Windows 说明**：若安装 `chromadb` 时报错「Microsoft Visual C++ 14.0 or greater is required」，可**不安装 chromadb**，只安装 `sentence-transformers` 和 `numpy`；程序会自动使用内置的纯 Python 向量存储，无需 C++ 编译。
- **内存说明**：即使仓库只有几 KB 代码，**首次**执行 build-kb 会加载 sentence-transformers 和 PyTorch，可能占用约 **2～8GB 内存**（视是否安装 GPU 版 PyTorch）。若本机内存紧张或出现闪退/黑屏，可先安装 **CPU 版 PyTorch** 再装 sentence-transformers，以降低占用：  
  `pip install torch --index-url https://download.pytorch.org/whl/cpu`，然后再 `pip install sentence-transformers`（或 `pipx inject repo-agent sentence-transformers numpy`）。
- **低内存 / 无 GPU 环境（如 16GB 内存办公机）**：可设置环境变量 `REPO_AGENT_LOW_MEMORY=1` 再执行 build-kb 或使用语义检索。该模式下会使用更小的 embedding 模型（paraphrase-MiniLM-L3-v2）并减小建索引的批大小，显著降低内存与 CPU 占用，适合「16GB 内存、无独显」的机器。若之前未在低内存模式下建过索引，启用后需重新执行一次 `repo-agent build-kb`。  
  示例（PowerShell）：`$env:REPO_AGENT_LOW_MEMORY="1"; repo-agent build-kb`
- **使用云端 API 做向量化（推荐内存紧张时）**：在 **运行 `repo-agent build-kb` 之前**，在 `.env` 中设置 `REPO_AGENT_EMBEDDING=openai` 并配置 `OPENAI_API_KEY`；建索引与检索不占本地模型内存，按调用量计费。执行 build-kb 时首行会显示「向量化：openai」或「向量化：local」。使用云端后需重新执行一次 `repo-agent build-kb`（因向量维度与本地模型不同）。**说明**：Kimi 不提供 Embedding API，向量化仅支持 local（默认）与 openai。
- **建索引时内存/CPU 仍很高**：当前默认使用 SimpleStore（按批落盘，内存 <100MB），不再默认加载 Chroma。若需 Chroma 后端可设 `REPO_AGENT_USE_CHROMA=1`（内存占用高）。也可用 `repo-agent build-kb --max-chunks 5000` 或 `--max-files 500` 限制索引规模。
- 未安装 `[rag]` 时，调用 `search_knowledge_base` 会得到安装提示，不影响其他工具使用。

## 扩展说明

- **新增工具**：在 `repo_agent/tools/` 下实现函数，并在 `registry.py` 中注册名称与函数声明（会适配 Kimi/OpenAI 兼容接口）。
- **本地 RAG**：已实现 `rag/` 的 `embeddings`、`store`、`retriever` 及工具 `search_knowledge_base`；可扩展为预注入上下文等。
- **本地知识库**：已实现 `kb/` 的 `loader` 与 `index`，通过 `repo-agent build-kb` 构建索引。

## 安全说明

- 所有文件操作均为只读
- 路径限制在当前工作目录内，禁止路径逃逸
- 不执行任何 shell 命令
- 不写入任何文件
- `agent` 服务默认本机监听（`127.0.0.1`）
- 如需额外保护，可配置 `AGENTD_TOKEN` 启用请求鉴权
- `.env` 已在 `.gitignore` 中，默认不会被提交
- 提交前请确认仓库中没有明文密钥（如 `sk-`、`AIza`）
