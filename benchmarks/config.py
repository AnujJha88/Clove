"""
Benchmark Configuration

Defines benchmark tasks for comparing agent frameworks:
- Clove
- LangChain
- CrewAI
- AutoGen
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class TaskCategory(Enum):
    """Categories of benchmark tasks"""
    AGENT_SPAWN = "agent_spawn"           # Agent creation/initialization
    LLM_CALL = "llm_call"                 # LLM inference latency
    TOOL_EXECUTION = "tool_execution"     # Tool/function calling
    MULTI_AGENT = "multi_agent"           # Multi-agent coordination
    MEMORY = "memory"                     # State/memory operations
    FILE_IO = "file_io"                   # File operations through framework
    END_TO_END = "end_to_end"             # Complete agent task


class Framework(Enum):
    """Supported frameworks for comparison"""
    CLOVE = "clove"
    LANGGRAPH = "langgraph"


@dataclass
class TaskConfig:
    """Configuration for a single benchmark task"""
    name: str
    category: TaskCategory
    description: str
    iterations: int = 10
    warmup_iterations: int = 2
    timeout_seconds: float = 60.0
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkConfig:
    """Overall benchmark configuration"""
    name: str
    frameworks: List[Framework] = field(default_factory=lambda: [Framework.CLOVE, Framework.LANGCHAIN])
    tasks: List[TaskConfig] = field(default_factory=list)
    output_dir: str = "benchmarks/results"
    collect_system_metrics: bool = True
    metrics_interval: float = 0.5  # seconds


# =============================================================================
# Benchmark Task Definitions
# =============================================================================

# Agent spawn/initialization tasks
AGENT_SPAWN_TASKS = [
    TaskConfig(
        name="single_agent_spawn",
        category=TaskCategory.AGENT_SPAWN,
        description="Create and initialize a single agent",
        iterations=20,
        warmup_iterations=3,
        params={}
    ),
    TaskConfig(
        name="agent_with_tools",
        category=TaskCategory.AGENT_SPAWN,
        description="Create agent with 5 tools attached",
        iterations=20,
        warmup_iterations=3,
        params={"tool_count": 5}
    ),
    TaskConfig(
        name="multi_agent_spawn",
        category=TaskCategory.AGENT_SPAWN,
        description="Create 5 agents concurrently",
        iterations=10,
        warmup_iterations=2,
        params={"agent_count": 5}
    ),
]

# LLM call tasks
LLM_CALL_TASKS = [
    TaskConfig(
        name="simple_completion",
        category=TaskCategory.LLM_CALL,
        description="Simple LLM completion (short prompt)",
        iterations=10,
        warmup_iterations=2,
        params={
            "prompt": "What is 2+2? Answer with just the number.",
            "max_tokens": 10
        }
    ),
    TaskConfig(
        name="structured_output",
        category=TaskCategory.LLM_CALL,
        description="LLM call with structured JSON output",
        iterations=10,
        warmup_iterations=2,
        params={
            "prompt": "Return a JSON object with keys 'name' and 'age' for a fictional person.",
            "max_tokens": 50
        }
    ),
]

# Tool execution tasks
TOOL_EXECUTION_TASKS = [
    TaskConfig(
        name="single_tool_call",
        category=TaskCategory.TOOL_EXECUTION,
        description="Execute a single tool/function",
        iterations=20,
        warmup_iterations=3,
        params={"tool": "calculator", "input": "add 5 and 3"}
    ),
    TaskConfig(
        name="chained_tools",
        category=TaskCategory.TOOL_EXECUTION,
        description="Execute 3 tools in sequence",
        iterations=10,
        warmup_iterations=2,
        params={"tool_chain": ["search", "summarize", "format"]}
    ),
]

# Multi-agent coordination tasks
MULTI_AGENT_TASKS = [
    TaskConfig(
        name="agent_message_pass",
        category=TaskCategory.MULTI_AGENT,
        description="Pass message between 2 agents",
        iterations=20,
        warmup_iterations=3,
        params={"message_size": 256}
    ),
    TaskConfig(
        name="agent_collaboration",
        category=TaskCategory.MULTI_AGENT,
        description="3 agents collaborating on task",
        iterations=5,
        warmup_iterations=1,
        params={"agent_count": 3, "task": "write a haiku"}
    ),
]

# Memory/state tasks
MEMORY_TASKS = [
    TaskConfig(
        name="memory_store",
        category=TaskCategory.MEMORY,
        description="Store 100 key-value pairs",
        iterations=20,
        warmup_iterations=3,
        params={"key_count": 100}
    ),
    TaskConfig(
        name="memory_retrieve",
        category=TaskCategory.MEMORY,
        description="Retrieve from memory with context",
        iterations=20,
        warmup_iterations=3,
        params={"query": "previous conversation about weather"}
    ),
]

# End-to-end tasks
END_TO_END_TASKS = [
    TaskConfig(
        name="simple_qa",
        category=TaskCategory.END_TO_END,
        description="Simple question-answer task",
        iterations=5,
        warmup_iterations=1,
        params={"question": "What is the capital of France?"}
    ),
    TaskConfig(
        name="research_task",
        category=TaskCategory.END_TO_END,
        description="Research task with tool use",
        iterations=3,
        warmup_iterations=1,
        params={"topic": "quantum computing basics"}
    ),
]


def get_default_config() -> BenchmarkConfig:
    """Get default benchmark configuration (full suite)"""
    return BenchmarkConfig(
        name="framework_comparison",
        frameworks=[Framework.CLOVE, Framework.LANGGRAPH],
        tasks=(
            AGENT_SPAWN_TASKS +
            LLM_CALL_TASKS +
            TOOL_EXECUTION_TASKS +
            MULTI_AGENT_TASKS +
            MEMORY_TASKS +
            END_TO_END_TASKS
        ),
        output_dir="benchmarks/results"
    )


def get_quick_config() -> BenchmarkConfig:
    """Get quick benchmark configuration (minimal tasks)"""
    return BenchmarkConfig(
        name="quick_comparison",
        frameworks=[Framework.CLOVE, Framework.LANGGRAPH],
        tasks=[
            TaskConfig(
                name="agent_spawn_quick",
                category=TaskCategory.AGENT_SPAWN,
                description="Quick agent spawn test",
                iterations=5,
                warmup_iterations=1,
                params={}
            ),
            TaskConfig(
                name="llm_call_quick",
                category=TaskCategory.LLM_CALL,
                description="Quick LLM call test",
                iterations=3,
                warmup_iterations=1,
                params={
                    "prompt": "Say hello.",
                    "max_tokens": 10
                }
            ),
            TaskConfig(
                name="tool_call_quick",
                category=TaskCategory.TOOL_EXECUTION,
                description="Quick tool execution test",
                iterations=5,
                warmup_iterations=1,
                params={"tool": "echo", "input": "test"}
            ),
        ],
        output_dir="benchmarks/results",
        collect_system_metrics=False
    )


def get_llm_only_config() -> BenchmarkConfig:
    """Get LLM-focused benchmark configuration"""
    return BenchmarkConfig(
        name="llm_comparison",
        frameworks=[Framework.CLOVE, Framework.LANGGRAPH],
        tasks=LLM_CALL_TASKS,
        output_dir="benchmarks/results"
    )
