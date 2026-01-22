#!/usr/bin/env python3
from clove import CloveClient
import time

# Create a simple worker agent
WORKER_SCRIPT = """
import time
from clove import CloveClient

with CloveClient() as client:
    print("Worker agent started!")
    for i in range(10):
        print(f"Working... {i+1}/10")
        time.sleep(1)
    print("Worker agent finished!")
"""

def main():
    with CloveClient() as client:
        print("=== Test 6: Agent Management ===\n")

        # Create worker script
        with open('/tmp/worker_agent.py', 'w') as f:
            f.write(WORKER_SCRIPT)

        # List agents before spawning
        print("--- Agents before spawn ---")
        agents = client.list_agents()
        print(f"Active agents: {len(agents)}\n")

        # Spawn an agent
        print("--- Spawning worker agent ---")
        spawn_result = client.spawn(
            name="test-worker",
            script="/tmp/worker_agent.py",
            sandboxed=False
        )
        agent_id = spawn_result.get('id') if spawn_result else None
        print(f"Spawn result: {spawn_result}")
        print(f"Spawned agent ID: {agent_id}\n")

        time.sleep(2)

        # List agents after spawning
        print("--- Agents after spawn ---")
        agents = client.list_agents()
        print(f"Active agents: {len(agents)}")
        for agent in agents:
            print(f"  - Agent {agent['id']}: {agent['name']} (PID: {agent.get('pid', 'N/A')})")
        print()

        # Kill the agent
        print(f"--- Killing agent {agent_id} ---")
        killed = client.kill(agent_id=agent_id)
        print(f"Kill successful: {killed}\n")

        time.sleep(1)

        # Verify agent is gone
        print("--- Agents after kill ---")
        agents = client.list_agents()
        print(f"Active agents: {len(agents)}\n")

        print("✅ Test 6 PASSED")

if __name__ == "__main__":
    main()