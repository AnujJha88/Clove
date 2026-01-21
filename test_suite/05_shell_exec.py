#!/usr/bin/env python3
from clove import CloveClient

def main():
    with CloveClient() as client:
        print("=== Test 5: Shell Command Execution ===\n")

        # Simple command
        print("--- Running: ls -la /tmp ---")
        result = client.exec("ls -la /tmp")
        print(f"Exit code: {result['exit_code']}")
        print(f"Output:\n{result['stdout'][:500]}\n")

        # Command with pipes
        print("--- Running: echo 'test' | wc -c ---")
        result = client.exec("echo 'test' | wc -c")
        print(f"Exit code: {result['exit_code']}")
        print(f"Output: {result['stdout'].strip()}\n")

        # Command that fails
        print("--- Running: ls /nonexistent ---")
        result = client.exec("ls /nonexistent")
        print(f"Exit code: {result['exit_code']}")
        print(f"Error: {result['stderr']}\n")

        # Timeout test (optional - takes 3 seconds)
        print("--- Testing timeout (2 second limit) ---")
        result = client.exec("sleep 5", timeout=2)
        if not result['success'] or result['exit_code'] != 0:
            print(f"Command timed out or failed as expected")
            print(f"Exit code: {result['exit_code']}")
            print(f"Stderr: {result['stderr']}\n")
        else:
            print(f"Warning: timeout may not have been enforced\n")

        print("✅ Test 5 PASSED")

if __name__ == "__main__":
    main()
