# CLOVE Demos

This directory contains demonstration applications showcasing CLOVE's capabilities.

## Quick Start

1. **Build and run the kernel:**
   ```bash
   # From repo root
   mkdir -p build && cd build
   cmake .. && make -j$(nproc)
   ./clove_kernel
   ```

2. **Run a demo:**
   ```bash
   cd demos/01-quickstart
   python main.py
   ```

## Demo Index

| Demo | Description | Key Features |
|------|-------------|--------------|
| [01-quickstart](./01-quickstart/) | Basic kernel interaction | Connection, commands, state store |
| [02-ml-pipeline](./02-ml-pipeline/) | ML training pipeline | Resource limits, stage orchestration, retry policies |
| [03-incident-response](./03-incident-response/) | Security monitoring | Multi-agent IPC, permissions, audit logging |
| [04-agentic-research](./04-agentic-research/) | LLM research agents | Agent coordination, fair scheduling, auto-recovery |
| [baseline](./baseline/) | Without CLOVE | Comparison baseline (no isolation) |

## Learning Path

**Recommended order:**

```
01-quickstart     → Understand basic kernel operations
       ↓
02-ml-pipeline    → Learn resource limits and stage orchestration
       ↓
03-incident-response → Explore multi-agent IPC and permissions
       ↓
04-agentic-research  → See LLM agent coordination
       ↓
baseline          → Compare with non-CLOVE implementation
```

## Directory Structure

```
demos/
├── README.md              # This file
├── shared/                # Shared utilities
│   ├── utils.py           # Common helpers
│   └── base_agent.py      # Base agent class
│
├── 01-quickstart/         # Simple intro demo
│   ├── main.py
│   └── README.md
│
├── 02-ml-pipeline/        # ML pipeline demo
│   ├── main.py            # Orchestrator
│   ├── benchmark_*.py     # Benchmark variants
│   ├── config/            # YAML configs
│   └── stages/            # Pipeline stages
│
├── 03-incident-response/  # Security demo
│   ├── main.py            # Single-run mode
│   ├── main_continuous.py # Continuous mode
│   ├── dashboard.py       # Rich TUI
│   ├── config/            # JSON configs
│   └── agents/            # Agent scripts
│
├── 04-agentic-research/   # LLM agents demo
│   ├── main.py            # Mission control
│   ├── dashboard/         # TUI dashboard
│   ├── config/            # Limits config
│   └── agents/            # Scout, critic, etc.
│
└── baseline/              # No-CLOVE comparison
    └── research_world/    # Standalone implementation
```

## CLOVE Features by Demo

| Feature | 01 | 02 | 03 | 04 |
|---------|----|----|----|----|
| Kernel connection | ✓ | ✓ | ✓ | ✓ |
| Command execution | ✓ | ✓ | ✓ | ✓ |
| Agent spawning | - | ✓ | ✓ | ✓ |
| Resource limits | - | ✓ | ✓ | ✓ |
| IPC messaging | - | ✓ | ✓ | ✓ |
| State store | ✓ | ✓ | ✓ | ✓ |
| Permission boundaries | - | - | ✓ | - |
| Audit logging | - | ✓ | ✓ | ✓ |
| Restart policies | - | ✓ | ✓ | ✓ |
| Real-time dashboard | - | - | ✓ | ✓ |
| LLM integration | - | - | - | ✓ |

## Shared Utilities

The `shared/` directory provides common utilities:

```python
from shared import (
    ensure_sdk_on_path,  # Add SDK to sys.path
    load_config,         # Load YAML/JSON configs
    write_json,          # Write JSON files
    log,                 # Structured logging
    normalize_limits,    # Convert limits to kernel format
    wait_for_message,    # Wait for IPC messages
    BaseAgent,           # Base class for agents
)
```

## Running Benchmarks

The `02-ml-pipeline` demo includes benchmarking:

```bash
cd demos/02-ml-pipeline

# Run single benchmark
python benchmark_orchestrator.py

# Run standalone comparison (no CLOVE)
python benchmark_standalone.py
```

## Artifacts and Logs

Each demo generates artifacts in gitignored directories:
- `artifacts/` - Output files, models, reports
- `logs/` - Execution logs
- `results/` - Benchmark results

To clean:
```bash
rm -rf demos/*/artifacts demos/*/logs demos/*/results
```

## Troubleshooting

**Kernel not running:**
```
ERROR: Failed to connect to kernel. Is clove_kernel running?
```
Start the kernel first: `./build/clove_kernel`

**Permission denied on artifacts:**
Some artifacts may be created by sandboxed processes (root-owned):
```bash
sudo rm -rf demos/*/artifacts demos/*/logs
```

**SDK not found:**
Ensure you're running from the demos directory or the SDK path is correct.
