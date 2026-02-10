#!/usr/bin/env python3
"""
Mission Control - Main orchestrator for the YC Agentic Demo.

Coordinates multiple AI agents to research a topic collaboratively:
1. Spawns Scout agents to research subtopics
2. Critic agent verifies findings
3. Synthesizer compiles final report
4. Auditor tracks everything

Usage:
    python mission_control.py "What are the latest breakthroughs in protein folding?"
"""

import sys
import time
import json
import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Add SDK to path
sdk_path = Path(__file__).resolve().parent.parent.parent / "agents" / "python_sdk"
sys.path.insert(0, str(sdk_path))

from clove_sdk import CloveClient


@dataclass
class MissionConfig:
    query: str
    mission_id: str
    num_scouts: int = 2
    output_dir: Path = Path("outputs")
    socket_path: str = "/tmp/clove.sock"
    sandboxed: bool = True
    enable_chaos: bool = False
    chaos_target: Optional[str] = None


class MissionControl:
    """Orchestrates the multi-agent research mission."""

    def __init__(self, config: MissionConfig):
        self.config = config
        self.client = CloveClient(config.socket_path)
        self.agents = {}
        self.agent_status = {}
        self.start_time = None

    def log(self, msg: str, level: str = "INFO"):
        timestamp = time.strftime("%H:%M:%S")
        prefix = {
            "INFO": "\033[36m[MISSION]\033[0m",
            "SUCCESS": "\033[32m[MISSION]\033[0m",
            "ERROR": "\033[31m[MISSION]\033[0m",
            "WARN": "\033[33m[MISSION]\033[0m"
        }.get(level, "[MISSION]")
        print(f"{prefix} {timestamp} {msg}", flush=True)

    def connect(self) -> bool:
        if not self.client.connect():
            self.log("Failed to connect to kernel", "ERROR")
            return False
        self.client.register_name("mission_control")
        self.client.set_permissions(level="unrestricted")
        self.log("Connected to CloveOS kernel")
        return True

    def spawn_agent(self, name: str, script: str, limits: dict = None) -> bool:
        """Spawn a single agent with resource limits."""
        script_path = Path(__file__).parent / "agents" / script

        default_limits = {
            "memory_mb": 256,
            "cpu_percent": 25,
            "max_pids": 10
        }
        agent_limits = {**default_limits, **(limits or {})}

        self.log(f"Spawning {name} (mem={agent_limits['memory_mb']}MB, cpu={agent_limits['cpu_percent']}%)")

        result = self.client.spawn(
            name=name,
            script=str(script_path),
            sandboxed=self.config.sandboxed,
            network=False,
            limits=agent_limits,
            restart_policy="on_failure",
            max_restarts=3,
            restart_window=60
        )

        if result and result.get("status") == "running":
            self.agents[name] = result.get("id", 0)
            self.agent_status[name] = "spawned"
            self.log(f"  -> {name} spawned (pid={result.get('pid', '?')})", "SUCCESS")
            return True
        else:
            self.log(f"  -> Failed to spawn {name}: {result}", "ERROR")
            return False

    def wait_for_agent(self, name: str, timeout: float = 5.0) -> bool:
        """Wait for an agent to register and become responsive."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self.client.send_message({"type": "ping"}, to_name=name)
            if result.get("success"):
                self.agent_status[name] = "ready"
                return True
            time.sleep(0.2)
        return False

    def wait_for_acks(self, expected: list, timeout: float = 10.0) -> dict:
        """Wait for init acknowledgments from agents."""
        acks = {name: False for name in expected}
        deadline = time.time() + timeout

        while time.time() < deadline:
            if all(acks.values()):
                break
            result = self.client.recv_messages()
            for msg in result.get("messages", []):
                payload = msg.get("message", {})
                if payload.get("type") == "init_ack":
                    agent = payload.get("agent")
                    if agent in acks:
                        acks[agent] = True
                        self.agent_status[agent] = "initialized"
            time.sleep(0.1)

        return acks

    def spawn_all_agents(self) -> bool:
        """Spawn all agents needed for the mission."""
        agents_to_spawn = [
            # (name, script, limits)
            ("auditor", "auditor.py", {"memory_mb": 128, "cpu_percent": 10}),
            ("critic", "critic.py", {"memory_mb": 256, "cpu_percent": 25}),
            ("synthesizer", "synthesizer.py", {"memory_mb": 256, "cpu_percent": 25}),
        ]

        # Add scout agents - all use the same script, differentiated by name
        for i in range(1, self.config.num_scouts + 1):
            agents_to_spawn.append(
                (f"scout_{i}", "scout.py", {"memory_mb": 256, "cpu_percent": 30})
            )

        # Spawn all agents
        for name, script, limits in agents_to_spawn:
            if not self.spawn_agent(name, script, limits):
                return False

        # Wait for all agents to register
        self.log("Waiting for agents to register...")
        for name in self.agents.keys():
            if not self.wait_for_agent(name, timeout=5.0):
                self.log(f"Agent {name} failed to register", "WARN")

        return True

    def initialize_agents(self) -> bool:
        """Send initialization message to all agents."""
        base_message = {
            "type": "init",
            "mission_id": self.config.mission_id,
            "query": self.config.query,
            "output_dir": str(self.config.output_dir),
            "reply_to": "mission_control"
        }

        for name in self.agents.keys():
            # Include the agent's assigned name so scouts can identify themselves
            init_message = {**base_message, "agent_name": name}
            self.client.send_message(init_message, to_name=name)

        # Wait for acknowledgments
        acks = self.wait_for_acks(list(self.agents.keys()), timeout=10.0)
        missing = [name for name, acked in acks.items() if not acked]

        if missing:
            self.log(f"Missing init_ack from: {missing}", "WARN")

        return True

    def generate_subtopics(self, query: str, count: int) -> list:
        """Use LLM to break down the query into subtopics for scouts."""
        self.log("Generating research subtopics...")

        prompt = f"""Break down this research query into {count} specific subtopics that can be researched independently.

