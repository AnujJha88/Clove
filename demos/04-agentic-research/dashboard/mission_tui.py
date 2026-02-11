#!/usr/bin/env python3
"""
Mission TUI Dashboard - Real-time visualization for YC demo.

Shows:
- Agent status with resource usage
- Live IPC message flow
- Mission progress
- Audit events

Usage:
    python mission_tui.py
    python mission_tui.py --socket /tmp/clove.sock
"""

import sys
import time
import argparse
from pathlib import Path
from datetime import datetime
from collections import deque

# Add SDK to path
sdk_path = Path(__file__).resolve().parent.parent.parent.parent / "agents" / "python_sdk"
sys.path.insert(0, str(sdk_path))

try:
    from rich.console import Console
    from rich.table import Table
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.live import Live
    from rich.text import Text
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich import box
except ImportError:
    print("Error: 'rich' library required. Install with: pip install rich")
    sys.exit(1)

from clove_sdk import CloveClient


class MissionDashboard:
    def __init__(self, socket_path: str = "/tmp/clove.sock"):
        self.socket_path = socket_path
        self.client = None
        self.console = Console()
        self.running = True

        # State
        self.agents = {}
        self.messages = deque(maxlen=15)
        self.events = deque(maxlen=10)
        self.mission_info = {}
        self.start_time = time.time()

    def connect(self) -> bool:
        self.client = CloveClient(self.socket_path)
        if not self.client.connect():
            return False
        self.client.register_name("dashboard")
        self.client.subscribe([
            "AGENT_SPAWNED",
            "AGENT_EXITED",
            "MESSAGE_RECEIVED",
            "RESOURCE_WARNING"
        ])
        return True

    def disconnect(self):
        if self.client:
            self.client.disconnect()

    def poll_data(self):
        """Poll for new data from the kernel."""
        # Get agent list
        agent_list = self.client.list_agents()
        if agent_list:
            for agent in agent_list:
                name = agent.get("name", "unknown")
                self.agents[name] = agent

        # Get metrics for each agent
        for name, agent in self.agents.items():
            metrics = self.client.get_agent_metrics(agent.get("id"))
            if metrics.get("success"):
                self.agents[name]["metrics"] = metrics

        # Poll kernel events
        events = self.client.poll_events(max_events=20)
        for event in events.get("events", []):
            self.events.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "type": event.get("type", "UNKNOWN"),
                "data": event
            })

        # Check for messages (to see IPC flow)
        messages = self.client.recv_messages(max_messages=10)
        for msg in messages.get("messages", []):
            payload = msg.get("message", {})
            self.messages.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "from": msg.get("from_name", "?"),
                "type": payload.get("type", "?"),
                "preview": str(payload)[:40]
            })

    def make_header(self) -> Panel:
        """Create the header panel."""
        elapsed = time.time() - self.start_time
        mins, secs = divmod(int(elapsed), 60)

        grid = Table.grid(expand=True)
        grid.add_column(justify="left")
        grid.add_column(justify="center")
        grid.add_column(justify="right")

        grid.add_row(
            Text("CloveOS", style="bold cyan"),
            Text("Multi-Agent Mission Dashboard", style="bold white"),
            Text(f"Uptime: {mins:02d}:{secs:02d}", style="dim")
        )

        return Panel(grid, style="cyan", box=box.DOUBLE)

    def make_agents_table(self) -> Panel:
        """Create the agents status table."""
        table = Table(
            title="Agents",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan"
        )
        table.add_column("Name", style="bold")
        table.add_column("Status", justify="center")
        table.add_column("PID", justify="right")
        table.add_column("CPU", justify="right")
        table.add_column("Memory", justify="right")
        table.add_column("Role", style="dim")

        # Define roles for coloring
        role_map = {
            "scout": ("Researcher", "blue"),
            "critic": ("Verifier", "yellow"),
            "synthesizer": ("Compiler", "green"),
            "auditor": ("Observer", "magenta"),
            "mission_control": ("Controller", "cyan"),
        }

        for name, agent in sorted(self.agents.items()):
            status = agent.get("status", "unknown")
            pid = str(agent.get("pid", "-"))

            # Status styling
            if status == "running":
                status_text = Text("● RUNNING", style="bold green")
            elif status == "paused":
                status_text = Text("◐ PAUSED", style="bold yellow")
            else:
                status_text = Text("○ " + status.upper(), style="dim")

            # Metrics
            metrics = agent.get("metrics", {})
            cpu = metrics.get("cpu_percent", 0)
            mem = metrics.get("memory_rss_mb", 0)

            # CPU bar
            cpu_bar = self._make_bar(cpu, 100, 8)
            mem_str = f"{mem:.1f}MB"

            # Role
            role, color = ("Agent", "white")
            for key, (r, c) in role_map.items():
                if key in name.lower():
                    role, color = r, c
                    break

            table.add_row(
                Text(name, style=color),
                status_text,
                pid,
                cpu_bar,
                mem_str,
                Text(role, style=f"dim {color}")
            )

        if not self.agents:
            table.add_row("No agents", "", "", "", "", "")

        return Panel(table, title="[bold cyan]Agent Status[/]", border_style="cyan")

    def _make_bar(self, value: float, max_val: float, width: int = 10) -> Text:
        """Create a simple progress bar."""
        filled = int((value / max_val) * width)
        filled = min(filled, width)
        empty = width - filled

        # Color based on value
        if value > 80:
            color = "red"
        elif value > 50:
            color = "yellow"
        else:
            color = "green"

        bar = "█" * filled + "░" * empty
        return Text(f"{bar} {value:.0f}%", style=color)

    def make_messages_panel(self) -> Panel:
        """Create the IPC messages panel."""
        table = Table(box=None, show_header=True, header_style="bold yellow")
        table.add_column("Time", style="dim", width=8)
        table.add_column("From", style="cyan", width=12)
        table.add_column("Type", style="yellow", width=15)
        table.add_column("Preview", style="dim")

        for msg in list(self.messages)[-10:]:
            table.add_row(
                msg["time"],
                msg["from"][:11],
                msg["type"][:14],
                msg["preview"][:35]
            )

        if not self.messages:
            table.add_row("-", "-", "Waiting for messages...", "-")

        return Panel(table, title="[bold yellow]IPC Messages[/]", border_style="yellow")

    def make_events_panel(self) -> Panel:
        """Create the kernel events panel."""
        table = Table(box=None, show_header=True, header_style="bold magenta")
        table.add_column("Time", style="dim", width=8)
        table.add_column("Event", style="magenta")
        table.add_column("Details", style="dim")

        for event in list(self.events)[-8:]:
            event_type = event["type"]
            data = event.get("data", {})

            # Format details based on event type
            if event_type == "AGENT_SPAWNED":
                details = f"Agent: {data.get('name', '?')}"
            elif event_type == "AGENT_EXITED":
                details = f"Agent: {data.get('name', '?')} (code: {data.get('exit_code', '?')})"
            elif event_type == "RESOURCE_WARNING":
                details = f"{data.get('agent', '?')}: {data.get('message', '')[:30]}"
            else:
                details = str(data)[:40]

            # Color by event type
            type_style = "magenta"
            if "ERROR" in event_type or "EXITED" in event_type:
                type_style = "red"
            elif "SPAWN" in event_type:
                type_style = "green"
            elif "WARNING" in event_type:
                type_style = "yellow"

            table.add_row(
                event["time"],
                Text(event_type, style=type_style),
                details[:40]
            )

        if not self.events:
            table.add_row("-", "Monitoring...", "-")

        return Panel(table, title="[bold magenta]Kernel Events[/]", border_style="magenta")

    def make_stats_panel(self) -> Panel:
        """Create a stats summary panel."""
        # Get system metrics
        sys_metrics = self.client.get_system_metrics()

        stats = []

        # Agent counts
        total = len(self.agents)
        running = sum(1 for a in self.agents.values() if a.get("status") == "running")
        stats.append(f"[cyan]Agents:[/] {running}/{total} running")

        # System stats
        if sys_metrics.get("success"):
            cpu = sys_metrics.get("cpu_percent", 0)
            mem_used = sys_metrics.get("memory_used_mb", 0)
            mem_total = sys_metrics.get("memory_total_mb", 1)
            mem_pct = (mem_used / mem_total) * 100

            stats.append(f"[cyan]System CPU:[/] {cpu:.1f}%")
            stats.append(f"[cyan]System Mem:[/] {mem_pct:.1f}%")

        # Message counts
        stats.append(f"[cyan]Messages:[/] {len(self.messages)}")
        stats.append(f"[cyan]Events:[/] {len(self.events)}")

        content = "\n".join(stats)
        return Panel(content, title="[bold green]Stats[/]", border_style="green")

    def make_layout(self) -> Layout:
        """Create the dashboard layout."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=12)
        )

        layout["body"].split_row(
            Layout(name="agents", ratio=2),
            Layout(name="sidebar", ratio=1)
        )

        layout["footer"].split_row(
            Layout(name="messages", ratio=2),
            Layout(name="events", ratio=1)
        )

        return layout

    def update_layout(self, layout: Layout):
        """Update all panels in the layout."""
        self.poll_data()

        layout["header"].update(self.make_header())
        layout["agents"].update(self.make_agents_table())
        layout["sidebar"].update(self.make_stats_panel())
        layout["messages"].update(self.make_messages_panel())
        layout["events"].update(self.make_events_panel())

    def run(self):
        """Run the dashboard."""
        if not self.connect():
            self.console.print("[bold red]Error:[/] Could not connect to CloveOS kernel")
            self.console.print(f"       Make sure it's running at {self.socket_path}")
            return 1

        layout = self.make_layout()

        try:
            with Live(layout, console=self.console, refresh_per_second=2, screen=True) as live:
                while self.running:
                    try:
                        self.update_layout(layout)
                        time.sleep(0.5)
                    except KeyboardInterrupt:
                        self.running = False
                        break

        except Exception as e:
            self.console.print(f"[bold red]Error:[/] {e}")
            return 1

        finally:
            self.disconnect()

        return 0


def main():
    parser = argparse.ArgumentParser(description="CloveOS Mission Dashboard")
    parser.add_argument("--socket", default="/tmp/clove.sock", help="Kernel socket path")
    args = parser.parse_args()

    dashboard = MissionDashboard(args.socket)
    return dashboard.run()


if __name__ == "__main__":
    sys.exit(main())
