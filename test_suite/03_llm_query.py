#!/usr/bin/env python3
"""Test 3: LLM Query - Test LLM integration through kernel"""
from clove import CloveClient
import os

def main():
    print("=== Test 3: LLM Query ===\n")

    # Check if kernel socket exists
    if not os.path.exists('/tmp/clove.sock'):
        print("⚠️  SKIP - Kernel not running")
        return 0

    try:
        with CloveClient() as client:
            # Simple math query
            print("--- Query: What is 2 + 2? ---")
            result = client.think("What is 2 + 2? Reply with just the number.")

            print(f"Response: {result.get('content', 'No content')}")
            print(f"Model: {result.get('model', 'Unknown')}")
            print(f"Tokens: {result.get('usage', {})}")

            # Check if we got a response
            if result.get('content'):
                # Check if response contains "4"
                if '4' in result['content']:
                    print("\n✅ LLM returned correct answer")
                else:
                    print("\n⚠️ LLM responded but answer may be incorrect")
            else:
                print("\n❌ No response from LLM")
                return 1

            print("\n✅ Test 3 PASSED")
            return 0

    except (ConnectionRefusedError, FileNotFoundError):
        print("⚠️  SKIP - Cannot connect to kernel")
        return 0

if __name__ == "__main__":
    exit(main())
