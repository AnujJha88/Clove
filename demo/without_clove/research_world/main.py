#!/usr/bin/env python3
"""
Research World - Main Entry Point

Run long-running multi-agent research tasks.

Usage:
    python main.py "Your research question here"
    python main.py "What are the best treatments for Type 2 Diabetes?" --hours 2
    python main.py --resume  # Resume from last checkpoint
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator import run_research, ResearchOrchestrator
from checkpoint import CheckpointManager
from pdf_processor import create_sample_data
import config


def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ██████╗ ███████╗███████╗███████╗ █████╗ ██████╗  ██████╗  ║
║   ██╔══██╗██╔════╝██╔════╝██╔════╝██╔══██╗██╔══██╗██╔════╝  ║
║   ██████╔╝█████╗  ███████╗█████╗  ███████║██████╔╝██║       ║
║   ██╔══██╗██╔══╝  ╚════██║██╔══╝  ██╔══██║██╔══██╗██║       ║
║   ██║  ██║███████╗███████║███████╗██║  ██║██║  ██║╚██████╗  ║
║   ╚═╝  ╚═╝╚══════╝╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ║
║                                                              ║
║   ██╗    ██╗ ██████╗ ██████╗ ██╗     ██████╗                ║
║   ██║    ██║██╔═══██╗██╔══██╗██║     ██╔══██╗               ║
║   ██║ █╗ ██║██║   ██║██████╔╝██║     ██║  ██║               ║
║   ██║███╗██║██║   ██║██╔══██╗██║     ██║  ██║               ║
║   ╚███╔███╔╝╚██████╔╝██║  ██║███████╗██████╔╝               ║
║    ╚══╝╚══╝  ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═════╝                ║
║                                                              ║
║   Multi-Agent Research System                                ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)


def list_checkpoints():
    """List available checkpoints."""
    cm = CheckpointManager()
    checkpoints = cm.list_checkpoints()

    if not checkpoints:
        print("No checkpoints found.")
        return

    print("\nAvailable Checkpoints:")
    print("-" * 60)
    for cp in checkpoints:
        print(f"  ID: {cp['checkpoint_id']}")
        print(f"  Task: {cp['research_task']}")
        print(f"  Status: {cp['status']}")
        print(f"  Time: {cp['timestamp']}")
        print(f"  Findings: {cp['num_findings']}")
        print("-" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Research World - Multi-Agent Research System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py "What are the best treatments for Type 2 Diabetes?"
  python main.py "Compare SGLT2 inhibitors vs GLP-1 agonists" --hours 2
  python main.py --list-checkpoints
  python main.py --resume
        """
    )

    parser.add_argument(
        "task",
        nargs="?",
        help="Research question or task"
    )

    parser.add_argument(
        "--hours",
        type=float,
        default=4,
        help="Maximum hours to run (default: 4)"
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint"
    )

    parser.add_argument(
        "--list-checkpoints",
        action="store_true",
        help="List available checkpoints"
    )

    parser.add_argument(
        "--create-samples",
        action="store_true",
        help="Create sample research documents"
    )

    args = parser.parse_args()

    print_banner()

    # Handle special commands
    if args.list_checkpoints:
        list_checkpoints()
        return

    if args.create_samples:
        create_sample_data()
        print("Sample documents created in data/pdfs/")
        return

    # Check for API keys
    if not config.API_KEYS:
        print("ERROR: No API keys configured!")
        print()
        print("Set your API keys in one of these ways:")
        print()
        print("1. Environment variables:")
        print("   export GOOGLE_API_KEY='your_key'")
        print("   # Or for multiple keys:")
        print("   export GOOGLE_API_KEY_1='key1'")
        print("   export GOOGLE_API_KEY_2='key2'")
        print("   # ... up to GOOGLE_API_KEY_10")
        print()
        print("2. Create .env file in research_world/:")
        print("   GOOGLE_API_KEY_1=your_key_1")
        print("   GOOGLE_API_KEY_2=your_key_2")
        print()
        sys.exit(1)

    print(f"API Keys available: {len(config.API_KEYS)}")

    # Handle resume
    if args.resume:
        cm = CheckpointManager()
        checkpoint = cm.load_checkpoint()
        if not checkpoint:
            print("No checkpoint found to resume from.")
            sys.exit(1)

        print(f"Resuming from: {checkpoint.checkpoint_id}")
        print(f"Task: {checkpoint.research_task}")
        # TODO: Implement full resume logic
        task = checkpoint.research_task
    else:
        if not args.task:
            print("ERROR: Please provide a research task")
            print("Usage: python main.py \"Your research question\"")
            sys.exit(1)
        task = args.task

    # Run research
    print(f"\nStarting research: {task}")
    print(f"Max duration: {args.hours} hours")
    print()

    try:
        report_path = asyncio.run(run_research(
            task=task,
            max_hours=args.hours,
        ))

        print(f"\n✓ Research complete!")
        print(f"✓ Report saved to: {report_path}")

    except KeyboardInterrupt:
        print("\n\nResearch interrupted. Progress saved to checkpoint.")
        sys.exit(0)

    except Exception as e:
        print(f"\n✗ Research failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
