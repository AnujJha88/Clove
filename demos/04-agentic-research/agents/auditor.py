#!/usr/bin/env python3
"""
Auditor Agent - Silent observer and logger for the YC demo.

Subscribes to events, logs all agent activities, and maintains
a complete audit trail for the mission.
"""

import sys
import time
import json
from pathlib import Path
from datetime import datetime

# Add SDK to path
sdk_path = Path(__file__).resolve().parent.parent.parent.parent / "agents" / "python_sdk"
sys.path.insert(0, str(sdk_path))

from clove_sdk import CloveClient


class AuditorAgent:
    def __init__(self, socket_path: str = "/tmp/clove.sock"):
        self.name = "auditor"
        self.client = CloveClient(socket_path)
        self.running = True
        self.mission_id = None
        self.output_dir = Path("outputs")
        self.audit_log = []
        self.agent_stats = {}
        self.start_time = None

    def log(self, msg: str):
        print(f"[{self.name}] {msg}", flush=True)

    def connect(self) -> bool:
        if not self.client.connect():
            self.log("ERROR: Failed to connect to kernel")
            return False
        self.client.register_name(self.name)

        # Subscribe to kernel events
        self.client.subscribe([
            "AGENT_SPAWNED",
            "AGENT_EXITED",
            "MESSAGE_RECEIVED",
            "SYSCALL_BLOCKED",
            "RESOURCE_WARNING"
        ])

        self.log("Connected, registered, and subscribed to events")
        return True

    def record_event(self, event_type: str, data: dict):
        """Record an event to the audit log."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "epoch": time.time(),
            "type": event_type,
            "data": data
        }
        self.audit_log.append(entry)

        # Update agent stats
        agent = data.get("agent") or data.get("source")
        if agent:
            if agent not in self.agent_stats:
                self.agent_stats[agent] = {
                    "events": 0,
                    "findings": 0,
                    "verifications": 0,
                    "errors": 0
                }
            self.agent_stats[agent]["events"] += 1

            if event_type == "finding_verified":
                self.agent_stats[agent]["verifications"] += 1
            elif "error" in str(data).lower():
                self.agent_stats[agent]["errors"] += 1

    def generate_audit_report(self) -> dict:
        """Generate a summary audit report."""
        duration = time.time() - self.start_time if self.start_time else 0

        report = {
            "mission_id": self.mission_id,
            "generated_at": datetime.now().isoformat(),
            "duration_seconds": round(duration, 2),
            "summary": {
                "total_events": len(self.audit_log),
                "agents_tracked": list(self.agent_stats.keys()),
                "agent_stats": self.agent_stats
            },
            "timeline": self.audit_log
        }

        return report

    def save_audit_log(self) -> str:
        """Save the audit log to a file."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"audit_{self.mission_id}_{timestamp}.json"
        filepath = self.output_dir / filename

        report = self.generate_audit_report()

        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)

        self.log(f"Audit log saved: {filepath}")
        return str(filepath)

    def poll_kernel_events(self):
        """Poll for kernel-level events."""
        result = self.client.poll_events(max_events=20)
        events = result.get("events", [])

        for event in events:
            event_type = event.get("type", "UNKNOWN")
            self.record_event(f"kernel_{event_type}", event)

            # Log important events
            if event_type == "AGENT_SPAWNED":
                self.log(f"Agent spawned: {event.get('name', 'unknown')}")
            elif event_type == "AGENT_EXITED":
                self.log(f"Agent exited: {event.get('name', 'unknown')} (code: {event.get('exit_code', '?')})")
            elif event_type == "RESOURCE_WARNING":
                self.log(f"Resource warning: {event.get('agent', 'unknown')} - {event.get('message', '')}")

    def handle_message(self, msg: dict):
        """Handle incoming messages."""
        payload = msg.get("message", {})
        msg_type = payload.get("type")

        if msg_type == "init":
            self.mission_id = payload.get("mission_id")
            self.output_dir = Path(payload.get("output_dir", "outputs"))
            self.audit_log = []  # Reset for new mission
            self.agent_stats = {}
            self.start_time = time.time()

            self.record_event("mission_started", {
                "mission_id": self.mission_id,
                "query": payload.get("query", "")
            })

            self.log(f"Initialized for mission: {self.mission_id}")
            reply_to = payload.get("reply_to", "mission_control")
            self.client.send_message({
                "type": "init_ack",
                "agent": self.name
            }, to_name=reply_to)

        elif msg_type == "audit_event":
            # Custom audit event from other agents
            event = payload.get("event", "unknown")
            data = payload.get("data", {})
            self.record_event(event, data)
            self.log(f"Audit event: {event}")

        elif msg_type == "generate_audit":
            # Generate and save the audit report
            filepath = self.save_audit_log()

            self.client.send_message({
                "type": "audit_complete",
                "mission_id": self.mission_id,
                "path": filepath,
                "events_count": len(self.audit_log)
            }, to_name=payload.get("reply_to", "mission_control"))

        elif msg_type == "status":
            self.client.send_message({
                "type": "status_report",
                "agent": self.name,
                "events_logged": len(self.audit_log),
                "agents_tracked": len(self.agent_stats),
                "mission_id": self.mission_id
            }, to_name=payload.get("reply_to", "mission_control"))

        elif msg_type == "shutdown":
            self.log("Received shutdown signal")
            # Save final audit before shutdown
            if self.audit_log:
                self.record_event("mission_ended", {"reason": "shutdown"})
                self.save_audit_log()
            self.running = False

        elif msg_type == "ping":
            pass

    def run(self):
        """Main agent loop."""
        if not self.connect():
            return 1

        self.log("Starting main loop (observing...)")

        last_poll = time.time()

        while self.running:
            try:
                # Check for direct messages
                result = self.client.recv_messages(max_messages=10)
                messages = result.get("messages", [])

                for msg in messages:
                    self.handle_message(msg)

                # Poll kernel events periodically
                if time.time() - last_poll > 0.5:
                    self.poll_kernel_events()
                    last_poll = time.time()

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
    parser.add_argument("--socket", default="/tmp/clove.sock")
    args = parser.parse_args()

    agent = AuditorAgent(args.socket)
    return agent.run()


if __name__ == "__main__":
    sys.exit(main())
