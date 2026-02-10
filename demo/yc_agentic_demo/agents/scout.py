#!/usr/bin/env python3
"""
Scout Agent - LLM-powered research agent for the YC demo.

Receives research topics, uses LLM to gather information,
and sends findings to the Critic and Synthesizer agents.
"""

import sys
import time
import json
from pathlib import Path

# Add SDK to path
sdk_path = Path(__file__).resolve().parent.parent.parent.parent / "agents" / "python_sdk"
sys.path.insert(0, str(sdk_path))

from clove_sdk import CloveClient


class ScoutAgent:
    def __init__(self, name: str = None, socket_path: str = "/tmp/clove.sock"):
        # Name will be set after connection if not provided
        self._pending_name = name
        self.name = name or "scout"
        self.client = CloveClient(socket_path)
        self.running = True
        self.mission_id = None
        self.findings = []

    def _detect_name(self):
        """Detect our name from kernel assignment or init message."""
        # The name is set when we receive the init message
        pass

    def log(self, msg: str):
        print(f"[{self.name}] {msg}", flush=True)

    def connect(self) -> bool:
        if not self.client.connect():
            self.log("ERROR: Failed to connect to kernel")
            return False
        self.client.register_name(self.name)
        self.log("Connected and registered")
        return True

    def research(self, topic: str, context: str = "") -> dict:
        """Use LLM to research a topic and return findings."""
        self.log(f"Researching: {topic}")

        prompt = f"""You are a research assistant. Your task is to provide factual, accurate information about the following topic.

Topic: {topic}

{f"Additional context: {context}" if context else ""}

Provide a concise but informative summary of the key facts, recent developments, and important details about this topic. Focus on accuracy and cite specific examples where possible.

Format your response as a structured summary with:
1. Key Facts (3-5 bullet points)
2. Recent Developments (if applicable)
3. Important Details

Keep your response under 300 words."""

        result = self.client.think(
            prompt=prompt,
            system_instruction="You are a factual research assistant. Only provide accurate, verifiable information. If you're uncertain about something, say so.",
            temperature=0.3
        )

        if result.get("success"):
            content = result.get("content", "")
            finding = {
                "topic": topic,
                "content": content,
                "source": self.name,
                "timestamp": time.time(),
                "tokens_used": result.get("tokens", 0)
            }
            self.findings.append(finding)
            self.log(f"Research complete: {len(content)} chars")
            return finding
        else:
            self.log(f"Research failed: {result.get('error', 'Unknown error')}")
            return {"topic": topic, "error": result.get("error", "Research failed")}

    def send_finding(self, finding: dict, to_agents: list):
        """Send a finding to other agents."""
        message = {
            "type": "finding",
            "mission_id": self.mission_id,
            "data": finding
        }
        for agent in to_agents:
            result = self.client.send_message(message, to_name=agent)
            if result.get("success"):
                self.log(f"Sent finding to {agent}")
            else:
                self.log(f"Failed to send to {agent}: {result.get('error')}")

    def handle_message(self, msg: dict):
        """Handle incoming messages."""
        payload = msg.get("message", {})
        msg_type = payload.get("type")

        if msg_type == "init":
            self.mission_id = payload.get("mission_id")
            # Get our assigned name from the init message if provided
            assigned_name = payload.get("agent_name")
            if assigned_name:
                self.name = assigned_name
                self.client.register_name(self.name)  # Re-register with correct name
            self.log(f"Initialized for mission: {self.mission_id}")
            # Send acknowledgment
            reply_to = payload.get("reply_to", "mission_control")
            self.client.send_message({
                "type": "init_ack",
                "agent": self.name
            }, to_name=reply_to)

        elif msg_type == "research":
            topic = payload.get("topic", "")
            context = payload.get("context", "")
            targets = payload.get("send_to", ["critic", "synthesizer"])

            finding = self.research(topic, context)
            if "error" not in finding:
                self.send_finding(finding, targets)

            # Notify mission control
            self.client.send_message({
                "type": "research_complete",
                "agent": self.name,
                "topic": topic,
                "success": "error" not in finding
            }, to_name=payload.get("reply_to", "mission_control"))

        elif msg_type == "status":
            self.client.send_message({
                "type": "status_report",
                "agent": self.name,
                "findings_count": len(self.findings),
                "mission_id": self.mission_id
            }, to_name=payload.get("reply_to", "mission_control"))

        elif msg_type == "shutdown":
            self.log("Received shutdown signal")
            self.running = False

        elif msg_type == "ping":
            # Respond to pings for liveness checks
            pass

    def run(self):
        """Main agent loop."""
        if not self.connect():
            return 1

        self.log("Starting main loop")

        while self.running:
            try:
                result = self.client.recv_messages(max_messages=10)
                messages = result.get("messages", [])

                for msg in messages:
                    self.handle_message(msg)

                time.sleep(0.1)

            except KeyboardInterrupt:
                self.log("Interrupted")
                break
            except Exception as e:
                self.log(f"Error: {e}")
                time.sleep(0.5)

        self.log("Shutting down")
        self.client.disconnect()
        return 0


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="scout")
    parser.add_argument("--socket", default="/tmp/clove.sock")
    args = parser.parse_args()

    agent = ScoutAgent(args.name, args.socket)
    return agent.run()


if __name__ == "__main__":
    sys.exit(main())
