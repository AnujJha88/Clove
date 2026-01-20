#!/usr/bin/env python3
"""
AgentOS CLI - Status Command

Display fleet status and machine information.
"""

import click
import sys
from datetime import datetime

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from cli.relay_api import SyncRelayAPIClient, RelayAPIError


console = Console() if RICH_AVAILABLE else None


def echo(message, style=None):
    """Print message with optional rich styling."""
    if RICH_AVAILABLE and style:
        console.print(message, style=style)
    else:
        click.echo(message)


@click.command()
@click.option('--relay', '-r', help='Relay server API URL')
@click.option('--local', '-l', is_flag=True, help='Show local machine registry only')
@click.option('--json', 'as_json', is_flag=True, help='Output as JSON')
@click.pass_context
def status(ctx, relay, local, as_json):
    """Show fleet status."""
    cfg = ctx.obj['config']

    if local:
        _show_local_status(cfg, as_json)
        return

    # Try to get status from relay server
    relay_url = relay or cfg.relay_api_url

    try:
        client = SyncRelayAPIClient(relay_url, cfg.api_token)
        relay_status = client.get_status()
        machines = client.list_machines()
        agents = client.list_agents()

        if as_json:
            import json
            click.echo(json.dumps({
                'relay_status': relay_status,
                'machines': [m.__dict__ for m in machines],
                'agents': [a.__dict__ for a in agents]
            }, indent=2))
            return

        _show_rich_status(relay_status, machines, agents, cfg)

    except RelayAPIError as e:
        if 'Connection' in str(e):
            echo(f"\nRelay server not reachable at {relay_url}", style="yellow")
            echo("Showing local machine registry...\n")
            _show_local_status(cfg, as_json)
        else:
            echo(f"Error: {e}", style="bold red")
            sys.exit(1)
    except Exception as e:
        echo(f"\nRelay server not reachable: {e}", style="yellow")
        echo("Showing local machine registry...\n")
        _show_local_status(cfg, as_json)


def _show_rich_status(relay_status, machines, agents, cfg):
    """Show status using rich tables."""
    if RICH_AVAILABLE:
        # Header panel
        console.print(Panel.fit(
            "[bold blue]AgentOS Fleet Status[/bold blue]",
            border_style="blue"
        ))

        # Summary
        console.print(f"\n[bold]Connected Kernels:[/bold] {relay_status.get('kernels_connected', 0)}")
        console.print(f"[bold]Active Agents:[/bold] {relay_status.get('remote_agents_connected', 0)}")

        # Machines table
        if machines:
            console.print("\n[bold underline]Machines[/bold underline]")
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Machine ID", style="dim")
            table.add_column("Provider")
            table.add_column("Status")
            table.add_column("IP Address")
            table.add_column("Created")

            for m in machines:
                status_style = "green" if m.status == "running" else "yellow"
                table.add_row(
                    m.machine_id,
                    m.provider,
                    f"[{status_style}]{m.status}[/{status_style}]",
                    m.ip_address or "-",
                    m.created_at[:19] if m.created_at else "-"
                )

            console.print(table)
        else:
            console.print("\n[dim]No machines registered[/dim]")

        # Agents table
        if agents:
            console.print("\n[bold underline]Running Agents[/bold underline]")
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Agent ID", style="dim")
            table.add_column("Name")
            table.add_column("Machine")
            table.add_column("Syscalls")
            table.add_column("Connected")

            for a in agents:
                table.add_row(
                    str(a.agent_id),
                    a.agent_name,
                    a.target_machine,
                    str(a.syscalls_sent),
                    a.connected_at[:19] if a.connected_at else "-"
                )

            console.print(table)
        else:
            console.print("\n[dim]No agents running[/dim]")

        # Local machines not in relay
        local_machines = cfg.list_machines()
        remote_ids = {m.machine_id for m in machines}
        local_only = {k: v for k, v in local_machines.items() if k not in remote_ids}

        if local_only:
            console.print("\n[bold underline]Local Registry (Not Connected)[/bold underline]")
            table = Table(show_header=True, header_style="bold yellow")
            table.add_column("Machine ID", style="dim")
            table.add_column("Provider")
            table.add_column("Status")

            for mid, info in local_only.items():
                table.add_row(
                    mid,
                    info.get('provider', 'unknown'),
                    f"[yellow]offline[/yellow]"
                )

            console.print(table)

    else:
        # Plain text fallback
        _show_plain_status(relay_status, machines, agents, cfg)


def _show_plain_status(relay_status, machines, agents, cfg):
    """Show status using plain text."""
    click.echo("\n=== AgentOS Fleet Status ===\n")

    click.echo(f"Connected Kernels: {relay_status.get('kernels_connected', 0)}")
    click.echo(f"Active Agents: {relay_status.get('remote_agents_connected', 0)}")

    if machines:
        click.echo("\n--- Machines ---")
        for m in machines:
            click.echo(f"  {m.machine_id}")
            click.echo(f"    Provider: {m.provider}")
            click.echo(f"    Status: {m.status}")
            click.echo(f"    IP: {m.ip_address or 'N/A'}")
    else:
        click.echo("\nNo machines registered")

    if agents:
        click.echo("\n--- Running Agents ---")
        for a in agents:
            click.echo(f"  [{a.agent_id}] {a.agent_name} -> {a.target_machine}")
    else:
        click.echo("\nNo agents running")


def _show_local_status(cfg, as_json):
    """Show local machine registry status."""
    machines = cfg.list_machines()

    if as_json:
        import json
        click.echo(json.dumps({'machines': machines}, indent=2))
        return

    if not machines:
        echo("No machines in local registry", style="dim")
        echo("\nDeploy a kernel with:")
        echo("  agentos deploy docker --name my-kernel")
        return

    if RICH_AVAILABLE:
        console.print(Panel.fit(
            "[bold blue]Local Machine Registry[/bold blue]",
            border_style="blue"
        ))

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Machine ID", style="dim")
        table.add_column("Provider")
        table.add_column("Name")
        table.add_column("Status")

        for mid, info in machines.items():
            status = info.get('status', 'unknown')
            status_style = "green" if status == "running" else "yellow"
            table.add_row(
                mid,
                info.get('provider', 'unknown'),
                info.get('name', '-'),
                f"[{status_style}]{status}[/{status_style}]"
            )

        console.print(table)
    else:
        click.echo("\n=== Local Machine Registry ===\n")
        for mid, info in machines.items():
            click.echo(f"  {mid}")
            click.echo(f"    Provider: {info.get('provider', 'unknown')}")
            click.echo(f"    Name: {info.get('name', '-')}")
            click.echo(f"    Status: {info.get('status', 'unknown')}")
