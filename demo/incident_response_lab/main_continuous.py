#!/usr/bin/env python3
"""SOC Service - Real incident response system.

A production-style service with:
- Real log monitoring from system logs, journalctl, and custom files
- Real system metrics via psutil
- Log-only remediation mode
- Rich terminal dashboard
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict

from rich.console import Console

from dashboard import (
    Dashboard,
    DashboardState,
    EventRecord,
    RemediationRecord,
)
from utils import ensure_sdk_on_path, load_config, normalize_limits, write_json

ensure_sdk_on_path()
from clove_sdk import CloveClient  # noqa: E402


# Full agent list with new enhanced agents
AGENTS = [
    "health_monitor",
    "log_watcher",
    "event_simulator",      # NEW: Attack scenario simulation
    "threat_intel",         # NEW: IP reputation lookup
    "anomaly_triager",
    "alert_escalator",      # NEW: Webhook notifications
    "remediation_executor",
    "auditor",
]

AGENTS_WITH_WRITE = ["remediation_executor", "auditor"]
AGENTS_WITH_NETWORK = ["threat_intel", "alert_escalator"]  # Need HTTP access


class GracefulShutdown:
    def __init__(self):
        self.shutdown_requested = False
        signal.signal(signal.SIGINT, self._handler)
        signal.signal(signal.SIGTERM, self._handler)

    def _handler(self, signum, frame):
        self.shutdown_requested = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SOC Service - Real incident response")
    parser.add_argument("--config", default="configs/continuous_scenario.json",
                        help="Path to configuration file")
    parser.add_argument("--duration", type=float, default=0,
                        help="Duration in hours (0 = unlimited)")
    parser.add_argument("--run-id", default=time.strftime("run_%Y%m%d_%H%M%S"))
    parser.add_argument("--artifacts-dir", default="artifacts")
    parser.add_argument("--logs-dir", default="logs")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--socket-path", default="/tmp/clove.sock")
    parser.add_argument("--sandboxed", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--network", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--no-dashboard", action="store_true", help="Disable terminal dashboard")
    return parser.parse_args()


def wait_for_name(client: CloveClient, name: str, timeout_s: int = 10) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        result = client.send_message({"type": "ping"}, to_name=name)
        if result.get("success"):
            return True
        time.sleep(0.2)
    return False


def wait_for_acks(client: CloveClient, expected_agents: list[str], timeout_s: int = 10) -> dict[str, bool]:
    acks = {agent: False for agent in expected_agents}
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if all(acks.values()):
            break
        result = client.recv_messages()
        for msg in result.get("messages", []):
            payload = msg.get("message", {})
            if payload.get("type") == "init_ack":
                agent = payload.get("agent")
                if agent in acks:
                    acks[agent] = True
        time.sleep(0.1)
    return acks


def build_permissions(
    base_dir: Path,
    logs_dir: Path,
    artifacts_dir: Path,
    reports_dir: Path,
    remediation_mode: str = "log_only",
) -> Dict[str, Dict[str, Any]]:
    read_paths = [
        str(base_dir / "*"), str(base_dir / "*" / "*"), str(base_dir / "*" / "*" / "*"),
        str(logs_dir / "*"), str(logs_dir / "*" / "*"),
        str(artifacts_dir / "*"), str(artifacts_dir / "*" / "*"),
        str(reports_dir / "*"), str(reports_dir / "*" / "*"),
    ]
    write_paths = [
        str(logs_dir / "*"), str(logs_dir / "*" / "*"),
        str(artifacts_dir / "*"), str(artifacts_dir / "*" / "*"),
        str(reports_dir / "*"), str(reports_dir / "*" / "*"),
    ]
    perms = {"filesystem": {"read": read_paths, "write": write_paths}, "max_exec_time_ms": 5000}

    # Build agent-specific permissions
    agent_perms = {}
    for agent in AGENTS_WITH_WRITE:
        agent_perms[agent] = dict(perms)

        # Grant exec permission to remediation_executor for sandbox/real modes
        if agent == "remediation_executor" and remediation_mode in ("sandbox_exec", "real_exec"):
            agent_perms[agent]["exec"] = {
                "enabled": True,
                "timeout_ms": 10000
            }

    return agent_perms


def process_messages(client: CloveClient, state: DashboardState) -> None:
    result = client.recv_messages()
    for msg in result.get("messages", []):
        payload = msg.get("message", {})
        msg_type = payload.get("type", "")

        if msg_type == "heartbeat":
            state.update_agent_heartbeat(payload.get("agent", ""))

        elif msg_type == "log_event":
            # Event detected from real log sources
            state.add_event(EventRecord(
                timestamp=time.strftime("%H:%M:%S"),
                severity=payload.get("severity", "low"),
                system=payload.get("system", "unknown"),
                event_type=payload.get("event_type", "unknown"),
                details=payload.get("source", ""),
            ))

        elif msg_type == "log_source_status":
            # Update log source status in dashboard
            status = payload.get("status", {})
            state.update_log_sources(status)

        elif msg_type == "health_update":
            state.update_health(payload.get("system", ""), payload.get("health", {}))

        elif msg_type == "health_alert":
            system = payload.get("system", "")
            if system in state.systems:
                state.systems[system].status = "warn"

        elif msg_type == "remediation_event":
            state.add_remediation(RemediationRecord(
                timestamp=time.strftime("%H:%M:%S"),
                action=payload.get("action", "unknown"),
                system=payload.get("system", "unknown"),
                status=payload.get("status", "unknown"),
                incident_id=payload.get("incident_id", ""),
                mode=payload.get("mode", "log_only"),
                command=payload.get("command", ""),
                exit_code=payload.get("exit_code", 0),
            ))

        elif msg_type == "periodic_report":
            state.last_report_time = time.time()

        elif msg_type == "escalation_event":
            # Track webhook escalations
            state.alerts_escalated = getattr(state, 'alerts_escalated', 0) + 1

        elif msg_type == "scenario_started":
            # Event simulator started a scenario
            pass  # Just acknowledge, dashboard will see events


def request_report(client: CloveClient, state: DashboardState, run_id: str, reports_dir: Path) -> None:
    client.send_message({
        "type": "generate_report",
        "run_id": run_id,
        "report_type": "periodic",
        "reports_dir": str(reports_dir),
        "stats": {
            "total_events": state.total_events,
            "events_by_severity": state.events_by_severity,
            "remediations_logged": state.remediations_logged,
            "remediations_skipped": state.remediations_skipped,
            "runtime": state.get_runtime(),
        }
    }, to_name="auditor")
    state.last_report_time = time.time()


def main() -> int:
    args = parse_args()
    console = Console()
    base_dir = Path(__file__).resolve().parent

    # Load config
    config_path = base_dir / args.config
    config = load_config(config_path)
    if not config:
        console.print(f"[red]ERROR: Failed to load config from {config_path}[/red]")
        return 1

    # Extract config values
    service_config = config.get("service", {})
    service_name = service_config.get("name", "SOC Service")
    report_interval = service_config.get("report_interval_seconds", 300)
    heartbeat_interval = service_config.get("heartbeat_interval_seconds", 5)
    dashboard_refresh = service_config.get("dashboard_refresh_ms", 500) / 1000.0

    systems = config.get("systems", ["web", "auth", "database", "network"])
    limits_config = load_config(base_dir / "configs" / "clove_limits.json")

    # Set up directories
    artifacts_dir = (base_dir / args.artifacts_dir).resolve()
    logs_dir = (base_dir / args.logs_dir).resolve()
    reports_dir = (base_dir / args.reports_dir).resolve()

    run_artifacts_dir = artifacts_dir / args.run_id
    run_logs_dir = logs_dir / args.run_id
    run_reports_dir = reports_dir / args.run_id
    run_artifacts_dir.mkdir(parents=True, exist_ok=True)
    run_logs_dir.mkdir(parents=True, exist_ok=True)
    run_reports_dir.mkdir(parents=True, exist_ok=True)

    stage_limits = limits_config.get("limits", {})
    restart_policy = limits_config.get("restart_policy", "on-failure")
    max_restarts = int(limits_config.get("max_restarts", 3))
    restart_window = int(limits_config.get("restart_window", 60))

    duration_s = args.duration * 3600 if args.duration > 0 else 0

    # Get remediation mode for display
    remediation_mode_display = config.get("remediation", {}).get("mode", "log_only")
    mode_descriptions = {
        "log_only": "Log-only (no execution)",
        "sandbox_exec": "Sandbox (dry-run with echo)",
        "real_exec": "Real execution (LIVE)",
    }
    mode_desc = mode_descriptions.get(remediation_mode_display, remediation_mode_display)

    console.print(f"\n[bold cyan]{service_name}[/bold cyan]")
    console.print(f"[dim]Run ID: {args.run_id}[/dim]")
    console.print(f"[dim]Config: {config_path}[/dim]")
    console.print(f"[dim]Mode: Real logs + {mode_desc} remediation[/dim]")
    if args.duration > 0:
        console.print(f"[dim]Duration: {args.duration}h[/dim]")
    else:
        console.print(f"[dim]Running continuously (Ctrl+C to stop)[/dim]")
    console.print()

    client = CloveClient(socket_path=args.socket_path)
    if not client.connect():
        console.print("[red]ERROR: Failed to connect to Clove kernel[/red]")
        console.print("[dim]Make sure the kernel is running[/dim]")
        return 1

    shutdown = GracefulShutdown()
    state = DashboardState()
    state.service_name = service_name
    state.report_interval = report_interval
    state.last_report_time = time.time()
    state.agent_count = len(AGENTS)
    state.init_systems(systems)

    # Initialize new feature tracking
    state.ml_scored_count = 0
    state.ml_confidence_avg = 0.0
    state.ips_enriched = 0
    state.malicious_ips = 0
    state.alerts_escalated = 0

    dashboard = Dashboard(state, refresh_rate=dashboard_refresh)

    try:
        client.register_name("orchestrator")
        client.set_permissions(level="unrestricted")

        # Get remediation mode for permissions
        remediation_config = config.get("remediation", {})
        remediation_mode = remediation_config.get("mode", "log_only")

        permissions = build_permissions(base_dir, logs_dir, artifacts_dir, reports_dir, remediation_mode)

        console.print("[dim]Spawning agents...[/dim]")
        for agent in AGENTS:
            script_path = base_dir / "agents" / f"{agent}.py"
            limits = normalize_limits(stage_limits.get(agent, {}))

            # Grant network access to agents that need HTTP (threat_intel, alert_escalator)
            agent_needs_network = args.network or agent in AGENTS_WITH_NETWORK

            spawn_result = client.spawn(
                name=agent,
                script=str(script_path),
                sandboxed=args.sandboxed,
                network=agent_needs_network,
                limits=limits,
                restart_policy=restart_policy,
                max_restarts=max_restarts,
                restart_window=restart_window,
            )

            if not spawn_result or spawn_result.get("status") != "running":
                console.print(f"[red]ERROR: Failed to spawn {agent}[/red]")
                return 1

            if not wait_for_name(client, agent, timeout_s=15):
                console.print(f"[red]ERROR: {agent} did not register[/red]")
                return 1

            console.print(f"  [green]✓[/green] {agent}")

        # Set permissions
        for agent in AGENTS:
            ping_result = client.send_message({"type": "ping"}, to_name=agent)
            socket_id = ping_result.get("delivered_to", 0)
            if socket_id:
                if agent in permissions:
                    client.set_permissions(permissions=permissions[agent], agent_id=socket_id)
                else:
                    client.set_permissions(level="readonly", agent_id=socket_id)

        # Send init with full config
        init_message = {
            "type": "init",
            "run_id": args.run_id,
            "artifacts_dir": str(artifacts_dir),
            "logs_dir": str(logs_dir),
            "reports_dir": str(reports_dir),
            "config": config,
            "rules": config.get("rules", {}),
            "remediation_playbook": config.get("remediation", {}).get("playbook", {}),
            "reply_to": "orchestrator",
            "mode": "continuous",
        }

        for agent in AGENTS:
            client.send_message(init_message, to_name=agent)

        acks = wait_for_acks(client, AGENTS, timeout_s=10)
        missing = [a for a, ok in acks.items() if not ok]
        if missing:
            console.print(f"[yellow]WARN: Missing acks from: {missing}[/yellow]")

        console.print("\n[green]All agents initialized[/green]\n")

        # Start monitoring only (no start_generation or start_chaos)
        client.send_message({"type": "start_monitoring"}, to_name="health_monitor")

        start_time = time.time()

        if args.no_dashboard:
            # Headless mode
            console.print("[dim]Running in headless mode...[/dim]")
            console.print("[dim]Monitoring real log sources for incidents...[/dim]")
            while not shutdown.shutdown_requested:
                if duration_s > 0 and (time.time() - start_time) >= duration_s:
                    break
                process_messages(client, state)
                if (time.time() - state.last_report_time) >= state.report_interval:
                    request_report(client, state, args.run_id, run_reports_dir)
                time.sleep(0.1)
        else:
            # Dashboard mode
            with dashboard.start():
                while not shutdown.shutdown_requested:
                    if duration_s > 0 and (time.time() - start_time) >= duration_s:
                        break
                    process_messages(client, state)
                    if (time.time() - state.last_report_time) >= state.report_interval:
                        request_report(client, state, args.run_id, run_reports_dir)
                    dashboard.update()
                    time.sleep(0.05)

    except KeyboardInterrupt:
        pass
    except Exception as e:
        console.print(f"\n[red]ERROR: {e}[/red]")
        import traceback
        traceback.print_exc()
    finally:
        console.print("\n[dim]Generating final report...[/dim]")
        request_report(client, state, args.run_id, run_reports_dir)
        time.sleep(1.0)

        console.print("[dim]Shutting down agents...[/dim]")
        for agent in AGENTS:
            client.send_message({"type": "shutdown"}, to_name=agent)

        time.sleep(0.5)
        client.disconnect()

    # Summary
    console.print()
    console.print("[bold]=" * 50 + "[/bold]")
    console.print(f"[bold]{service_name} - Session Complete[/bold]")
    console.print("[bold]=" * 50 + "[/bold]")
    console.print(f"  Runtime:      {state.get_runtime()}")
    console.print(f"  Events:       {state.total_events:,}")
    console.print(f"  Remediations: Logged={state.remediations_logged} Skipped={state.remediations_skipped}")
    console.print()
    console.print(f"  [red]Critical:[/red] {state.events_by_severity.get('critical', 0)}")
    console.print(f"  [red]High:[/red]     {state.events_by_severity.get('high', 0)}")
    console.print(f"  [yellow]Medium:[/yellow]   {state.events_by_severity.get('medium', 0)}")
    console.print(f"  [cyan]Low:[/cyan]      {state.events_by_severity.get('low', 0)}")
    console.print()
    console.print(f"  Reports: {run_reports_dir}")
    console.print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
