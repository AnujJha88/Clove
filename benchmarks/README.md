# Clove vs LangGraph Benchmark

Compare Clove against LangGraph - both using Gemini as the LLM backend.

## Quick Start

```bash
# Make sure Clove kernel is running
./build/clove_kernel &

# Run the benchmark
python3 benchmarks/run_benchmark.py --quick

# Or run with HTML report
python3 benchmarks/run_benchmark.py --quick --report
```

## Prerequisites

- Clove kernel running (`./build/clove_kernel`)
- API key in `.env` file (GOOGLE_API_KEY or GEMINI_API_KEY)
- LangGraph installed: `pip install langgraph langchain-google-genai`

## Command Line Options

| Option | Description |
|--------|-------------|
| `--quick` | Run quick benchmark with fewer iterations |
| `--clove-only` | Only benchmark Clove |
| `--langgraph-only` | Only benchmark LangGraph |
| `--output DIR` | Output directory (default: `benchmarks/results`) |
| `--report` | Generate HTML comparison report |

## Sample Results

```
======================================================================
  CLOVE vs LANGGRAPH COMPARISON
======================================================================

Task                      clove        langgraph    Winner
-------------------------------------------------------------
agent_spawn_quick         0.00         110.62       clove
llm_call_quick            1056.66      4361.91      clove
tool_call_quick           0.04         34981.90     clove
-------------------------------------------------------------
TOTAL                     1056.70      39454.43     clove

Task Wins:                3            0

Clove vs LangGraph Performance:
  agent_spawn_quick: Clove is 100.0% faster
  llm_call_quick: Clove is 75.8% faster
  tool_call_quick: Clove is 100.0% faster
```

## Why Clove is Faster

| Operation | Clove | LangGraph |
|-----------|-------|-----------|
| Agent Spawn | Direct kernel IPC (~0ms) | Python object creation + LLM init (~110ms) |
| LLM Call | Direct API call via kernel | Multiple abstraction layers |
| Tool Execution | Kernel syscall (~0ms) | Full ReAct reasoning loop (~35s) |

### Key Differences

1. **Architecture**: Clove uses Unix sockets + msgpack, LangGraph uses Python abstractions
2. **Tool Execution**: Clove executes tools as kernel syscalls, LangGraph uses LLM reasoning
3. **Overhead**: Clove has minimal framework overhead, LangGraph has multiple layers

## Benchmark Categories

### AGENT_SPAWN
Measures agent creation and initialization time.

### LLM_CALL
Direct LLM inference latency (same Gemini model for both).

### TOOL_EXECUTION
Tool/function execution:
- **Clove**: Direct kernel syscall (echo)
- **LangGraph**: Full ReAct agent reasoning loop

## Architecture

```
benchmarks/
├── config.py              # Task definitions
├── metrics.py             # Metrics collection
├── report.py              # HTML report generator
├── run_benchmark.py       # Main entry point
└── runners/
    ├── clove_runner.py    # Clove kernel execution
    └── langgraph_runner.py # LangGraph execution
```

## Adding More Benchmarks

Edit `config.py` to add new task configurations:

```python
TaskConfig(
    name="my_new_task",
    category=TaskCategory.LLM_CALL,
    description="Description of task",
    iterations=10,
    warmup_iterations=2,
    params={"prompt": "...", "max_tokens": 100}
)
```
