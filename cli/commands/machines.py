#!/usr/bin/env python3
"""
AgentOS CLI - Machines Commands

Manage deployed machines (kernels).
"""

import click
import subprocess
import sys

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
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


@click.group()
def machines():
    """Manage deployed machines."""
    pass


@machines.command('list')
@click.option('--relay', '-r', help='Relay server API URL')
@click.option('--local', '-l', is_flag=True, help='Show local registry only')
@click.option('--json', 'as_json', is_flag=True, help='Output as JSON')
@click.pass_context
def list_machines(ctx, relay, local, as_json):
    """List all machines."""
    cfg = ctx.obj['config']

    if local:
        _list_local_machines(cfg, as_json)
        return

    relay_url = relay or cfg.relay_api_url

    try:
        client = SyncRelayAPIClient(relay_url, cfg.api_token)
        machines = client.list_machines()

        if as_json:
            import json
            click.echo(json.dumps([m.__dict__ for m in machines], indent=2))
            return

        if not machines:
            echo("No machines registered", style="dim")
            return

        if RICH_AVAILABLE:
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Machine ID")
            table.add_column("Provider")
            table.add_column("Status")
            table.add_column("IP Address")
            table.add_column("Last Seen")

            for m in machines:
                status_style = "green" if m.status == "running" else "yellow"
                table.add_row(
                    m.machine_id,
                    m.provider,
                    f"[{status_style}]{m.status}[/{status_style}]",
                    m.ip_address or "-",
                    m.last_seen[:19] if m.last_seen else "-"
                )

            console.print(table)
        else:
            for m in machines:
                click.echo(f"{m.machine_id} ({m.provider}) - {m.status}")

    except RelayAPIError as e:
        echo(f"\nRelay server not reachable: {e}", style="yellow")
        echo("Showing local machine registry...\n")
        _list_local_machines(cfg, as_json)


def _list_local_machines(cfg, as_json):
    """List machines from local registry."""
    machines = cfg.list_machines()

    if as_json:
        import json
        click.echo(json.dumps(machines, indent=2))
        return

    if not machines:
        echo("No machines in local registry", style="dim")
        return

    if RICH_AVAILABLE:
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Machine ID")
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
        for mid, info in machines.items():
            click.echo(f"{mid} ({info.get('provider', '?')}) - {info.get('status', '?')}")


@machines.command('show')
@click.argument('machine_id')
@click.option('--json', 'as_json', is_flag=True, help='Output as JSON')
@click.pass_context
def show_machine(ctx, machine_id, as_json):
    """Show details of a specific machine."""
    cfg = ctx.obj['config']

    # First check local registry
    machine = cfg.get_machine(machine_id)

    if machine:
        if as_json:
            import json
            click.echo(json.dumps({'machine_id': machine_id, **machine}, indent=2))
            return

        if RICH_AVAILABLE:
            console.print(Panel.fit(
                f"[bold blue]{machine_id}[/bold blue]",
                border_style="blue"
            ))

            for key, value in machine.items():
                if key == 'token':
                    value = f"{value[:20]}..." if value else "-"
                console.print(f"  [bold]{key}:[/bold] {value}")
        else:
            click.echo(f"\n=== {machine_id} ===")
            for key, value in machine.items():
                if key == 'token':
                    value = f"{value[:20]}..." if value else "-"
                click.echo(f"  {key}: {value}")
    else:
        echo(f"Machine not found: {machine_id}", style="bold red")
        sys.exit(1)


@machines.command('remove')
@click.argument('machine_id')
@click.option('--force', '-f', is_flag=True, help='Force removal without confirmation')
@click.option('--destroy', '-d', is_flag=True, help='Also destroy cloud resources')
@click.pass_context
def remove_machine(ctx, machine_id, force, destroy):
    """Remove a machine from the fleet."""
    cfg = ctx.obj['config']

    machine = cfg.get_machine(machine_id)

    if not machine:
        echo(f"Machine not found: {machine_id}", style="bold red")
        sys.exit(1)

    if not force:
        if not click.confirm(f"Remove machine {machine_id}?"):
            return

    provider = machine.get('provider', 'unknown')

    if destroy:
        echo(f"Destroying {provider} resources...", style="yellow")

        if provider == 'docker':
            container_name = f"agentos-{machine.get('name', 'kernel')}"
            subprocess.run(['docker', 'rm', '-f', container_name], capture_output=True)
            echo(f"  Removed container: {container_name}")

        elif provider == 'aws':
            echo("  Note: AWS resources must be destroyed via Terraform")
            echo("  Run: cd deploy/terraform/aws && terraform destroy")

        elif provider == 'gcp':
            echo("  Note: GCP resources must be destroyed via Terraform")
            echo("  Run: cd deploy/terraform/gcp && terraform destroy")

    # Remove from local registry
    if cfg.remove_machine(machine_id):
        echo(f"Removed {machine_id} from registry", style="green")
    else:
        echo(f"Failed to remove {machine_id}", style="bold red")
        sys.exit(1)


@machines.command('ssh')
@click.argument('machine_id')
@click.pass_context
def ssh_machine(ctx, machine_id):
    """SSH into a machine."""
    cfg = ctx.obj['config']

    machine = cfg.get_machine(machine_id)

    if not machine:
        echo(f"Machine not found: {machine_id}", style="bold red")
        sys.exit(1)

    provider = machine.get('provider', 'unknown')

    if provider == 'docker':
        container_name = f"agentos-{machine.get('name', 'kernel')}"
        echo(f"Attaching to container: {container_name}")
        subprocess.run(['docker', 'exec', '-it', container_name, '/bin/bash'])

    elif provider == 'aws':
        ip = machine.get('public_ip')
        key_path = cfg.ssh_key_path
        if ip:
            echo(f"SSH to AWS instance: {ip}")
            subprocess.run(['ssh', '-i', key_path, f'ubuntu@{ip}'])
        else:
            echo("No public IP available for this machine", style="bold red")

    elif provider == 'gcp':
        instance_name = machine.get('instance_name')
        zone = machine.get('zone', cfg.gcp_zone)
        if instance_name:
            echo(f"SSH to GCP instance: {instance_name}")
            subprocess.run(['gcloud', 'compute', 'ssh', instance_name, f'--zone={zone}'])
        else:
            echo("No instance name available", style="bold red")

    else:
        echo(f"SSH not supported for provider: {provider}", style="bold red")


@machines.command('logs')
@click.argument('machine_id')
@click.option('--follow', '-f', is_flag=True, help='Follow log output')
@click.option('--tail', '-n', default=100, help='Number of lines to show')
@click.pass_context
def logs_machine(ctx, machine_id, follow, tail):
    """Show logs from a machine."""
    cfg = ctx.obj['config']

    machine = cfg.get_machine(machine_id)

    if not machine:
        echo(f"Machine not found: {machine_id}", style="bold red")
        sys.exit(1)

    provider = machine.get('provider', 'unknown')

    if provider == 'docker':
        container_name = f"agentos-{machine.get('name', 'kernel')}"
        cmd = ['docker', 'logs', f'--tail={tail}']
        if follow:
            cmd.append('-f')
        cmd.append(container_name)
        subprocess.run(cmd)

    else:
        echo(f"Logs command not implemented for provider: {provider}", style="yellow")
        echo("Use SSH to access logs directly")
