# 本地代码仓库问答 Agent

基于 Python + Google Gemini API 的本地代码仓库问答 Agent。通过 Function Calling 机制，自动调用工具函数访问本地代码仓库，回答用户的自然语言问题。

## 功能

- 自然语言提问（支持中文）
- 自动搜索代码文件内容（`search_files`）
- 读取指定文件片段（`read_file`）
- 列出目录结构（`list_dir`）
- 基于 Gemini Function Calling 的 Agent 循环
- 多轮对话支持

## 环境要求

- Python 3.10+
- Google AI Studio 免费 API Key（[获取地址](https://aistudio.google.com/apikey)）

## 安装

```bash
cd repo_agent
pip install -r requirements.txt
```

## 配置 API Key

方式一：设置环境变量

```bash
# Linux / macOS
export GEMINI_API_KEY=your_api_key_here

# Windows PowerShell
$env:GEMINI_API_KEY="your_api_key_here"

# Windows CMD
set GEMINI_API_KEY=your_api_key_here
```

方式二：在 `repo_agent/` 目录下创建 `.env` 文件

```
GEMINI_API_KEY=your_api_key_here
```

## 使用方法

进入你想要分析的代码仓库目录，然后运行：

```bash
cd /path/to/your/code/repo
python /path/to/repo_agent/agent.py
```

或者直接在 `repo_agent/` 目录运行（将分析 `repo_agent` 自身）：

```bash
cd repo_agent
python agent.py
```

## 交互示例

```
You: 这个项目的目录结构是什么？
  [工具调用 #1] list_dir({"path": "."})
  [工具结果] ./  ├── agent.py  ├── config.py  ...

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
| `/quit` | 退出程序 |
| `/help` | 显示帮助 |
| `Ctrl+C` | 退出程序 |

## 项目结构

```
repo_agent/
├── agent.py           # 主循环逻辑（Agent 核心）
├── tools.py           # 工具函数定义（search_files, read_file, list_dir）
├── config.py          # API Key 读取
├── requirements.txt   # 依赖
└── README.md          # 说明文档
```

## 安全说明

- 所有文件操作均为只读
- 路径限制在当前工作目录内，禁止路径逃逸
- 不执行任何 shell 命令
- 不写入任何文件