Query: {query}

Return exactly {count} subtopics, one per line. Each subtopic should be a specific aspect that contributes to answering the main query. Make them distinct and complementary.

Format:
1. [subtopic 1]
2. [subtopic 2]
...
"""

        result = self.client.think(
            prompt=prompt,
            system_instruction="You are a research planning assistant. Break down queries into clear, researchable subtopics.",
            temperature=0.3
        )

        if result.get("success"):
            content = result.get("content", "")
            # Parse subtopics
            subtopics = []
            for line in content.split("\n"):
                line = line.strip()
                if line and (line[0].isdigit() or line.startswith("-")):
                    # Remove numbering/bullets
                    topic = line.lstrip("0123456789.-) ").strip()
                    if topic:
                        subtopics.append(topic)

            if len(subtopics) >= count:
                return subtopics[:count]
            else:
                # Fallback: use the query itself
                return [query] * count
        else:
            self.log("Failed to generate subtopics, using main query", "WARN")
            return [query] * count

    def dispatch_research(self, subtopics: list) -> None:
        """Send research tasks to scout agents."""
        scouts = [name for name in self.agents.keys() if name.startswith("scout_")]

        for i, (scout, topic) in enumerate(zip(scouts, subtopics)):
            self.log(f"Dispatching to {scout}: {topic[:50]}...")
            self.client.send_message({
                "type": "research",
                "topic": topic,
                "context": self.config.query,
                "send_to": ["critic", "synthesizer"],
                "reply_to": "mission_control"
            }, to_name=scout)

    def wait_for_research(self, expected_count: int, timeout: float = 120.0) -> int:
        """Wait for research_complete messages from scouts."""
        completed = 0
        deadline = time.time() + timeout

        while completed < expected_count and time.time() < deadline:
            result = self.client.recv_messages()
            for msg in result.get("messages", []):
                payload = msg.get("message", {})
                if payload.get("type") == "research_complete":
                    agent = payload.get("agent", "unknown")
                    success = payload.get("success", False)
                    topic = payload.get("topic", "")[:40]

                    if success:
                        self.log(f"Research complete from {agent}: {topic}...", "SUCCESS")
                    else:
                        self.log(f"Research failed from {agent}: {topic}...", "WARN")

                    completed += 1

            time.sleep(0.2)

        return completed

    def wait_for_processing(self, timeout: float = 60.0) -> None:
        """Wait for critic to process all findings."""
        self.log("Waiting for verification to complete...")
        deadline = time.time() + timeout

        verified_count = 0
        while time.time() < deadline:
            result = self.client.recv_messages()
            for msg in result.get("messages", []):
                payload = msg.get("message", {})
                # Look for verification events
                if payload.get("type") == "audit_event":
                    if payload.get("event") == "finding_verified":
                        verified_count += 1
                        self.log(f"Finding verified ({verified_count})")

            # Check if we have enough verifications
            if verified_count >= self.config.num_scouts:
                break

            time.sleep(0.3)

        self.log(f"Verification phase complete ({verified_count} findings)")

    def trigger_report_generation(self) -> Optional[str]:
        """Tell synthesizer to generate the final report."""
        self.log("Triggering report generation...")

        self.client.send_message({
            "type": "generate_report",
            "reply_to": "mission_control"
        }, to_name="synthesizer")

        # Wait for report
        deadline = time.time() + 60.0
        while time.time() < deadline:
            result = self.client.recv_messages()
            for msg in result.get("messages", []):
                payload = msg.get("message", {})
                if payload.get("type") == "report_complete":
                    path = payload.get("path")
                    self.log(f"Report generated: {path}", "SUCCESS")
                    return path
                elif payload.get("type") == "report_error":
                    self.log(f"Report generation failed: {payload.get('error')}", "ERROR")
                    return None
            time.sleep(0.3)

        self.log("Report generation timed out", "ERROR")
        return None

    def trigger_audit(self) -> Optional[str]:
        """Tell auditor to generate the audit log."""
        self.log("Generating audit log...")

        self.client.send_message({
            "type": "generate_audit",
            "reply_to": "mission_control"
        }, to_name="auditor")

        # Wait for audit
        deadline = time.time() + 10.0
        while time.time() < deadline:
            result = self.client.recv_messages()
            for msg in result.get("messages", []):
                payload = msg.get("message", {})
                if payload.get("type") == "audit_complete":
                    path = payload.get("path")
                    self.log(f"Audit log saved: {path}", "SUCCESS")
                    return path
            time.sleep(0.2)

        return None

    def inject_chaos(self) -> None:
        """Inject a failure into one of the agents (for demo purposes)."""
        if not self.config.enable_chaos:
            return

        target = self.config.chaos_target
        if not target:
            # Default: crash scout_1
            scouts = [n for n in self.agents.keys() if n.startswith("scout_")]
            target = scouts[0] if scouts else None

        if not target:
            return

        self.log(f"CHAOS: Injecting failure into {target}...", "WARN")

        # Kill the agent - it should auto-restart due to restart_policy
        self.client.kill(name=target)

        # Give it a moment to restart
        time.sleep(1.0)

        # Check if it restarted
        if self.wait_for_agent(target, timeout=5.0):
            self.log(f"CHAOS: {target} recovered automatically!", "SUCCESS")
        else:
            self.log(f"CHAOS: {target} failed to recover", "ERROR")

    def shutdown_agents(self) -> None:
        """Send shutdown signal to all agents."""
        self.log("Shutting down agents...")
        for name in self.agents.keys():
            self.client.send_message({"type": "shutdown"}, to_name=name)
        time.sleep(0.5)

    def print_banner(self) -> None:
        """Print the mission banner."""
        print("\n" + "=" * 60)
        print("\033[36m" + """
   _____ _                    ____   _____
  / ____| |                  / __ \\ / ____|
 | |    | | _____   _____   | |  | | (___
 | |    | |/ _ \\ \\ / / _ \\  | |  | |\\___ \\
 | |____| | (_) \\ V /  __/  | |__| |____) |
  \\_____|_|\\___/ \\_/ \\___|   \\____/|_____/

        """ + "\033[0m")
        print("        Multi-Agent Research Mission")
        print("=" * 60)
        print(f"\n  Mission ID: {self.config.mission_id}")
        print(f"  Query: {self.config.query[:50]}...")
        print(f"  Scouts: {self.config.num_scouts}")
        print(f"  Chaos Mode: {'ENABLED' if self.config.enable_chaos else 'disabled'}")
        print("\n" + "=" * 60 + "\n")

    def print_summary(self, report_path: str, audit_path: str, duration: float) -> None:
        """Print the mission summary."""
        print("\n" + "=" * 60)
        print("\033[32m" + "  MISSION COMPLETE" + "\033[0m")
        print("=" * 60)
        print(f"\n  Duration: {duration:.1f} seconds")
        print(f"  Agents deployed: {len(self.agents)}")
        print(f"  Report: {report_path or 'Not generated'}")
        print(f"  Audit: {audit_path or 'Not generated'}")
        print("\n" + "=" * 60 + "\n")

    def run(self) -> int:
        """Execute the full mission."""
        self.start_time = time.time()
        self.print_banner()

        # Connect to kernel
        if not self.connect():
            return 1

        try:
            # Spawn all agents
            self.log("Phase 1: Spawning agents")
            if not self.spawn_all_agents():
                return 1

            # Initialize agents
            self.log("Phase 2: Initializing agents")
            self.initialize_agents()

            # Generate subtopics
            self.log("Phase 3: Planning research")
            subtopics = self.generate_subtopics(self.config.query, self.config.num_scouts)
            for i, topic in enumerate(subtopics, 1):
                self.log(f"  Subtopic {i}: {topic[:60]}...")

            # Dispatch research tasks
            self.log("Phase 4: Dispatching research tasks")
            self.dispatch_research(subtopics)

            # Optional: inject chaos mid-mission
            if self.config.enable_chaos:
                time.sleep(2.0)  # Let research start
                self.inject_chaos()

            # Wait for research to complete
            self.log("Phase 5: Awaiting research results")
            completed = self.wait_for_research(self.config.num_scouts, timeout=120.0)
            self.log(f"Research phase complete ({completed}/{self.config.num_scouts})")

            # Wait for critic to verify
            self.log("Phase 6: Verification")
            self.wait_for_processing(timeout=60.0)

            # Generate final report
            self.log("Phase 7: Report synthesis")
            report_path = self.trigger_report_generation()

            # Generate audit log
            self.log("Phase 8: Audit")
            audit_path = self.trigger_audit()

            # Shutdown
            self.shutdown_agents()

            # Summary
            duration = time.time() - self.start_time
            self.print_summary(report_path, audit_path, duration)

            return 0 if report_path else 1

        except KeyboardInterrupt:
            self.log("Mission aborted by user", "WARN")
            self.shutdown_agents()
            return 130

        except Exception as e:
            self.log(f"Mission failed: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            self.shutdown_agents()
            return 1

        finally:
            self.client.disconnect()


def main():
    parser = argparse.ArgumentParser(
        description="CloveOS Multi-Agent Research Mission",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python mission_control.py "What are the latest breakthroughs in protein folding?"
  python mission_control.py "Explain quantum computing advances" --scouts 3
  python mission_control.py "AI safety research overview" --chaos
        """
    )
    parser.add_argument("query", help="The research query to investigate")
    parser.add_argument("--scouts", type=int, default=2, help="Number of scout agents (default: 2)")
    parser.add_argument("--output", default="outputs", help="Output directory for reports")
    parser.add_argument("--socket", default="/tmp/clove.sock", help="Kernel socket path")
    parser.add_argument("--no-sandbox", action="store_true", help="Disable sandboxing")
    parser.add_argument("--chaos", action="store_true", help="Enable chaos injection (demo)")
    parser.add_argument("--chaos-target", help="Specific agent to crash (default: scout_1)")

    args = parser.parse_args()

    mission_id = f"mission_{int(time.time())}"
    output_dir = Path(args.output) / mission_id
    output_dir.mkdir(parents=True, exist_ok=True)

    config = MissionConfig(
        query=args.query,
        mission_id=mission_id,
        num_scouts=args.scouts,
        output_dir=output_dir,
        socket_path=args.socket,
        sandboxed=not args.no_sandbox,
        enable_chaos=args.chaos,
        chaos_target=args.chaos_target
    )

    mission = MissionControl(config)
    return mission.run()


if __name__ == "__main__":
    sys.exit(main())
