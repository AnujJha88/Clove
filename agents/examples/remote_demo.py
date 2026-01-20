#!/usr/bin/env python3
"""
AgentOS Remote Connectivity Demo

This example demonstrates how a cloud agent can connect to a local
AgentOS kernel through a relay server.

Prerequisites:
1. Start the relay server:
   cd relay && python relay_server.py --dev

2. Start the AgentOS kernel with tunnel enabled:
   ./agentos_kernel

3. Connect the kernel to the relay (from a local agent or CLI):
   Use SYS_TUNNEL_CONNECT syscall with:
   - relay_url: ws://localhost:8765
   - machine_id: my-pc
   - token: test-token

4. Run this demo (simulating a cloud agent):
   python agents/examples/remote_demo.py

The demo will connect to the relay, authenticate as a remote agent,
and then execute commands on the local kernel through the relay.
"""

import sys
import os
import time
import argparse

# Add SDK to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python_sdk'))

from remote_client import RemoteAgentClient


def main():
    parser = argparse.ArgumentParser(description="AgentOS Remote Connectivity Demo")
    parser.add_argument("--relay", default="ws://localhost:8765",
                       help="Relay server URL")
    parser.add_argument("--name", default="remote-demo-agent",
                       help="Agent name")
    parser.add_argument("--token", default="demo-token",
                       help="Agent authentication token")
    parser.add_argument("--target", default="test-pc",
                       help="Target machine ID")
    args = parser.parse_args()

    print("=" * 60)
    print("AgentOS Remote Connectivity Demo")
    print("=" * 60)
    print()
    print(f"Relay URL:      {args.relay}")
    print(f"Agent Name:     {args.name}")
    print(f"Target Machine: {args.target}")
    print()

    # Create remote client
    client = RemoteAgentClient(
        relay_url=args.relay,
        agent_name=args.name,
        agent_token=args.token,
        target_machine=args.target
    )

    print("[1] Connecting to relay server...")
    try:
        if not client.connect():
            print("    FAILED: Could not connect to relay")
            print()
            print("Make sure:")
            print("  1. Relay server is running: cd relay && python relay_server.py --dev")
            print("  2. Kernel is connected to relay with machine_id:", args.target)
            return 1
        print("    OK: Connected to relay")
        print()
    except Exception as e:
        print(f"    FAILED: {e}")
        return 1

    # Test echo
    print("[2] Testing echo (SYS_NOOP)...")
    result = client.echo("Hello from the cloud!")
    if result:
        print(f"    OK: Echo response: {result}")
    else:
        print("    FAILED: No echo response")
    print()

    # List agents
    print("[3] Listing local agents (SYS_LIST)...")
    agents = client.list_agents()
    if agents:
        print(f"    OK: Found {len(agents)} agents:")
        for agent in agents:
            print(f"        - {agent.get('name', 'unnamed')} (id={agent.get('id')}, state={agent.get('state')})")
    else:
        print("    OK: No agents running")
    print()

    # Test LLM
    print("[4] Testing LLM (SYS_THINK)...")
    result = client.think("What is 2+2? Answer in one word.")
    if result.get("success"):
        print(f"    OK: LLM response: {result.get('content', '')[:100]}...")
    else:
        print(f"    SKIPPED: {result.get('error', 'LLM not configured')}")
    print()

    # Execute command
    print("[5] Executing command (SYS_EXEC)...")
    result = client.exec("echo 'Hello from remote agent!'")
    if result.get("success"):
        print(f"    OK: Command output: {result.get('stdout', '').strip()}")
    else:
        print(f"    FAILED: {result.get('error', 'Unknown error')}")
    print()

    # Read a file
    print("[6] Reading /etc/hostname (SYS_READ)...")
    result = client.read_file("/etc/hostname")
    if result.get("success"):
        print(f"    OK: Hostname: {result.get('content', '').strip()}")
    else:
        print(f"    FAILED: {result.get('error', 'Unknown error')}")
    print()

    # Store and fetch data
    print("[7] Testing state store (SYS_STORE/SYS_FETCH)...")
    client.store("remote_demo_key", {"message": "Hello from cloud!", "timestamp": time.time()})
    result = client.fetch("remote_demo_key")
    if result.get("exists"):
        print(f"    OK: Stored and retrieved: {result.get('value')}")
    else:
        print("    FAILED: Could not retrieve stored value")
    print()

    # Get permissions
    print("[8] Getting permissions (SYS_GET_PERMS)...")
    result = client.get_permissions()
    if result.get("success"):
        perms = result.get("permissions", {})
        print(f"    OK: Permission level: {perms.get('level', 'unknown')}")
        print(f"        Can execute: {perms.get('can_execute', False)}")
        print(f"        Can use LLM: {perms.get('can_llm', False)}")
        print(f"        Can HTTP: {perms.get('can_http', False)}")
    else:
        print(f"    FAILED: {result.get('error', 'Unknown error')}")
    print()

    # Disconnect
    print("[9] Disconnecting from relay...")
    client.disconnect()
    print("    OK: Disconnected")
    print()

    print("=" * 60)
    print("Demo completed successfully!")
    print("=" * 60)
    print()
    print("This demonstrates that a cloud agent can:")
    print("  - Connect through a relay to a local kernel")
    print("  - Execute all standard syscalls remotely")
    print("  - Work behind NAT without port forwarding")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
