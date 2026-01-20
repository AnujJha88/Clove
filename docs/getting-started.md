# Getting Started with AgentOS

## Prerequisites

- Linux (Ubuntu 22.04+ / Debian 12+)
- GCC 11+ with C++23 support
- CMake 3.20+
- Python 3.10+
- Root access (optional, for full sandbox isolation)

## Quick Install

```bash
# Clone
git clone <repo-url> AgentOS
cd AgentOS

# Run install script
./scripts/install.sh

# Set up API key
cp .env.example .env
# Edit .env and add GEMINI_API_KEY
```

## Manual Install

### 1. System Dependencies

```bash
sudo apt update
sudo apt install -y build-essential cmake pkg-config libssl-dev python3 python3-pip
```

### 2. vcpkg (C++ package manager)

```bash
git clone https://github.com/Microsoft/vcpkg.git ~/vcpkg
~/vcpkg/bootstrap-vcpkg.sh
export VCPKG_ROOT="$HOME/vcpkg"
```

### 3. Python Dependencies

```bash
pip3 install google-genai websockets
```

### 4. Build Kernel

```bash
cd AgentOS
mkdir -p build && cd build
cmake ..
make -j$(nproc)
```

### 5. Configure

```bash
cp .env.example .env
# Add your Gemini API key to .env
```

## Running AgentOS

### Start the Kernel

```bash
./build/agentos_kernel
```

For full sandbox isolation (namespaces + cgroups):
```bash
sudo ./build/agentos_kernel
```

### Run Your First Agent

```bash
python3 agents/examples/hello_agent.py
```

### Start the Dashboard

```bash
# Terminal 1: Kernel (already running)

# Terminal 2: WebSocket proxy
python3 agents/dashboard/ws_proxy.py

# Terminal 3: HTTP server
cd agents/dashboard && python3 -m http.server 8000

# Open http://localhost:8000
```

## Basic SDK Usage

```python
from agentos import AgentOSClient

with AgentOSClient() as client:
    # Echo test
    result = client.noop("Hello!")
    print(result)

    # LLM query
    response = client.think("What is 2+2?")
    print(response['content'])

    # Spawn an agent
    agent = client.spawn(
        name="worker",
        script="/path/to/agent.py",
        sandboxed=True
    )

    # List agents
    agents = client.list_agents()

    # Kill agent
    client.kill(name="worker")
```

## CLI Tool

The `agentos` CLI provides fleet management and remote deployment.

### Install CLI

```bash
cd cli
pip install -e .

# Or install dependencies manually
pip install -r requirements.txt
```

### Configure

```bash
# Set relay server URL
agentos config set relay_url http://localhost:8766

# View configuration
agentos config show
```

### Deploy to Docker

```bash
# Deploy a local Docker container
agentos deploy docker --name dev-kernel

# Check status
agentos status
```

### Deploy to AWS

```bash
# Deploy to AWS EC2
agentos deploy aws --region us-east-1 --instance-type t3.micro

# View machines
agentos machines list
```

### Deploy to GCP

```bash
# Deploy to GCP Compute Engine
agentos deploy gcp --zone us-central1-a --machine-type n1-standard-1
```

### Run Agents Remotely

```bash
# Run on a specific machine
agentos agent run agents/examples/hello_agent.py --machine docker-dev-kernel-abc123

# Run on all machines
agentos agent run agents/examples/health_check.py --all

# List running agents
agentos agent list
```

### Token Management

```bash
# Create machine token (for new kernels)
agentos tokens create machine --name production-server

# Create agent token
agentos tokens create agent --target-machine docker-dev-kernel-abc123

# List tokens
agentos tokens list
```

## Fleet Management

### Start Relay Server

```bash
cd relay
pip install -r requirements.txt
python relay_server.py
```

The relay server runs on:
- WebSocket: `ws://localhost:8765` (kernel connections)
- REST API: `http://localhost:8766` (CLI management)

### Connect Kernel to Relay

```bash
# Using Python tunnel client
python scripts/tunnel_client.py --relay ws://relay.example.com:8765 --token <machine_token>
```

### Fleet Status

```bash
$ agentos status

 AgentOS Fleet Status
┏━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Machine ID            ┃ Provider   ┃ Status      ┃ Agents      ┃
┡━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ docker-dev-abc123     │ docker     │ connected   │ 2           │
│ aws-i-0def456-us-e1   │ aws        │ connected   │ 0           │
└───────────────────────┴────────────┴─────────────┴─────────────┘
```

## Next Steps

- [Syscall Reference](syscalls.md) - All available syscalls
- [Architecture](architecture.md) - How AgentOS works
- [CLI Reference](../cli/README.md) - Full CLI documentation
- [Examples](../agents/examples/README.md) - Demo agents
