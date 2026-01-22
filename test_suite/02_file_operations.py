#!/usr/bin/env python3
"""Test 2: File Operations - Read and write files through kernel"""
from clove import CloveClient
import os

def main():
    print("=== Test 2: File Operations ===\n")

    # Check if kernel socket exists
    if not os.path.exists('/tmp/clove.sock'):
        print("⚠️  SKIP - Kernel not running")
        return 0

    try:
        with CloveClient() as client:
            # Create a temp file path
            test_file = "/tmp/clove_test_file.txt"
            test_content = "Hello from Clove test suite!\nLine 2\nLine 3"

            # Write file
            print(f"--- Writing to {test_file} ---")
            result = client.write(test_file, test_content)
            print(f"Write result: {result}")

            # Read file back
            print(f"\n--- Reading from {test_file} ---")
            content = client.read(test_file)
            print(f"Read content:\n{content}")

            # Verify
            if content.strip() == test_content:
                print("\n✅ Write/Read verified")
            else:
                print("\n❌ Content mismatch!")
                return 1

            # Cleanup
            os.remove(test_file)

            # Test reading non-existent file
            print("\n--- Reading non-existent file ---")
            try:
                client.read("/tmp/nonexistent_file_12345.txt")
                print("❌ Should have raised error")
                return 1
            except Exception as e:
                print(f"Got expected error: {type(e).__name__}")

            print("\n✅ Test 2 PASSED")
            return 0

    except (ConnectionRefusedError, FileNotFoundError):
        print("⚠️  SKIP - Cannot connect to kernel")
        return 0

if __name__ == "__main__":
    exit(main())
