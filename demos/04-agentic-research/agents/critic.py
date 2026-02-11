#!/usr/bin/env python3
"""
Critic Agent - Fact-checking and verification agent for the YC demo.

Receives findings from Scout agents, verifies claims using LLM,
and sends verified findings to the Synthesizer.
"""

import sys
import time
import json
from pathlib import Path

# Add SDK to path
sdk_path = Path(__file__).resolve().parent.parent.parent.parent / "agents" / "python_sdk"
sys.path.insert(0, str(sdk_path))

from clove_sdk import CloveClient


class CriticAgent:
    def __init__(self, socket_path: str = "/tmp/clove.sock"):
        self.name = "critic"
        self.client = CloveClient(socket_path)
        self.running = True
        self.mission_id = None
        self.verified_findings = []
        self.rejected_findings = []

    def log(self, msg: str):
        print(f"[{self.name}] {msg}", flush=True)

    def connect(self) -> bool:
        if not self.client.connect():
            self.log("ERROR: Failed to connect to kernel")
            return False
        self.client.register_name(self.name)
        self.log("Connected and registered")
        return True

    def verify_finding(self, finding: dict) -> dict:
        """Use LLM to fact-check a finding."""
        topic = finding.get("topic", "Unknown")
        content = finding.get("content", "")
        source = finding.get("source", "unknown")

        self.log(f"Verifying finding from {source}: {topic}")

        prompt = f"""You are a fact-checker. Analyze the following research finding for accuracy and reliability.

Topic: {topic}
Source: {source}

Finding:
{content}

Evaluate this finding and provide:
1. VERDICT: One of [VERIFIED, PARTIALLY_VERIFIED, NEEDS_REVIEW, REJECTED]
2. CONFIDENCE: A score from 0-100
3. ISSUES: Any factual errors, outdated information, or unsupported claims (if any)
4. NOTES: Brief explanation of your assessment

Be critical but fair. Look for:
- Factual accuracy
- Internal consistency
- Plausibility of claims
- Presence of specific, verifiable details

Format your response exactly as:
VERDICT: [your verdict]
CONFIDENCE: [score]
ISSUES: [list any issues or "None"]
NOTES: [your explanation]"""

        result = self.client.think(
            prompt=prompt,
            system_instruction="You are a rigorous fact-checker. Be thorough but fair in your assessments.",
            temperature=0.2
        )

        if result.get("success"):
            response = result.get("content", "")

            # Parse the response
            verdict = "NEEDS_REVIEW"
            confidence = 50
            issues = []
            notes = ""

            for line in response.split("\n"):
                line = line.strip()
                if line.startswith("VERDICT:"):
                    verdict = line.replace("VERDICT:", "").strip()
                elif line.startswith("CONFIDENCE:"):
                    try:
                        confidence = int(line.replace("CONFIDENCE:", "").strip())
                    except:
                        pass
                elif line.startswith("ISSUES:"):
                    issues_text = line.replace("ISSUES:", "").strip()
                    if issues_text.lower() != "none":
                        issues = [issues_text]
                elif line.startswith("NOTES:"):
                    notes = line.replace("NOTES:", "").strip()

            verification = {
                "original": finding,
                "verdict": verdict,
                "confidence": confidence,
                "issues": issues,
                "notes": notes,
                "verified_by": self.name,
                "timestamp": time.time()
            }

            if verdict in ["VERIFIED", "PARTIALLY_VERIFIED"]:
                self.verified_findings.append(verification)
                self.log(f"VERIFIED ({confidence}%): {topic}")
            else:
                self.rejected_findings.append(verification)
                self.log(f"REJECTED ({verdict}): {topic}")

            return verification
        else:
            self.log(f"Verification failed: {result.get('error', 'Unknown error')}")
            return {
                "original": finding,
                "verdict": "ERROR",
                "error": result.get("error", "Verification failed")
            }

    def send_verification(self, verification: dict):
        """Send verified finding to synthesizer and auditor."""
        message = {
            "type": "verified_finding",
            "mission_id": self.mission_id,
            "data": verification
        }

        # Send to synthesizer
        self.client.send_message(message, to_name="synthesizer")

        # Also send to auditor for logging
        self.client.send_message({
            "type": "audit_event",
            "event": "finding_verified",
            "data": {
                "topic": verification["original"].get("topic"),
                "verdict": verification.get("verdict"),
                "confidence": verification.get("confidence"),
                "source": verification["original"].get("source")
            }
        }, to_name="auditor")

    def handle_message(self, msg: dict):
        """Handle incoming messages."""
        payload = msg.get("message", {})
        msg_type = payload.get("type")

        if msg_type == "init":
            self.mission_id = payload.get("mission_id")
            self.log(f"Initialized for mission: {self.mission_id}")
            reply_to = payload.get("reply_to", "mission_control")
            self.client.send_message({
                "type": "init_ack",
                "agent": self.name
            }, to_name=reply_to)

        elif msg_type == "finding":
            finding = payload.get("data", {})
            verification = self.verify_finding(finding)
            self.send_verification(verification)

        elif msg_type == "status":
            self.client.send_message({
                "type": "status_report",
                "agent": self.name,
                "verified_count": len(self.verified_findings),
                "rejected_count": len(self.rejected_findings),
                "mission_id": self.mission_id
            }, to_name=payload.get("reply_to", "mission_control"))

        elif msg_type == "shutdown":
            self.log("Received shutdown signal")
            self.running = False

        elif msg_type == "ping":
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
    parser.add_argument("--socket", default="/tmp/clove.sock")
    args = parser.parse_args()

    agent = CriticAgent(args.socket)
    return agent.run()


if __name__ == "__main__":
    sys.exit(main())
