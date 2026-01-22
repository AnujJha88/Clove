#!/usr/bin/env python3
"""
Framework Benchmark Runner

Compares Clove against LangGraph (both using Gemini).

Usage:
    python benchmarks/run_benchmark.py [--quick] [--frameworks clove,langgraph]
"""

import argparse
import sys
import os
from datetime import datetime
from typing import Dict, List

# Load .env from project root
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

# Add paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'agents', 'python_sdk'))

from config import get_default_config, get_quick_config, BenchmarkConfig, Framework
from runners.clove_runner import CloveRunner
from runners.langgraph_runner import LangGraphRunner
from report import generate_comparison_report


RUNNERS = {
    Framework.CLOVE: CloveRunner,
    Framework.LANGGRAPH: LangGraphRunner,
}


def run_benchmarks(config: BenchmarkConfig, frameworks: List[Framework]) -> Dict:
    """Run benchmarks for specified frameworks"""
    results = {}

    for i, framework in enumerate(frameworks, 1):
        print(f"\n{'='*70}")
        print(f"  PHASE {i}: {framework.value.upper()} BENCHMARK")
        print(f"{'='*70}")

        runner_class = RUNNERS.get(framework)
        if not runner_class:
            print(f"WARNING: No runner for {framework.value}, skipping")
            continue

        # Check prerequisites
        if framework == Framework.CLOVE and not os.path.exists('/tmp/clove.sock'):
            print("WARNING: Clove kernel not running (/tmp/clove.sock not found)")
            print("Start kernel with: ./build/clove_kernel")
            print("Skipping Clove benchmark...\n")
            continue

        if framework == Framework.LANGGRAPH:
            try:
                import langgraph
            except ImportError:
                print("WARNING: LangGraph not installed")
                print("Install with: pip install langgraph langchain-google-genai")
                print("Skipping LangGraph benchmark...\n")
                continue

            # Check for API key
            api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
            if not api_key:
                print("WARNING: No API key found (GOOGLE_API_KEY or GEMINI_API_KEY)")
                print("LangGraph benchmark uses Gemini and requires an API key")
                print("Skipping LangGraph benchmark...\n")
                continue

        runner = runner_class(config)
        results[framework.value] = runner.run()

        # Save results
        filepath = results[framework.value].save(config.output_dir)
        print(f"{framework.value.capitalize()} results saved to: {filepath}")

    return results


def print_summary(results: Dict):
    """Print comparison summary"""
    print("\n" + "=" * 70)
    print("  CLOVE vs LANGGRAPH COMPARISON")
    print("=" * 70)

    if len(results) < 2:
        print("\nNeed at least 2 frameworks for comparison")
        for name, res in results.items():
            print(f"\n{name.upper()} Results:")
            for task, stats in res.statistics.items():
                print(f"  {task}: {stats['mean_ms']:.2f}ms (mean)")
        return

    # Get framework names
    frameworks = list(results.keys())

    # Find common tasks
    all_tasks = set()
    for res in results.values():
        all_tasks.update(res.statistics.keys())

    # Print header
    header = f"{'Task':<25}"
    for fw in frameworks:
        header += f" {fw:<12}"
    header += " Winner"
    print(f"\n{header}")
    print("-" * (25 + 13 * len(frameworks) + 10))

    # Print each task
    totals = {fw: 0 for fw in frameworks}
    wins = {fw: 0 for fw in frameworks}

    for task in sorted(all_tasks):
        row = f"{task:<25}"
        task_times = {}

        for fw in frameworks:
            if fw in results and task in results[fw].statistics:
                mean = results[fw].statistics[task]["mean_ms"]
                task_times[fw] = mean
                totals[fw] += mean
                row += f" {mean:<12.2f}"
            else:
                row += f" {'N/A':<12}"

        # Determine winner (lowest time)
        if task_times:
            winner = min(task_times, key=task_times.get)
            wins[winner] += 1
            row += f" {winner}"
        else:
            row += " -"

        print(row)

    # Print totals
    print("-" * (25 + 13 * len(frameworks) + 10))
    total_row = f"{'TOTAL':<25}"
    for fw in frameworks:
        total_row += f" {totals[fw]:<12.2f}"
    overall_winner = min(totals, key=totals.get) if totals else "-"
    total_row += f" {overall_winner}"
    print(total_row)

    # Print win counts
    print(f"\n{'Task Wins:':<25}", end="")
    for fw in frameworks:
        print(f" {wins[fw]:<12}", end="")
    print()

    # Calculate performance comparison
    if "clove" in results and "langgraph" in results:
        print(f"\nClove vs LangGraph Performance:")
        common = set(results["clove"].statistics.keys()) & set(results["langgraph"].statistics.keys())
        for task in sorted(common):
            clove_time = results["clove"].statistics[task]["mean_ms"]
            langgraph_time = results["langgraph"].statistics[task]["mean_ms"]
            if langgraph_time > 0:
                diff = ((clove_time - langgraph_time) / langgraph_time) * 100
                faster = "faster" if diff < 0 else "slower"
                print(f"  {task}: Clove is {abs(diff):.1f}% {faster}")


def main():
    parser = argparse.ArgumentParser(description="Run Clove vs LangGraph benchmarks")
    parser.add_argument("--quick", action="store_true", help="Run quick benchmark (fewer iterations)")
    parser.add_argument("--frameworks", type=str, default="clove,langgraph",
                        help="Comma-separated list of frameworks (clove,langgraph)")
    parser.add_argument("--clove-only", action="store_true", help="Only run Clove benchmark")
    parser.add_argument("--langgraph-only", action="store_true", help="Only run LangGraph benchmark")
    parser.add_argument("--output", type=str, default="benchmarks/results", help="Output directory")
    parser.add_argument("--report", action="store_true", help="Generate HTML report")

    args = parser.parse_args()

    # Get configuration
    if args.quick:
        config = get_quick_config()
        print("Running QUICK benchmark (reduced iterations)")
    else:
        config = get_default_config()
        print("Running FULL benchmark")

    config.output_dir = args.output
    os.makedirs(config.output_dir, exist_ok=True)

    # Determine frameworks to run
    if args.clove_only:
        frameworks = [Framework.CLOVE]
    elif args.langgraph_only:
        frameworks = [Framework.LANGGRAPH]
    else:
        framework_names = [f.strip().lower() for f in args.frameworks.split(",")]
        frameworks = []
        for name in framework_names:
            try:
                frameworks.append(Framework(name))
            except ValueError:
                print(f"WARNING: Unknown framework '{name}', skipping")

    if not frameworks:
        print("ERROR: No valid frameworks specified")
        return 1

    print(f"Frameworks to benchmark: {', '.join(f.value for f in frameworks)}")

    # Run benchmarks
    results = run_benchmarks(config, frameworks)

    if not results:
        print("\nNo benchmark results collected")
        return 1

    # Print summary
    print_summary(results)

    # Generate HTML report if requested
    if args.report and len(results) >= 2:
        # Convert to format expected by report generator
        report_results = {}
        framework_list = list(results.keys())
        if len(framework_list) >= 2:
            report_results["native"] = results[framework_list[1]]  # LangGraph as baseline
            report_results["clove"] = results[framework_list[0]]   # Clove
        report_path = generate_comparison_report(report_results, config.output_dir)
        print(f"\nHTML report generated: {report_path}")

    print("\nBenchmark complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
