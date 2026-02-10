# Clove

A microkernel runtime for AI agents. Provides OS-level isolation, resource limits, and sandboxing for autonomous agents.

```
┌─────────────────────────────────┐
│  Your Agent Code (Python)       │  ← pip install clove-sdk
│  from clove_sdk import ...      │
└────────────┬────────────────────┘
             │ Unix socket
┌────────────▼────────────────────┐
│  Clove Kernel (C++)             │  ← ./clove_kernel
│  • Process isolation            │
│  • cgroups resource limits      │
│  • Linux namespace sandboxing   │
│  • Inter-agent IPC              │
└─────────────────────────────────┘
```

---

## Quick Start

### 1. Build the Kernel

```bash
# Clone and build
git clone https://github.com/anixd/clove.git
cd clove

# Install dependencies (Ubuntu/Debian)
sudo apt install build-essential cmake libssl-dev pkg-config

# Build
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
```

### 2. Run the Kernel

```bash
# Start the kernel (requires root for full sandboxing)
sudo ./clove_kernel

# Or without sandboxing (no root required)
./clove_kernel --no-sandbox
```

The kernel listens on `/tmp/clove.sock` by default.

### 3. Install the SDK

```bash
pip install clove-sdk
```

### 4. Write Your First Agent

```python
from clove_sdk import CloveClient

with CloveClient() as client:
    # Test connection
    info = client.hello()
    print(f"Connected to kernel v{info.version}")

    # Execute a command
    result = client.exec("echo 'Hello from Clove!'")
    print(result.stdout)

    # Read/write files
    client.write_file("/tmp/test.txt", "Hello World")
    content = client.read_file("/tmp/test.txt")
    print(content.content)
```

Run it:
```bash
python my_agent.py
```

---

## SDK Features

### Command Execution

```python
from clove_sdk import CloveClient, ExecResult

with CloveClient() as client:
    result: ExecResult = client.exec("ls -la /tmp")
    print(f"Exit code: {result.exit_code}")
    print(result.stdout)
```

### Spawn Child Agents

```python
from clove_sdk import CloveClient, SpawnResult

with CloveClient() as client:
    # Spawn a sandboxed agent with resource limits
    spawn: SpawnResult = client.spawn(
        name="worker",
        script="/path/to/worker.py",
        sandboxed=True,
        limits={"memory": 256 * 1024 * 1024, "cpu_quota": 50000}
    )
    print(f"Spawned agent {spawn.agent_id} (PID: {spawn.pid})")

    # List running agents
    agents = client.list_agents()
    for agent in agents:
        print(f"{agent.name}: {agent.state.value}")

    # Kill an agent
    client.kill(name="worker")
```

### Inter-Agent Communication

```python
# Agent A: Send a message
client.register_name("orchestrator")
client.send_message({"task": "process_data"}, to_name="worker")

# Agent B: Receive messages
messages = client.recv_messages()
for msg in messages.messages:
    print(f"From {msg.from_name}: {msg.message}")
```

### State Store

```python
# Store data (persists across agent restarts)
client.store("config", {"model": "gpt-4", "temp": 0.7})

# Fetch data
result = client.fetch("config")
if result.found:
    print(result.value)
```

### LLM Integration

Set your API key:
```bash
export GEMINI_API_KEY=your_key_here
```

```python
with CloveClient() as client:
    response = client.think("Explain quantum computing in one sentence")
    print(response['content'])
```

---

## Kernel Options

```bash
./clove_kernel [OPTIONS]

Options:
  --socket PATH       Socket path (default: /tmp/clove.sock)
  --no-sandbox        Disable Linux namespace isolation
  --log-level LEVEL   Log level: debug, info, warn, error (default: info)
```

---

## Requirements

| Component | Requirements |
|-----------|--------------|
| **Kernel** | Linux x86_64, Ubuntu 22.04+, GCC 12+ or Clang 15+ |
| **SDK** | Python 3.10+, any platform |
| **Full Sandboxing** | Root privileges, cgroups v2 |

### Build Dependencies

```bash
# Ubuntu/Debian
sudo apt install build-essential cmake libssl-dev pkg-config

# Fedora
sudo dnf install gcc-c++ cmake openssl-devel pkgconf-pkg-config
```

---

## Project Structure

```
clove/
├── src/                    # C++ kernel source
│   ├── kernel/             # Core kernel (syscalls, router)
│   ├── runtime/            # Agent lifecycle management
│   ├── ipc/                # Wire protocol
│   └── metrics/            # System metrics collection
├── agents/
│   ├── python_sdk/         # Python SDK (clove-sdk)
│   └── llm_service/        # LLM integration service
└── cli/                    # Command-line tools
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [System Design](SYSTEM_DESIGN.md) | Architecture and internals |
| [Python SDK](agents/python_sdk/README.md) | Full SDK API reference |

---

## License

MIT
