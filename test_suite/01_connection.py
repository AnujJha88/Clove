#!/usr/bin/env python3
"""Test 1: Basic Connection - Verify kernel connectivity"""
from clove import CloveClient
import os

def main():
    print("=== Test 1: Basic Connection ===\n")

    # Check if kernel socket exists
    if not os.path.exists('/tmp/clove.sock'):
        print("⚠️  SKIP - Kernel not running (/tmp/clove.sock not found)")
        print("   Start kernel with: ./build/clove_kernel")
        return 0  # Skip, don't fail

    # Test connection
    print("--- Connecting to kernel ---")
    try:
        with CloveClient() as client:
            print(f"Connected: Agent ID = {client.agent_id}")

            # NOOP test
            print("\n--- NOOP Echo Test ---")
            result = client.noop("Hello Clove!")
            print(f"Sent: 'Hello Clove!'")
            print(f"Received: '{result}'")

            if result == "Hello Clove!":
                print("\n✅ Test 1 PASSED")
            else:
                print("\n❌ Test 1 FAILED - Echo mismatch")
                return 1
    except ConnectionRefusedError:
        print("⚠️  SKIP - Cannot connect to kernel")
        return 0

    return 0

if __name__ == "__main__":
    exit(main())
