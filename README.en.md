# Local Code Repository Q&A Agent

[English](./README.en.md) | [中文](./README.zh.md) | [Home](./README.md)

A Python-based local code repository Q&A agent using Kimi (Moonshot) paid API. Through the Function Calling/Tool Calling mechanism, it automatically invokes tool functions to access the code repository under the **current working directory** and answer users' natural-language questions. The current version adopts an architecture of "**managed Agent subprocess + TUI frontend**", and the project layout reserves modules for future **local RAG** and **local knowledge base** extensions.

## Features

- Natural-language questions (Chinese supported)
- Automatic code content search (`search_files`)
- Read specific file snippets (`read_file`)
- List directory structure (`list_dir`)
- Uses Kimi (OpenAI-compatible) API
- Agent loop based on Function Calling/Tool Calling
- Up to 30 effective tool calls per turn (with duplicate-call protection)
- Consecutive repeated tool calls with identical arguments automatically reuse the previous result
- `read_file` reads 120 lines by default to reduce fragmented reads
- Multi-turn conversation support
- Agent and TUI run separately (agent runs as an independent subprocess)
- Managed startup (starting `repo-agent` automatically launches the agent and enters TUI)

## Requirements

- Python 3.10+
- Kimi API Key (Moonshot, paid API)

## Installation

Create a virtual environment first, then install from `requirements.txt` so dependencies stay isolated.

**1. Create and activate a virtual environment**

```bash
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

**2. Install dependencies in the project root**

```bash
pip install -r requirements.txt
pip install -e .
```

`textual` is already included as a base dependency, so no extra TUI extension package is needed.
After installation, you can use the `repo-agent` command (equivalent to `python -m repo_agent`).

### Development and testing

```bash
pytest tests -v
```

## Configure Model and API Key

Recommended approach: create `.env` in the project root (do not commit it to the repository).
You can copy the template first:

```bash
# Linux / macOS
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

Configure Kimi (Moonshot) in `.env`:

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

Optional: if you need a custom OpenAI-compatible endpoint, set `KIMI_BASE_URL` (default: `https://api.moonshot.cn/v1`).

`.env` example:

```env
LLM_PROVIDER=kimi
MOONSHOT_API_KEY=your_kimi_api_key_here
KIMI_MODEL_ID=kimi-k2-turbo-preview
KIMI_BASE_URL=https://api.moonshot.cn/v1
```

## Usage

The agent only accesses files under the **current working directory where repo-agent is started**, so enter the target code repository directory before starting.

Startup (managed mode):

```bash
repo-agent
# or
python -m repo_agent
```

Note: the current version no longer provides the `--mode service/cli/tui/local` runtime mode parameter.

Current behavior:

1. Automatically starts an independent agent service subprocess (HTTP daemon).
2. Automatically opens TUI and connects to that subprocess.
3. After exiting TUI, the main process automatically stops that agent subprocess.

Optional parameters:

- `--host` / `--port`: Specify the listening address of the managed agent (default: `127.0.0.1:8765`).
- `--token`: Specify an access token (request header `X-Agent-Token`).
- `--session-id`: Attach to a specified session after TUI startup.
- `--max-events`: Maximum number of events retained per session (default: `2000`).
- `--startup-timeout`: Timeout for waiting agent startup (seconds, default: `15`).

Environment variables (optional):

- `AGENTD_HOST`: Default listen address (default: `127.0.0.1`).
- `AGENTD_PORT`: Default listen port (default: `8765`).
- `AGENTD_TOKEN`: Service access token (equivalent to startup parameter `--token`).
- `REPO_AGENTD_ACCESS_LOG`: Whether to output HTTP access logs (`1/true/yes/on` means enabled, disabled by default).

## Interaction Example

```
You: What is the directory structure of this project?
  [Tool Call #1] list_dir({"path": "."})
  [Tool Result] ./
  ├── repo_agent/
  ├── pyproject.toml
  ├── README.md
  ...

Agent: This project contains the following files: ...

You: Find all files that contain "def "
  [Tool Call #1] search_files({"query": "def "})
  [Tool Result] 15 matches found...

Agent: The following functions are defined in this project: ...
```

## Built-in Commands

| Command | Description |
|------|------|
| `/clear` | Clear conversation history |
| `/status` | View session status (busy/pending, etc.) |
| `/cancel` | Cancel pending tasks (does not forcibly interrupt current execution) |
| `/quit` | Exit program |
| `/help` | Show help |
| `Ctrl+C` | Exit program |

Additional TUI shortcuts:

| Shortcut | Description |
|------|------|
| `Ctrl+L` | Clear session and logs |
| `Ctrl+K` | Cancel pending tasks |

Command completion:
- Type `/` in the input box to show command candidates.
- Use `↑` / `↓` to select a candidate command, and the input box will auto-complete accordingly.
- Use `Tab` to complete the current candidate.
- If not yet completed, pressing `Enter` completes once first; press `Enter` again to execute the command.

## Project Structure

```
repo_agent/
├── repo_agent/              # Main package
│   ├── __init__.py
│   ├── __main__.py          # Entry: managed agent + TUI
│   ├── config/              # Configuration
│   │   ├── __init__.py
│   │   └── settings.py      # API Key + agentd address/token
│   ├── agent/               # Agent core
│   │   ├── __init__.py
│   │   ├── client.py        # Kimi client (OpenAI-compatible)
│   │   ├── prompts.py       # System prompts and constants
│   │   └── loop.py          # Main loop and tool scheduling
│   ├── daemon/              # Long-running service side
│   │   ├── __init__.py
│   │   ├── app.py           # HTTP API
│   │   ├── models.py        # Event/task models
│   │   └── session_manager.py
│   ├── remote/              # Remote client SDK
│   │   ├── __init__.py
│   │   └── client.py
│   ├── tools/               # Tools
│   │   ├── __init__.py
│   │   ├── registry.py      # Tool registry (declarations + functions)
│   │   └── repo.py          # Repository tools: search_files, read_file, list_dir
│   ├── ui/                  # Remote TUI interaction layer
│   │   ├── __init__.py
│   │   └── tui.py
│   ├── rag/                 # RAG reserved (local retrieval enhancement)
│   │   ├── __init__.py
│   │   ├── embeddings.py    # Local embedding
│   │   ├── store.py         # Vector storage
│   │   └── retriever.py     # Retriever
│   └── kb/                  # Knowledge base reserved
│       ├── __init__.py
│       ├── loader.py        # Document loading
│       └── index.py         # Index building
├── requirements.txt
├── pyproject.toml           # Package config, supports pip install -e .
├── .gitignore
└── README.md
```

## Extension Notes

- **Add new tools**: Implement functions under `repo_agent/tools/`, and register names and function declarations in `registry.py` (adapted for Kimi/OpenAI-compatible API).
- **Local RAG**: Implement `embeddings`, `store`, and `retriever` in `rag/`, then either add new tools (such as `search_knowledge_base`) or inject as context.
- **Local knowledge base**: Implement `loader` and `index` in `kb/`, chunk and vectorize documents, then write them into `rag.store`.

## Security Notes

- All file operations are read-only
- Path access is restricted within the current working directory; path traversal is forbidden
- No shell commands are executed
- No files are written
- The `agent` service listens on localhost by default (`127.0.0.1`)
- For extra protection, configure `AGENTD_TOKEN` to enable request authentication
- `.env` is listed in `.gitignore` and will not be committed by default
- Before committing, ensure no plaintext secrets exist in the repository (for example, `sk-`, `AIza`)
