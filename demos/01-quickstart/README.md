# CLOVE Quickstart Demo

A simple introduction to the CLOVE kernel, demonstrating basic operations.

## What This Demo Shows

1. **Kernel Connection** - Connect to the CLOVE kernel
2. **Kernel Info** - Query version, capabilities, and uptime
3. **Command Execution** - Run shell commands through the kernel
4. **Echo/NOOP** - Basic message round-trip
5. **State Store** - Store and retrieve key-value data
6. **Agent Listing** - See active agents

## Prerequisites

1. CLOVE kernel must be running:
   ```bash
   # From repo root
   ./build/clove_kernel
   ```

2. Python SDK must be available (it's in `agents/python_sdk/`)

## Running

```bash
cd demos/01-quickstart
python main.py
```

## Expected Output

```
Kernel Version: 0.3.0
Agent ID: 1
Capabilities: spawn, ipc, state, events, ...
Uptime: 123.4s

Command output: Linux hostname 5.15.0 ...
Echo response: Hello from quickstart!
Stored and retrieved: {'message': 'Hello CLOVE!', ...}

Active agents: 1
  - quickstart (ID: 1, State: running)

Quickstart demo completed successfully!
```

## Next Steps

After this demo, try:
- `02-ml-pipeline` - Multi-stage ML pipeline with resource limits
- `03-incident-response` - Multi-agent security monitoring
- `04-agentic-research` - LLM-powered research agents
