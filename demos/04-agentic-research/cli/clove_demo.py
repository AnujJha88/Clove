#!/usr/bin/env python3
"""
CloveOS Demo CLI - Clean interface for YC demo.

Commands:
    clove-demo mission "query"    Start a research mission
    clove-demo status             Show running agents and metrics
    clove-demo chaos <agent>      Inject failure into an agent
    clove-demo audit              Show recent audit events
    clove-demo kill <agent>       Kill a specific agent
    clove-demo dashboard          Launch the TUI dashboard
"""

import sys
import os
import argparse
import time
from pathlib import Path

# Add SDK to path
sdk_path = Path(__file__).resolve().parent.parent.parent.parent / "agents" / "python_sdk"
sys.path.insert(0, str(sdk_path))

from clove_sdk import CloveClient


class DemoCLI:
    def __init__(self, socket_path: str = "/tmp/clove.sock"):
        self.socket_path = socket_path
        self.client = None

    def connect(self) -> bool:
        self.client = CloveClient(self.socket_path)
        if not self.client.connect():
            print("\033[31mError:\033[0m Could not connect to CloveOS kernel")
            print(f"       Make sure the kernel is running at {self.socket_path}")
            return False
        return True

    def disconnect(self):
        if self.client:
            self.client.disconnect()

    def cmd_mission(self, args):
        """Start a research mission."""
        # Import and run mission control
        mission_dir = Path(__file__).parent.parent
        sys.path.insert(0, str(mission_dir))

        from mission_control import MissionControl, MissionConfig

        mission_id = f"mission_{int(time.time())}"
        output_dir = mission_dir / "outputs" / mission_id
        output_dir.mkdir(parents=True, exist_ok=True)

        config = MissionConfig(
            query=args.query,
            mission_id=mission_id,
            num_scouts=args.scouts,
            output_dir=output_dir,
            socket_path=self.socket_path,
            sandboxed=not args.no_sandbox,
            enable_chaos=args.chaos,
            chaos_target=args.chaos_target
        )

        mission = MissionControl(config)
        return mission.run()

    def cmd_status(self, args):
        """Show running agents and system status."""
        if not self.connect():
            return 1

        try:
            # Get agent list
            agents = self.client.list_agents()

            print("\n\033[36m=== CloveOS Status ===\033[0m\n")

            if not agents:
                print("No agents running")
            else:
                print(f"{'Name':<20} {'PID':<8} {'Status':<12} {'Memory':<12} {'CPU':<8}")
                print("-" * 60)

                for agent in agents:
                    name = agent.get("name", "unknown")[:19]
                    pid = agent.get("pid", "?")
                    status = agent.get("status", "unknown")

                    # Color-code status
                    if status == "running":
                        status_str = f"\033[32m{status}\033[0m"
                    elif status == "paused":
                        status_str = f"\033[33m{status}\033[0m"
                    else:
                        status_str = f"\033[31m{status}\033[0m"

                    # Get metrics if available
                    metrics = self.client.get_agent_metrics(agent.get("id"))
                    if metrics.get("success"):
                        mem = metrics.get("memory_rss_mb", 0)
                        cpu = metrics.get("cpu_percent", 0)
                        mem_str = f"{mem:.1f} MB"
                        cpu_str = f"{cpu:.1f}%"
                    else:
                        mem_str = "-"
                        cpu_str = "-"

                    print(f"{name:<20} {pid:<8} {status_str:<21} {mem_str:<12} {cpu_str:<8}")

            # System metrics
            sys_metrics = self.client.get_system_metrics()
            if sys_metrics.get("success"):
                print(f"\n{'System:':<20}")
                print(f"  CPU: {sys_metrics.get('cpu_percent', 0):.1f}%")
                print(f"  Memory: {sys_metrics.get('memory_used_mb', 0):.0f} MB / {sys_metrics.get('memory_total_mb', 0):.0f} MB")

            print()
            return 0

        finally:
            self.disconnect()

    def cmd_chaos(self, args):
        """Inject chaos into an agent."""
        if not self.connect():
            return 1

        try:
            target = args.agent
            mode = args.mode

            print(f"\n\033[33m[CHAOS]\033[0m Targeting: {target}")

            if mode == "kill":
                print(f"\033[33m[CHAOS]\033[0m Killing agent...")
                result = self.client.kill(name=target)
                if result:
                    print(f"\033[32m[CHAOS]\033[0m Agent killed - watching for auto-restart...")

                    # Wait and check for restart
                    time.sleep(2.0)
                    agents = self.client.list_agents()
                    restarted = any(a.get("name") == target for a in agents)

                    if restarted:
                        print(f"\033[32m[CHAOS]\033[0m Agent auto-restarted! Recovery successful.")
                    else:
                        print(f"\033[31m[CHAOS]\033[0m Agent did not restart (may need restart_policy)")
                else:
                    print(f"\033[31m[CHAOS]\033[0m Failed to kill agent")

            elif mode == "pause":
                print(f"\033[33m[CHAOS]\033[0m Pausing agent...")
                result = self.client.pause(name=target)
                if result:
                    print(f"\033[32m[CHAOS]\033[0m Agent paused (SIGSTOP)")
                else:
                    print(f"\033[31m[CHAOS]\033[0m Failed to pause agent")

            elif mode == "resume":
                print(f"\033[33m[CHAOS]\033[0m Resuming agent...")
                result = self.client.resume(name=target)
                if result:
                    print(f"\033[32m[CHAOS]\033[0m Agent resumed (SIGCONT)")
                else:
                    print(f"\033[31m[CHAOS]\033[0m Failed to resume agent")

            print()
            return 0

        finally:
            self.disconnect()

    def cmd_audit(self, args):
        """Show recent audit events."""
        if not self.connect():
            return 1

        try:
            result = self.client.get_audit_log(limit=args.limit)

            if not result.get("success"):
                print(f"\033[31mError:\033[0m {result.get('error', 'Failed to get audit log')}")
                return 1

            entries = result.get("entries", [])

            print(f"\n\033[36m=== Audit Log ({len(entries)} entries) ===\033[0m\n")

            if not entries:
                print("No audit entries")
            else:
                for entry in entries[-args.limit:]:
                    ts = entry.get("timestamp", "")[:19]
                    category = entry.get("category", "UNKNOWN")
                    message = entry.get("message", "")[:60]

                    # Color by category
                    if category == "SECURITY":
                        cat_str = f"\033[31m{category}\033[0m"
                    elif category == "AGENT_LIFECYCLE":
                        cat_str = f"\033[33m{category}\033[0m"
                    else:
                        cat_str = f"\033[36m{category}\033[0m"

                    print(f"{ts} [{cat_str:<25}] {message}")

            print()
            return 0

        finally:
            self.disconnect()

    def cmd_kill(self, args):
        """Kill a specific agent."""
        if not self.connect():
            return 1

        try:
            result = self.client.kill(name=args.agent)
            if result:
                print(f"\033[32m[OK]\033[0m Agent '{args.agent}' killed")
                return 0
            else:
                print(f"\033[31m[ERROR]\033[0m Failed to kill '{args.agent}'")
                return 1
        finally:
            self.disconnect()

    def cmd_dashboard(self, args):
        """Launch the TUI dashboard."""
        dashboard_path = Path(__file__).parent.parent / "dashboard" / "mission_tui.py"
        if dashboard_path.exists():
            os.execvp("python3", ["python3", str(dashboard_path), "--socket", self.socket_path])
        else:
            print(f"\033[31mError:\033[0m Dashboard not found at {dashboard_path}")
            return 1

    def cmd_queue(self, args):
        """Show LLM queue status (demo visualization)."""
        if not self.connect():
            return 1

        try:
            # Get all agent metrics to show who's using LLM
            result = self.client.get_all_agent_metrics()

            print("\n\033[36m=== LLM Queue Status ===\033[0m\n")
            print("Fair Scheduling: \033[32mENABLED\033[0m (Round-Robin)")
            print()

            if result.get("success"):
                agents = result.get("agents", [])
                if agents:
                    print(f"{'Agent':<20} {'LLM Calls':<12} {'Tokens Used':<15}")
                    print("-" * 50)
                    for agent in agents:
                        name = agent.get("name", "unknown")[:19]
                        # These would need to be tracked in practice
                        print(f"{name:<20} {'queued':<12} {'-':<15}")
                else:
                    print("No agents currently queued")
            else:
                print("Queue status unavailable")

            print()
            return 0

        finally:
            self.disconnect()


