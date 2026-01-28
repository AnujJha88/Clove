#!/usr/bin/env python3
"""Test 15: Async Syscalls - Verify async exec and poll"""
import sys
import os
import time
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agents', 'python_sdk'))
from clove_sdk import CloveClient


def main():
    print("=== Test 15: Async Syscalls ===\n")

    if not os.path.exists('/tmp/clove.sock'):
        print("SKIP - Kernel not running (/tmp/clove.sock not found)")
        print("   Start kernel with: ./build/clove_kernel")
        return 0

    try:
        with CloveClient() as client:
            print("Connected to kernel\n")

            print("--- Test 15.1: Async EXEC ---")
            result = client.exec("echo async-ok", async_=True)
            if not result or not result.get("success"):
                print(f"  FAILED - {result}")
                return 1

            request_id = result.get("request_id")
            if not request_id:
                print("  FAILED - Missing request_id")
                return 1

            print(f"  Accepted async request_id={request_id}")

            print("--- Test 15.2: Poll Async Results ---")
            deadline = time.time() + 5.0
            found = None
            while time.time() < deadline:
                poll = client.poll_async(max_results=10)
                if poll.get("success"):
                    for entry in poll.get("results", []):
                        if entry.get("request_id") == request_id:
                            found = entry
                            break
                if found:
                    break
                time.sleep(0.1)

            if not found:
                print("  FAILED - No async result within timeout")
                return 1

            try:
                payload = json.loads(found.get("payload", "{}"))
            except json.JSONDecodeError:
                print("  FAILED - Invalid payload JSON")
                return 1

            if payload.get("success") and "async-ok" in payload.get("stdout", ""):
                print("  PASSED\n")
            else:
                print(f"  FAILED - Unexpected payload: {payload}")
                return 1

            print("=== Test 15 PASSED ===")
            return 0

    except ConnectionRefusedError:
        print("SKIP - Cannot connect to kernel")
        return 0
    except Exception as e:
        print(f"ERROR - {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
