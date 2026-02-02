"""Rich-based terminal dashboard for the SOC service."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


SEVERITY_STYLES = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "cyan",
}

STATUS_STYLES = {
    "ok": "green",
    "warn": "yellow",
    "offline": "dim",
}


@dataclass
class EventRecord:
    timestamp: str
    severity: str
    system: str
    event_type: str
    details: str = ""


@dataclass
class RemediationRecord:
    timestamp: str
    action: str
    system: str
    status: str
    incident_id: str = ""
    mode: str = "log_only"
    command: str = ""
    exit_code: int = 0


@dataclass
class SystemHealth:
    name: str
    cpu: float = 0.0
    memory: float = 0.0
    disk: float = 0.0
    latency_ms: float = 0.0
    error_rate: float = 0.0
    status: str = "ok"
    last_update: float = 0.0


@dataclass
class LogSourceStatus:
    files_active: List[str] = field(default_factory=list)
    journal_running: bool = False
    last_update: float = 0.0


@dataclass
class DashboardState:
    start_time: float = field(default_factory=time.time)
    last_render: float = 0.0
    service_name: str = "SOC Service"

    total_events: int = 0
    events_by_severity: Dict[str, int] = field(default_factory=lambda: {
        "critical": 0, "high": 0, "medium": 0, "low": 0
    })
    recent_events: List[EventRecord] = field(default_factory=list)
    max_recent_events: int = 10

    systems: Dict[str, SystemHealth] = field(default_factory=dict)
    log_sources: LogSourceStatus = field(default_factory=LogSourceStatus)

    recent_remediations: List[RemediationRecord] = field(default_factory=list)
    max_recent_remediations: int = 6
    remediations_logged: int = 0
    remediations_skipped: int = 0

    agent_count: int = 8  # Updated: added event_simulator, threat_intel, alert_escalator
    agent_heartbeats: Dict[str, float] = field(default_factory=dict)

    last_report_time: float = 0.0
    report_interval: float = 300.0

    # New feature tracking
    ml_scored_count: int = 0
    ml_confidence_avg: float = 0.0
    ml_override_count: int = 0
    ips_enriched: int = 0
    malicious_ips: int = 0
    threat_cache_hits: int = 0
    alerts_escalated: int = 0
    escalation_failures: int = 0

    def init_systems(self, system_names: List[str]) -> None:
        for name in system_names:
            if name not in self.systems:
                self.systems[name] = SystemHealth(name=name)

    def add_event(self, event: EventRecord) -> None:
        self.total_events += 1
        severity = event.severity.lower()
        if severity in self.events_by_severity:
            self.events_by_severity[severity] += 1
        self.recent_events.insert(0, event)
        if len(self.recent_events) > self.max_recent_events:
            self.recent_events.pop()

    def add_remediation(self, rem: RemediationRecord) -> None:
        self.recent_remediations.insert(0, rem)
        if len(self.recent_remediations) > self.max_recent_remediations:
            self.recent_remediations.pop()
        # Count based on status
        if rem.status in ("logged", "dry_run", "executed"):
            self.remediations_logged += 1
        else:
            self.remediations_skipped += 1

    def update_health(self, system: str, health: Dict[str, Any]) -> None:
        if system in self.systems:
            h = self.systems[system]
            h.cpu = health.get("cpu", h.cpu)
            h.memory = health.get("memory", h.memory)
            h.disk = health.get("disk", h.disk)
            h.latency_ms = health.get("latency_ms", h.latency_ms)
            h.error_rate = health.get("error_rate", h.error_rate)
            h.status = health.get("status", h.status)
            h.last_update = time.time()

    def update_log_sources(self, status: Dict[str, Any]) -> None:
        files_info = status.get("files", {})
        journal_info = status.get("journal", {})
        self.log_sources.files_active = files_info.get("active", [])
        self.log_sources.journal_running = journal_info.get("running", False)
        self.log_sources.last_update = time.time()

    def update_agent_heartbeat(self, agent: str) -> None:
        self.agent_heartbeats[agent] = time.time()

    def get_runtime(self) -> str:
        elapsed = time.time() - self.start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def count_alive_agents(self) -> int:
        now = time.time()
        return sum(1 for t in self.agent_heartbeats.values() if now - t < 10)


class Dashboard:
    def __init__(self, state: DashboardState, refresh_rate: float = 0.5):
        self.state = state
        self.console = Console()
        self.refresh_rate = refresh_rate
        self.live: Live | None = None

    def create_header(self) -> Panel:
        runtime = self.state.get_runtime()
        events = self.state.total_events
        agents = self.state.count_alive_agents()
        sources = len(self.state.log_sources.files_active) + (1 if self.state.log_sources.journal_running else 0)

        header = Table.grid(expand=True)
        header.add_column(justify="center", ratio=1)
        header.add_row(
            Text(self.state.service_name, style="bold cyan")
        )
        header.add_row(
            Text(
                f"Runtime: {runtime}  |  Events: {events:,}  |  Sources: {sources}  |  Agents: {agents}/{self.state.agent_count}",
                style="dim"
            )
        )
        return Panel(header, style="cyan")

    def create_events_table(self) -> Panel:
        table = Table(show_header=True, header_style="bold", expand=True, box=None)
        table.add_column("Time", width=8)
        table.add_column("Sev", width=6)
        table.add_column("System", width=10)
        table.add_column("Type", width=18)

        for event in self.state.recent_events[:8]:
            style = SEVERITY_STYLES.get(event.severity.lower(), "")
            table.add_row(
                event.timestamp,
                Text(event.severity[:4].upper(), style=style),
                event.system,
                event.event_type[:18]
            )
        return Panel(table, title="Live Event Feed", border_style="blue")

    def create_health_panel(self) -> Panel:
        table = Table(show_header=True, header_style="bold", expand=True, box=None)
        table.add_column("System", width=10)
        table.add_column("CPU", width=6, justify="right")
        table.add_column("Mem", width=6, justify="right")
        table.add_column("Disk", width=6, justify="right")
        table.add_column("Status", width=8)

        for name, health in self.state.systems.items():
            status_style = STATUS_STYLES.get(health.status, "")
            cpu_style = "red" if health.cpu > 80 else ("yellow" if health.cpu > 60 else "green")
            mem_style = "red" if health.memory > 85 else ("yellow" if health.memory > 60 else "green")
            disk_style = "red" if health.disk > 90 else ("yellow" if health.disk > 75 else "green")

            table.add_row(
                name,
                Text(f"{health.cpu:.0f}%", style=cpu_style),
                Text(f"{health.memory:.0f}%", style=mem_style),
                Text(f"{health.disk:.0f}%", style=disk_style),
                Text(health.status.upper(), style=status_style)
            )
        return Panel(table, title="System Health (Real)", border_style="green")

    def create_log_sources_panel(self) -> Panel:
        table = Table(show_header=False, box=None, expand=True)
        table.add_column("Info")

        # Files
        files = self.state.log_sources.files_active
        if files:
            for f in files[:3]:  # Show first 3 files
                short_name = f.split("/")[-1] if "/" in f else f
                table.add_row(Text(f"[FILE] {short_name}", style="green"))
        else:
            table.add_row(Text("[FILE] No files accessible", style="dim"))

        # Journal
        if self.state.log_sources.journal_running:
            table.add_row(Text("[JOURNAL] systemd journal active", style="green"))
        else:
            table.add_row(Text("[JOURNAL] not running", style="dim"))

        return Panel(table, title="Log Sources", border_style="blue")

    def create_enhanced_features_panel(self) -> Panel:
        """Panel showing ML, Threat Intel, and Escalation stats."""
        table = Table(show_header=False, box=None, expand=True)
        table.add_column("Feature", width=14)
        table.add_column("Value", width=10)

        # ML Scoring section
        ml_scored = getattr(self.state, 'ml_scored_count', 0)
        ml_override = getattr(self.state, 'ml_override_count', 0)
        if ml_scored > 0:
            table.add_row(
                Text("ML Scored", style="cyan"),
                Text(str(ml_scored), style="green")
            )
            table.add_row(
                Text("ML Overrides", style="dim"),
                Text(str(ml_override), style="yellow" if ml_override > 0 else "dim")
            )
        else:
            table.add_row(Text("ML Scoring", style="dim"), Text("disabled", style="dim"))

        table.add_row("", "")

        # Threat Intel section
        ips_enriched = getattr(self.state, 'ips_enriched', 0)
        malicious = getattr(self.state, 'malicious_ips', 0)
        table.add_row(
            Text("IPs Checked", style="cyan"),
            Text(str(ips_enriched), style="green" if ips_enriched > 0 else "dim")
        )
        table.add_row(
            Text("Malicious", style="dim"),
            Text(str(malicious), style="red" if malicious > 0 else "dim")
        )

        table.add_row("", "")

        # Escalation section
        escalated = getattr(self.state, 'alerts_escalated', 0)
        table.add_row(
            Text("Alerts Sent", style="cyan"),
            Text(str(escalated), style="green" if escalated > 0 else "dim")
        )

        return Panel(table, title="Enhanced Features", border_style="magenta")

    def create_summary_panel(self) -> Panel:
        crit = self.state.events_by_severity.get("critical", 0)
        high = self.state.events_by_severity.get("high", 0)
        med = self.state.events_by_severity.get("medium", 0)
        low = self.state.events_by_severity.get("low", 0)
        total = crit + high + med + low

        table = Table(show_header=False, box=None, expand=True)
        table.add_column("Metric", width=12)
        table.add_column("Value", width=8)

        table.add_row(Text("Critical", style="bold red"), str(crit))
        table.add_row(Text("High", style="red"), str(high))
        table.add_row(Text("Medium", style="yellow"), str(med))
        table.add_row(Text("Low", style="cyan"), str(low))
        table.add_row("Total", str(total))
        table.add_row("", "")
        table.add_row("Logged", Text(str(self.state.remediations_logged), style="green"))
        table.add_row("Skipped", Text(str(self.state.remediations_skipped), style="yellow"))

        return Panel(table, title="Incident Summary", border_style="yellow")

    def create_remediations_panel(self) -> Panel:
        table = Table(show_header=True, header_style="bold", box=None, expand=True)
        table.add_column("Time", width=8)
        table.add_column("Action", width=12)
        table.add_column("Mode", width=7)
        table.add_column("Status", width=8)

        for rem in self.state.recent_remediations[:5]:
            # Status styling
            status_styles = {
                "logged": "dim",
                "dry_run": "yellow",
                "executed": "green",
                "failed": "red",
                "blocked": "red",
                "pending_approval": "yellow",
            }
            status_style = status_styles.get(rem.status, "dim")

            # Mode styling
            mode_styles = {
                "log_only": "dim",
                "sandbox_exec": "yellow",
                "real_exec": "green",
            }
            mode_style = mode_styles.get(rem.mode, "dim")
            mode_short = {"log_only": "LOG", "sandbox_exec": "DRY", "real_exec": "EXEC"}.get(rem.mode, rem.mode[:4].upper())

            table.add_row(
                rem.timestamp,
                rem.action[:12],
                Text(mode_short, style=mode_style),
                Text(rem.status.upper()[:8], style=status_style)
            )

        # Determine panel title based on most recent mode
        if self.state.recent_remediations:
            latest_mode = self.state.recent_remediations[0].mode
            mode_labels = {
                "log_only": "Log-Only",
                "sandbox_exec": "Sandbox (Dry-Run)",
                "real_exec": "Real Execution",
            }
            mode_label = mode_labels.get(latest_mode, latest_mode)
        else:
            mode_label = "Awaiting"

        return Panel(table, title=f"Recent Remediations ({mode_label})", border_style="magenta")

    def create_footer(self) -> Panel:
        next_report = max(0, self.state.report_interval - (time.time() - self.state.last_report_time))
        mins = int(next_report // 60)
        secs = int(next_report % 60)

        # Determine remediation mode from recent remediations
        if self.state.recent_remediations:
            mode = self.state.recent_remediations[0].mode
            mode_labels = {
                "log_only": "Log-Only",
                "sandbox_exec": "Sandbox (Dry-Run)",
                "real_exec": "Real Execution",
            }
            mode_text = mode_labels.get(mode, mode)
        else:
            mode_text = "Log-Only"

        return Panel(
            Text(f"Mode: Real Logs + {mode_text} Remediation  |  Next report: {mins}:{secs:02d}  |  Ctrl+C to stop", justify="center", style="dim"),
            style="dim"
        )

    def create_layout(self) -> Layout:
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=5),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3)
        )

        layout["main"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1)
        )

        layout["left"].split_column(
            Layout(name="events", ratio=2),
            Layout(name="summary", ratio=1)
        )

        layout["right"].split_column(
            Layout(name="health", ratio=1),
            Layout(name="enhanced", ratio=1),
            Layout(name="remediations", ratio=1)
        )

        layout["header"].update(self.create_header())
        layout["events"].update(self.create_events_table())
        layout["health"].update(self.create_health_panel())
        layout["enhanced"].update(self.create_enhanced_features_panel())
        layout["summary"].update(self.create_summary_panel())
        layout["remediations"].update(self.create_remediations_panel())
        layout["footer"].update(self.create_footer())

        return layout

    def start(self) -> Live:
        self.live = Live(
            self.create_layout(),
            console=self.console,
            refresh_per_second=1 / self.refresh_rate,
            screen=True
        )
        return self.live

    def update(self) -> None:
        if self.live:
            self.live.update(self.create_layout())