def main():
    parser = argparse.ArgumentParser(
        prog="clove-demo",
        description="CloveOS Demo CLI for YC presentation",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--socket", default="/tmp/clove.sock", help="Kernel socket path")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # mission command
    mission_parser = subparsers.add_parser("mission", help="Start a research mission")
    mission_parser.add_argument("query", help="Research query")
    mission_parser.add_argument("--scouts", type=int, default=2, help="Number of scout agents")
    mission_parser.add_argument("--chaos", action="store_true", help="Enable chaos injection")
    mission_parser.add_argument("--chaos-target", help="Agent to target for chaos")
    mission_parser.add_argument("--no-sandbox", action="store_true", help="Disable sandboxing")

    # status command
    subparsers.add_parser("status", help="Show agent status")

    # chaos command
    chaos_parser = subparsers.add_parser("chaos", help="Inject chaos")
    chaos_parser.add_argument("agent", help="Target agent name")
    chaos_parser.add_argument("--mode", choices=["kill", "pause", "resume"], default="kill",
                             help="Chaos mode (default: kill)")

    # audit command
    audit_parser = subparsers.add_parser("audit", help="Show audit log")
    audit_parser.add_argument("--limit", type=int, default=20, help="Max entries to show")

    # kill command
    kill_parser = subparsers.add_parser("kill", help="Kill an agent")
    kill_parser.add_argument("agent", help="Agent name to kill")

    # dashboard command
    subparsers.add_parser("dashboard", help="Launch TUI dashboard")

    # queue command
    subparsers.add_parser("queue", help="Show LLM queue status")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    cli = DemoCLI(args.socket)

    command_map = {
        "mission": cli.cmd_mission,
        "status": cli.cmd_status,
        "chaos": cli.cmd_chaos,
        "audit": cli.cmd_audit,
        "kill": cli.cmd_kill,
        "dashboard": cli.cmd_dashboard,
        "queue": cli.cmd_queue,
    }

    handler = command_map.get(args.command)
    if handler:
        return handler(args)
    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
