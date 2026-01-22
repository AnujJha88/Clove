"""
LangGraph Runner

Executes benchmark tasks using LangGraph framework with Gemini.
"""

import sys
import os
from datetime import datetime
from typing import Optional, Annotated
from typing_extensions import TypedDict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env from project root
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env'))

from config import BenchmarkConfig, TaskCategory, TaskConfig
from metrics import BenchmarkResults, MetricsCollector, TaskTimer


class LangGraphRunner:
    """Runs benchmarks using LangGraph framework with Gemini"""

    def __init__(self, config: BenchmarkConfig):
        self.config = config
        self.results = BenchmarkResults(
            benchmark_name=config.name,
            start_time=datetime.now(),
            runner_type="langgraph"
        )
        self.metrics_collector = MetricsCollector(interval=config.metrics_interval)

        # LangGraph components (initialized on connect)
        self.llm = None
        self.graph = None
        self.tools = []
        self.memory = {}

    def connect(self) -> bool:
        """Initialize LangGraph components with Gemini"""
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langgraph.graph import StateGraph, END
            from langgraph.prebuilt import ToolNode, tools_condition
            from langchain_core.tools import tool

            # Get API key from environment
            api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
            if not api_key:
                print("ERROR: No API key found (GOOGLE_API_KEY or GEMINI_API_KEY)")
                return False

            # Initialize Gemini LLM
            model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-exp")
            self.llm = ChatGoogleGenerativeAI(
                model=model_name,
                temperature=0,
                google_api_key=api_key
            )

            # Create tools
            @tool
            def calculator(expression: str) -> str:
                """Calculate a math expression. Input should be a valid math expression."""
                try:
                    return str(eval(expression))
                except:
                    return "Error: Invalid expression"

            @tool
            def echo(message: str) -> str:
                """Echo back the input message."""
                return message

            self.tools = [calculator, echo]

            # Bind tools to LLM
            self.llm_with_tools = self.llm.bind_tools(self.tools)

            # Create the graph
            self._create_graph()

            return True
        except ImportError as e:
            print(f"ERROR: LangGraph not installed: {e}")
            print("Install with: pip install langgraph langchain-google-genai")
            return False
        except Exception as e:
            print(f"ERROR: Could not initialize LangGraph with Gemini: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _create_graph(self):
        """Create the LangGraph agent graph"""
        from langgraph.graph import StateGraph, END
        from langgraph.prebuilt import ToolNode, tools_condition
        from langchain_core.messages import HumanMessage, AIMessage

        # Define state
        class AgentState(TypedDict):
            messages: list

        # Define nodes
        def call_model(state: AgentState):
            messages = state["messages"]
            response = self.llm_with_tools.invoke(messages)
            return {"messages": [response]}

        # Create tool node
        tool_node = ToolNode(self.tools)

        # Build graph
        workflow = StateGraph(AgentState)
        workflow.add_node("agent", call_model)
        workflow.add_node("tools", tool_node)

        workflow.set_entry_point("agent")
        workflow.add_conditional_edges(
            "agent",
            tools_condition,
        )
        workflow.add_edge("tools", "agent")

        self.graph = workflow.compile()

    def disconnect(self):
        """Cleanup LangGraph components"""
        self.llm = None
        self.graph = None
        self.tools = []
        self.memory = {}

    def run(self) -> BenchmarkResults:
        """Run all configured benchmark tasks"""
        print(f"\n{'='*60}")
        print(f"  LANGGRAPH + GEMINI BENCHMARK: {self.config.name}")
        print(f"{'='*60}\n")

        if not self.connect():
            return self.results

        if self.config.collect_system_metrics:
            self.metrics_collector.start_collection(use_clove=False)

        try:
            for task_config in self.config.tasks:
                self._run_task(task_config)
        finally:
            if self.config.collect_system_metrics:
                snapshots = self.metrics_collector.stop_collection()
                self.results.system_snapshots = snapshots

            self.disconnect()

        self.results.end_time = datetime.now()
        self.results.compute_statistics()

        return self.results

    def _run_task(self, task_config: TaskConfig):
        """Run a single task with all iterations"""
        print(f"Running: {task_config.name} ({task_config.description})")
        print(f"  Category: {task_config.category.value}")
        print(f"  Iterations: {task_config.warmup_iterations} warmup + {task_config.iterations} measured")

        # Warmup iterations
        for i in range(task_config.warmup_iterations):
            self._execute_task(task_config, iteration=-(task_config.warmup_iterations - i))

        # Measured iterations
        for i in range(task_config.iterations):
            with TaskTimer(task_config.name, i) as timer:
                result = self._execute_task(task_config, iteration=i)
                timer.extra = result if isinstance(result, dict) else {}

            self.results.add_task_metric(timer.to_metric())

            if (i + 1) % 5 == 0 or i == task_config.iterations - 1:
                print(f"  Progress: {i + 1}/{task_config.iterations}")

        print(f"  Done\n")

    def _execute_task(self, task_config: TaskConfig, iteration: int) -> Optional[dict]:
        """Execute a single task iteration"""
        params = task_config.params

        if task_config.category == TaskCategory.AGENT_SPAWN:
            return self._spawn_agent(params)

        elif task_config.category == TaskCategory.LLM_CALL:
            return self._llm_call(params)

        elif task_config.category == TaskCategory.TOOL_EXECUTION:
            return self._tool_execution(params)

        elif task_config.category == TaskCategory.MULTI_AGENT:
            return self._multi_agent(params)

        elif task_config.category == TaskCategory.MEMORY:
            return self._memory_ops(params)

        elif task_config.category == TaskCategory.END_TO_END:
            return self._end_to_end(params)

        return {"success": True}

    def _spawn_agent(self, params: dict) -> dict:
        """Spawn a new LangGraph agent"""
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langgraph.graph import StateGraph, END
            from langgraph.prebuilt import ToolNode, tools_condition
            from langchain_core.tools import tool

            # Create tools based on params
            tool_count = params.get("tool_count", 0)
            tools = []
            for i in range(tool_count):
                @tool
                def dynamic_tool(x: str) -> str:
                    f"""Tool number {i}. Returns the input."""
                    return x
                dynamic_tool.name = f"tool_{i}"
                tools.append(dynamic_tool)

            # Get API key
            api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
            model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-exp")

            # Create new Gemini LLM instance
            llm = ChatGoogleGenerativeAI(
                model=model_name,
                temperature=0,
                google_api_key=api_key
            )

            if tools:
                llm_with_tools = llm.bind_tools(tools)

                class AgentState(TypedDict):
                    messages: list

                def call_model(state):
                    return {"messages": [llm_with_tools.invoke(state["messages"])]}

                tool_node = ToolNode(tools)
                workflow = StateGraph(AgentState)
                workflow.add_node("agent", call_model)
                workflow.add_node("tools", tool_node)
                workflow.set_entry_point("agent")
                workflow.add_conditional_edges("agent", tools_condition)
                workflow.add_edge("tools", "agent")
                graph = workflow.compile()

            return {"success": True, "tool_count": tool_count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _llm_call(self, params: dict) -> dict:
        """Make an LLM call to Gemini"""
        try:
            from langchain_core.messages import HumanMessage

            prompt = params.get("prompt", "Hello")

            response = self.llm.invoke([HumanMessage(content=prompt)])

            return {
                "success": True,
                "response_length": len(response.content) if hasattr(response, 'content') else 0
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_execution(self, params: dict) -> dict:
        """Execute a tool through LangGraph"""
        try:
            from langchain_core.messages import HumanMessage

            tool_name = params.get("tool", "echo")
            tool_input = params.get("input", "test")

            # Run through the graph
            result = self.graph.invoke({
                "messages": [HumanMessage(content=f"Use the {tool_name} tool with input: {tool_input}")]
            })

            last_message = result["messages"][-1]
            output = last_message.content if hasattr(last_message, 'content') else str(last_message)

            return {"success": True, "result": str(output)[:100]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _multi_agent(self, params: dict) -> dict:
        """Multi-agent coordination through LangGraph"""
        try:
            from langchain_core.messages import HumanMessage

            agent_count = params.get("agent_count", 2)
            message = params.get("task", "hello")

            # Sequential agent invocations
            for i in range(agent_count):
                result = self.graph.invoke({
                    "messages": [HumanMessage(content=message)]
                })
                last_msg = result["messages"][-1]
                message = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)

            return {"success": True, "agent_count": agent_count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _memory_ops(self, params: dict) -> dict:
        """Memory/state operations"""
        try:
            key_count = params.get("key_count", 10)

            # Store items in memory dict
            for i in range(key_count):
                self.memory[f"key_{i}"] = f"value_{i}"

            # Retrieve items
            for i in range(key_count):
                _ = self.memory.get(f"key_{i}")

            return {"success": True, "stored": key_count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _end_to_end(self, params: dict) -> dict:
        """End-to-end agent task through LangGraph"""
        try:
            from langchain_core.messages import HumanMessage

            question = params.get("question", params.get("topic", "Hello"))

            result = self.graph.invoke({
                "messages": [HumanMessage(content=question)]
            })

            last_message = result["messages"][-1]
            output = last_message.content if hasattr(last_message, 'content') else str(last_message)

            return {
                "success": True,
                "output_length": len(str(output))
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


def main():
    """Run LangGraph benchmark with Gemini"""
    from config import get_quick_config

    config = get_quick_config()
    runner = LangGraphRunner(config)
    results = runner.run()

    print("\n" + "=" * 60)
    print("  RESULTS SUMMARY")
    print("=" * 60)

    for task_name, stats in results.statistics.items():
        print(f"\n{task_name}:")
        print(f"  Mean: {stats['mean_ms']:.2f}ms")
        print(f"  Median: {stats['median_ms']:.2f}ms")
        print(f"  P95: {stats['p95_ms']:.2f}ms")

    filepath = results.save(config.output_dir)
    print(f"\nResults saved to: {filepath}")


if __name__ == "__main__":
    main()
