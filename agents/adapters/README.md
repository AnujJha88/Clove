# Clove Framework Adapters

This directory contains adapters that enable popular AI agent frameworks to use Clove as their execution backend.

## Why Use These Adapters?

Instead of giving AI agents direct access to your system, these adapters route all operations through Clove's permission system:

- **Path restrictions** - Agents can only access approved directories
- **Command filtering** - Dangerous commands are blocked
- **Domain whitelist** - HTTP requests limited to approved domains
- **LLM quotas** - Token and call limits prevent runaway costs
- **Process isolation** - Spawned agents run in sandboxes

## Available Adapters

| Adapter | Framework | Status |
|---------|-----------|--------|
| `langchain_adapter.py` | LangChain | ✅ Ready |
| `crewai_adapter.py` | CrewAI | ✅ Ready |
| `autogen_adapter.py` | Microsoft AutoGen | ✅ Ready |

## Prerequisites

1. Clove kernel must be running:
```bash
./build/clove_kernel
```

2. Install the framework you want to use:
```bash
# For LangChain
pip install langchain langchain-core pydantic

# For CrewAI
pip install crewai

# For AutoGen
pip install pyautogen
```

## LangChain Adapter

The LangChain adapter provides Clove syscalls as LangChain tools.

### Quick Start

```python
from langchain.agents import create_react_agent, AgentExecutor
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate

# Import Clove toolkit
import sys
sys.path.insert(0, '/path/to/CLOVE/agents/adapters')
from langchain_adapter import CloveToolkit

# Create toolkit (connects to Clove)
toolkit = CloveToolkit(permission_level="standard")
tools = toolkit.get_tools()

# Create LangChain agent
llm = ChatOpenAI(model="gpt-4")
prompt = PromptTemplate.from_template("...")
agent = create_react_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools)

# Run
result = executor.invoke({"input": "Read the file /tmp/test.txt"})
```

### Available Tools

- `clove_read` - Read files
- `clove_write` - Write files
- `clove_exec` - Execute commands
- `clove_think` - Query LLM
- `clove_spawn` - Spawn agents
- `clove_http` - HTTP requests

## CrewAI Adapter

The CrewAI adapter provides Clove-backed tools and agents for CrewAI.

### Quick Start

```python
from crewai import Task, Crew

import sys
sys.path.insert(0, '/path/to/CLOVE/agents/adapters')
from crewai_adapter import CloveCrewAgent

# Create agent factory
factory = CloveCrewAgent(permission_level="standard")

# Create agents
researcher = factory.create_researcher()
developer = factory.create_developer()

# Create tasks
task1 = Task(
    description="Research the latest Python best practices",
    agent=researcher
)
task2 = Task(
    description="Write a Python script following best practices",
    agent=developer
)

# Run crew
crew = Crew(agents=[researcher, developer], tasks=[task1, task2])
result = crew.kickoff()
```

### Pre-built Agent Types

- `create_researcher()` - Read-only tools for research
- `create_developer()` - Full tools for development
- `create_orchestrator()` - Can spawn and manage sub-agents

## AutoGen Adapter

The AutoGen adapter enables AutoGen agents to execute through Clove.

### Quick Start

```python
import sys
sys.path.insert(0, '/path/to/CLOVE/agents/adapters')
from autogen_adapter import CloveAssistant, CloveUserProxy

# Create assistant with Clove tools
assistant = CloveAssistant(
    name="coder",
    llm_config={"config_list": [{"model": "gpt-4", "api_key": "..."}]},
    permission_level="standard"
)

# Create user proxy that executes through Clove
user_proxy = CloveUserProxy(
    name="user",
    human_input_mode="NEVER"
)

# Start conversation
user_proxy.initiate_chat(
    assistant,
    message="Create a Python script that lists files in /tmp"
)
```

### Code Execution

The `CloveUserProxy` automatically routes code execution through Clove:

- Python code is written to a temp file and executed via `clove_exec`
- Bash/shell commands are executed directly via `clove_exec`
- All execution respects Clove permission settings

## Permission Levels

All adapters accept a `permission_level` parameter:

| Level | Description |
|-------|-------------|
| `unrestricted` | No restrictions (dangerous!) |
| `standard` | Default restrictions for safe operation |
| `sandboxed` | Strict restrictions, limited paths |
| `readonly` | Can only read, no writes or execution |
| `minimal` | Almost no permissions |

### Example with Restricted Permissions

```python
# LangChain with read-only access
toolkit = CloveToolkit(permission_level="readonly")
tools = toolkit.get_read_tools()  # Only reading tools

# CrewAI with sandboxed access
factory = CloveCrewAgent(permission_level="sandboxed")
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Your Application                          │
├─────────────────────────────────────────────────────────────┤
│   LangChain     │     CrewAI      │      AutoGen            │
│   Agent         │     Crew        │      Agents             │
├─────────────────────────────────────────────────────────────┤
│            Clove Framework Adapters                        │
│   (langchain_adapter / crewai_adapter / autogen_adapter)    │
├─────────────────────────────────────────────────────────────┤
│                  Clove Python SDK                          │
│                    (clove.py)                              │
├─────────────────────────────────────────────────────────────┤
│                Unix Domain Socket IPC                        │
├─────────────────────────────────────────────────────────────┤
│                  Clove Kernel                              │
│        (Permission System, Sandboxing, Quotas)              │
├─────────────────────────────────────────────────────────────┤
│                 System Resources                             │
│        (Files, Processes, Network, LLM APIs)                │
└─────────────────────────────────────────────────────────────┘
```

## Troubleshooting

### "Failed to connect to Clove kernel"

Make sure the kernel is running:
```bash
./build/clove_kernel
```

### "Permission denied" errors

Check your permission level. Use `standard` for most cases:
```python
toolkit = CloveToolkit(permission_level="standard")
```

### Framework not installed

Install the required framework:
```bash
pip install langchain  # or crewai, pyautogen
```

### Import errors

Make sure the adapters directory is in your Python path:
```python
import sys
sys.path.insert(0, '/path/to/CLOVE/agents/adapters')
```
