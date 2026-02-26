# 本地代码仓库问答 Agent

（此处待翻译）

## 功能

- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）

## 环境要求

- （此处待翻译）
- （此处待翻译）

## 安装

（此处待翻译）

```bash
pip install -r requirements.txt
```

（此处待翻译）

```bash
pip install -e .
```

（此处待翻译）
（此处待翻译）

## 配置模型与 API Key

（此处待翻译）
（此处待翻译）

```bash
# Linux / macOS
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

（此处待翻译）

```bash
# Linux / macOS（gemini / kimi 二选一）
export LLM_PROVIDER=gemini

# Windows PowerShell
$env:LLM_PROVIDER="gemini"
```

### Gemini

（此处待翻译）

```bash
# Linux / macOS
export GEMINI_API_KEY=your_api_key_here

# Windows PowerShell
$env:GEMINI_API_KEY="your_api_key_here"

# Windows CMD
set GEMINI_API_KEY=your_api_key_here
```

（此处待翻译）

（此处待翻译）

- （此处待翻译）
- （此处待翻译）

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

（此处待翻译）

（此处待翻译）

```env
LLM_PROVIDER=kimi
MOONSHOT_API_KEY=your_kimi_api_key_here
KIMI_MODEL_ID=kimi-k2-turbo-preview
KIMI_BASE_URL=https://api.moonshot.cn/v1

# 可选：切回 Gemini 时使用
GEMINI_API_KEY=your_gemini_api_key_here
```

## 使用方法

（此处待翻译）

（此处待翻译）

```bash
repo-agent
# 或
python -m repo_agent
```

（此处待翻译）

（此处待翻译）

1. （此处待翻译）
2. （此处待翻译）
3. （此处待翻译）

（此处待翻译）

- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）

（此处待翻译）

- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）

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

| （此处待翻译） | （此处待翻译） |
|------|------|
| （此处待翻译） | （此处待翻译） |
| （此处待翻译） | （此处待翻译） |
| （此处待翻译） | （此处待翻译） |
| （此处待翻译） | （此处待翻译） |
| （此处待翻译） | （此处待翻译） |
| （此处待翻译） | （此处待翻译） |

（此处待翻译）

| （此处待翻译） | （此处待翻译） |
|------|------|
| （此处待翻译） | （此处待翻译） |
| （此处待翻译） | （此处待翻译） |

（此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）

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

- （此处待翻译）
- （此处待翻译）
- （此处待翻译）

## 安全说明

- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
- （此处待翻译）
