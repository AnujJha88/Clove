#!/usr/bin/env python3
"""CLOVE Quickstart Demo.

A simple demo showing basic CLOVE kernel interaction:
- Connect to kernel
- Query kernel info
- Execute a command
- Spawn a simple agent
- Send/receive IPC messages

Run with: python main.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Add shared utils and SDK to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared import ensure_sdk_on_path, log

ensure_sdk_on_path()

from clove_sdk import CloveClient


def main():
    log("quickstart", "INFO", "Starting CLOVE Quickstart Demo")

    # Connect to kernel
    client = CloveClient()
    if not client.connect():
        log("quickstart", "ERROR", "Failed to connect to kernel. Is clove_kernel running?")
        sys.exit(1)

    try:
        # 1. Query kernel info
        log("quickstart", "INFO", "Querying kernel info...")
        info = client.hello()
        print(f"\n{'='*50}")
        print(f"Kernel Version: {info.version}")
        print(f"Agent ID: {info.agent_id}")
        print(f"Capabilities: {', '.join(info.capabilities)}")
        print(f"Uptime: {info.uptime_seconds:.1f}s")
        print(f"{'='*50}\n")

        # 2. Execute a simple command
        log("quickstart", "INFO", "Executing command: uname -a")
        result = client.exec("uname -a")
        if result.success:
            print(f"Command output: {result.stdout.strip()}")
        else:
            print(f"Command failed: {result.stderr}")

        # 3. Echo test
        log("quickstart", "INFO", "Testing NOOP/echo...")
        echo_result = client.echo("Hello from quickstart!")
        print(f"Echo response: {echo_result}")

        # 4. State store test
        log("quickstart", "INFO", "Testing state store...")
        client.store("demo_key", {"message": "Hello CLOVE!", "timestamp": time.time()})
        fetched = client.fetch("demo_key")
        if fetched.found:
            print(f"Stored and retrieved: {fetched.value}")
        client.delete("demo_key")

        # 5. List agents
        log("quickstart", "INFO", "Listing agents...")
        agents = client.list_agents()
        print(f"\nActive agents: {len(agents)}")
        for agent in agents:
            print(f"  - {agent.name} (ID: {agent.id}, State: {agent.state.value})")

        print(f"\n{'='*50}")
        print("Quickstart demo completed successfully!")
        print(f"{'='*50}\n")

    finally:
        client.disconnect()
        log("quickstart", "INFO", "Disconnected from kernel")


if __name__ == "__main__":
    main()
