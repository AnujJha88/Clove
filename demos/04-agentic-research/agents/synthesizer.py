#!/usr/bin/env python3
"""
Synthesizer Agent - Report compilation agent for the YC demo.

Receives verified findings from the Critic, combines them into
a coherent report, and produces the final output.
"""

import sys
import time
import json
from pathlib import Path

# Add SDK to path
sdk_path = Path(__file__).resolve().parent.parent.parent.parent / "agents" / "python_sdk"
sys.path.insert(0, str(sdk_path))

from clove_sdk import CloveClient


class SynthesizerAgent:
    def __init__(self, socket_path: str = "/tmp/clove.sock"):
        self.name = "synthesizer"
        self.client = CloveClient(socket_path)
        self.running = True
        self.mission_id = None
        self.mission_query = ""
        self.verified_findings = []
        self.output_dir = Path("outputs")

    def log(self, msg: str):
        print(f"[{self.name}] {msg}", flush=True)

    def connect(self) -> bool:
        if not self.client.connect():
            self.log("ERROR: Failed to connect to kernel")
            return False
        self.client.register_name(self.name)
        self.log("Connected and registered")
        return True

    def synthesize_report(self) -> dict:
        """Use LLM to synthesize all findings into a coherent report."""
        if not self.verified_findings:
            self.log("No findings to synthesize")
            return {"error": "No findings available"}

        self.log(f"Synthesizing {len(self.verified_findings)} verified findings")

        # Build context from all findings
        findings_text = ""
        for i, vf in enumerate(self.verified_findings, 1):
            original = vf.get("original", {})
            findings_text += f"""
### Finding {i}: {original.get('topic', 'Unknown')}
Source: {original.get('source', 'unknown')}
Verification: {vf.get('verdict', 'Unknown')} (Confidence: {vf.get('confidence', 0)}%)

{original.get('content', 'No content')}

---
"""

        prompt = f"""You are a research synthesizer. Your task is to combine multiple verified research findings into a single, coherent report.

Original Research Query: {self.mission_query}

Verified Findings:
{findings_text}

Create a well-structured research report that:
1. Answers the original query comprehensively
2. Integrates all the verified findings coherently
3. Highlights key insights and patterns
4. Notes any areas of uncertainty or disagreement
5. Provides actionable conclusions

Format the report as:
# Research Report: [Topic]

## Executive Summary
[2-3 sentence overview]

## Key Findings
[Integrated findings organized by theme]

## Analysis
[Deeper analysis and connections between findings]

## Conclusions
[Final takeaways and recommendations]

## Sources
[List the sources/scouts that contributed]"""

        result = self.client.think(
            prompt=prompt,
            system_instruction="You are an expert research synthesizer. Create clear, well-organized reports that integrate multiple sources.",
            temperature=0.4
        )

        if result.get("success"):
            report_content = result.get("content", "")

            report = {
                "mission_id": self.mission_id,
                "query": self.mission_query,
                "content": report_content,
                "findings_count": len(self.verified_findings),
                "generated_at": time.time(),
                "tokens_used": result.get("tokens", 0)
            }

            self.log(f"Report generated: {len(report_content)} chars")
            return report
        else:
            self.log(f"Synthesis failed: {result.get('error', 'Unknown error')}")
            return {"error": result.get("error", "Synthesis failed")}

    def save_report(self, report: dict) -> str:
        """Save the report to a file."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"report_{self.mission_id}_{timestamp}.md"
        filepath = self.output_dir / filename

        content = report.get("content", "No content")

        # Add metadata header
        full_content = f"""<!--
Mission ID: {report.get('mission_id')}
Query: {report.get('query')}
Findings: {report.get('findings_count')}
Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
-->

{content}
"""

        filepath.write_text(full_content)
        self.log(f"Report saved: {filepath}")
        return str(filepath)

    def handle_message(self, msg: dict):
        """Handle incoming messages."""
        payload = msg.get("message", {})
        msg_type = payload.get("type")

        if msg_type == "init":
            self.mission_id = payload.get("mission_id")
            self.mission_query = payload.get("query", "")
            self.output_dir = Path(payload.get("output_dir", "outputs"))
            self.verified_findings = []  # Reset for new mission
            self.log(f"Initialized for mission: {self.mission_id}")
            reply_to = payload.get("reply_to", "mission_control")
            self.client.send_message({
                "type": "init_ack",
                "agent": self.name
            }, to_name=reply_to)

        elif msg_type == "finding":
            # Raw finding from scout (before verification)
            finding = payload.get("data", {})
            self.log(f"Received raw finding: {finding.get('topic', 'unknown')}")
            # We'll wait for verified findings from critic

        elif msg_type == "verified_finding":
            # Verified finding from critic
            verification = payload.get("data", {})
            verdict = verification.get("verdict", "UNKNOWN")

            if verdict in ["VERIFIED", "PARTIALLY_VERIFIED"]:
                self.verified_findings.append(verification)
                topic = verification.get("original", {}).get("topic", "unknown")
                self.log(f"Added verified finding: {topic} ({len(self.verified_findings)} total)")
            else:
                self.log(f"Skipped non-verified finding: {verdict}")

        elif msg_type == "generate_report":
            # Signal to generate the final report
            report = self.synthesize_report()

            if "error" not in report:
                filepath = self.save_report(report)

                # Notify mission control
                self.client.send_message({
                    "type": "report_complete",
                    "mission_id": self.mission_id,
                    "path": filepath,
                    "findings_count": len(self.verified_findings)
                }, to_name=payload.get("reply_to", "mission_control"))

                # Notify auditor
                self.client.send_message({
                    "type": "audit_event",
                    "event": "report_generated",
                    "data": {
                        "mission_id": self.mission_id,
                        "path": filepath,
                        "findings_count": len(self.verified_findings)
                    }
                }, to_name="auditor")
            else:
                self.client.send_message({
                    "type": "report_error",
                    "mission_id": self.mission_id,
                    "error": report.get("error")
                }, to_name=payload.get("reply_to", "mission_control"))

        elif msg_type == "status":
            self.client.send_message({
                "type": "status_report",
                "agent": self.name,
                "verified_findings": len(self.verified_findings),
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

    agent = SynthesizerAgent(args.socket)
    return agent.run()


if __name__ == "__main__":
    sys.exit(main())
