#!/usr/bin/env python3
"""Test 7: HTTP Requests - Test HTTP syscall"""
from clove import CloveClient
import os

def main():
    print("=== Test 7: HTTP Requests ===\n")

    # Check if kernel socket exists
    if not os.path.exists('/tmp/clove.sock'):
        print("⚠️  SKIP - Kernel not running")
        return 0

    try:
        with CloveClient() as client:
            # Test GET request
            print("--- GET https://httpbin.org/get ---")
            try:
                result = client.http("https://httpbin.org/get")
                print(f"Status: {result.get('status')}")
                print(f"Response length: {len(result.get('body', ''))}")

                if result.get('status') == 200:
                    print("✅ GET request successful")
                else:
                    print(f"⚠️ Unexpected status: {result.get('status')}")
            except Exception as e:
                print(f"❌ HTTP request failed: {e}")
                return 1

            # Test POST request
            print("\n--- POST https://httpbin.org/post ---")
            try:
                result = client.http(
                    "https://httpbin.org/post",
                    method="POST",
                    body='{"test": "data"}',
                    headers={"Content-Type": "application/json"}
                )
                print(f"Status: {result.get('status')}")

                if result.get('status') == 200:
                    print("✅ POST request successful")
                else:
                    print(f"⚠️ Unexpected status: {result.get('status')}")
            except Exception as e:
                print(f"❌ POST request failed: {e}")
                return 1

            print("\n✅ Test 7 PASSED")
            return 0

    except (ConnectionRefusedError, FileNotFoundError):
        print("⚠️  SKIP - Cannot connect to kernel")
        return 0

if __name__ == "__main__":
    exit(main())
