# Clove SDK

Python client for the Clove kernel.

## Installation

```bash
pip install clove-sdk
```

## Quick Start

```python
from clove_sdk import CloveClient

with CloveClient() as client:
    # Test connection
    info = client.hello()
    print(f"Connected to kernel v{info.version}")

    # Execute commands
    result = client.exec("ls -la")
    print(result.stdout)

    # Read/write files
    client.write_file("/tmp/test.txt", "Hello")
    content = client.read_file("/tmp/test.txt")
    print(content.content)
```

## API Reference

### Command Execution

```python
from clove_sdk import ExecResult

result: ExecResult = client.exec("echo hello", timeout=30)
# result.success, result.stdout, result.stderr, result.exit_code
```

### Agent Management

```python
from clove_sdk import SpawnResult, AgentInfo

# Spawn agent
spawn: SpawnResult = client.spawn(
    name="worker",
    script="/path/to/worker.py",
    sandboxed=True,
    limits={"memory": 256 * 1024 * 1024}
)

# List agents
agents: list[AgentInfo] = client.list_agents()

# Kill agent
client.kill(name="worker")
```

### Inter-Agent Communication

```python
# Register name
client.register_name("orchestrator")

# Send message
client.send_message({"task": "process"}, to_name="worker")

# Receive messages
messages = client.recv_messages()
for msg in messages.messages:
    print(f"From {msg.from_name}: {msg.message}")

# Broadcast
client.broadcast({"event": "shutdown"})
```

### State Store

```python
from clove_sdk import FetchResult

# Store
client.store("key", {"data": "value"}, scope="global")

# Fetch
result: FetchResult = client.fetch("key")
if result.found:
    print(result.value)

# List keys
keys = client.list_keys(prefix="user:")
```

### Metrics

```python
from clove_sdk import SystemMetrics, AgentMetrics

# System metrics
sys: SystemMetrics = client.get_system_metrics()
print(f"CPU: {sys.cpu_percent}%")

# Agent metrics
agent: AgentMetrics = client.get_agent_metrics(agent_id=1)
print(f"Memory: {agent.memory_bytes} bytes")
```

### LLM Integration

```bash
export GEMINI_API_KEY=your_key
```

```python
response = client.think("Explain quantum computing")
print(response['content'])
```

## Exception Handling

```python
from clove_sdk import (
    CloveError,       # Base exception
    ConnectionError,  # Failed to connect
    SyscallError,     # Syscall failed
    AgentNotFound,    # Agent doesn't exist
)

try:
    client.kill(name="nonexistent")
except AgentNotFound as e:
    print(f"Not found: {e}")
```

## Architecture

```
clove_sdk/
├── client.py       # CloveClient (main entry point)
├── protocol.py     # Wire protocol, SyscallOp enum
├── transport.py    # Socket communication
├── models.py       # Response dataclasses (30+)
├── exceptions.py   # Exception hierarchy
└── mixins/         # Domain-specific operations
    ├── agents.py
    ├── filesystem.py
    ├── ipc.py
    ├── state.py
    ├── events.py
    └── metrics.py
```

## Requirements

- Python 3.10+
- Running Clove kernel (see main README)
