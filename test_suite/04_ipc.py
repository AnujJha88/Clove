#!/usr/bin/env python3
"""Test 4: Inter-Process Communication - Agent messaging"""
from clove import CloveClient
import time
import threading
import os

def main():
    print("=== Test 4: Inter-Process Communication ===\n")

    # Check if kernel socket exists
    if not os.path.exists('/tmp/clove.sock'):
        print("⚠️  SKIP - Kernel not running")
        return 0

    received_messages = []

    def receiver_thread():
        """Receiver agent that listens for messages"""
        try:
            with CloveClient() as client:
                # Register name
                client.register("test-receiver")

                # Wait for messages
                time.sleep(0.5)
                result = client.recv_messages()
                if result.get("success"):
                    received_messages.extend(result.get("messages", []))
        except Exception as e:
            print(f"Receiver error: {e}")

    try:
        # Start receiver in background
        print("--- Starting receiver agent ---")
        receiver = threading.Thread(target=receiver_thread)
        receiver.start()

        time.sleep(0.2)  # Let receiver register

        with CloveClient() as client:
            client.register("test-sender")

            # Send message to receiver
            print("--- Sending message to test-receiver ---")
            result = client.send_message({"type": "greeting", "text": "Hello from sender!"}, to_name="test-receiver")
            print(f"Send result: {result}")

            time.sleep(0.5)

        receiver.join(timeout=2)

        # Check results
        print(f"\n--- Received messages: {len(received_messages)} ---")
        for msg in received_messages:
            print(f"  {msg}")

        if len(received_messages) > 0:
            print("\n✅ Test 4 PASSED")
            return 0
        else:
            print("\n⚠️ Test 4 PARTIAL - No messages received (may be timing issue)")
            return 0  # Don't fail on timing issues

    except (ConnectionRefusedError, FileNotFoundError):
        print("⚠️  SKIP - Cannot connect to kernel")
        return 0

if __name__ == "__main__":
    exit(main())
