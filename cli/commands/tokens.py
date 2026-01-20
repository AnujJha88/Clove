#!/usr/bin/env python3
"""
AgentOS CLI - Token Commands

Manage authentication tokens for machines and agents.
"""

import click
import sys
import secrets
from datetime import datetime
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from cli.relay_api import SyncRelayAPIClient, RelayAPIError
from cli.config import ensure_config_dir


console = Console() if RICH_AVAILABLE else None


def echo(message, style=None):
    """Print message with optional rich styling."""
    if RICH_AVAILABLE and style:
        console.print(message, style=style)
    else:
        click.echo(message)


@click.group()
def tokens():
    """Manage authentication tokens."""
    pass


@tokens.command('create')
@click.argument('token_type', type=click.Choice(['machine', 'agent']))
@click.option('--name', '-n', default='', help='Token name/description')
@click.option('--machine', '-m', help='Machine ID (for agent tokens)')
@click.option('--target-machine', help='Target machine for agent token')
@click.option('--expires', '-e', default=24, type=int,
              help='Token expiration in hours (0 for no expiry)')
@click.option('--relay', '-r', help='Relay server API URL')
@click.option('--local', '-l', is_flag=True, help='Create local token only')
@click.pass_context
def create_token(ctx, token_type, name, machine, target_machine, expires, relay, local):
    """Create a new authentication token."""
    cfg = ctx.obj['config']

    if token_type == 'agent' and not (machine or target_machine):
        echo("Error: --machine or --target-machine required for agent tokens",
             style="bold red")
        sys.exit(1)

    target = machine or target_machine

    if local:
        # Create a local token
        token = secrets.token_urlsafe(32)
        token_id = secrets.token_hex(8)

        # Save to local tokens directory
        ensure_config_dir()
        tokens_dir = Path.home() / '.agentos' / 'tokens'
        tokens_dir.mkdir(exist_ok=True)

        token_file = tokens_dir / f"{token_id}.json"
        import json
        token_data = {
            'id': token_id,
            'type': token_type,
            'name': name or f'{token_type}-token',
            'token': token,
            'created_at': datetime.now().isoformat(),
            'expires_hours': expires
        }

        if token_type == 'agent':
            token_data['target_machine'] = target

        elif token_type == 'machine':
            token_data['machine_id'] = machine if machine else f'local-{token_id[:8]}'

        with open(token_file, 'w') as f:
            json.dump(token_data, f, indent=2)

        echo(f"\nToken created!", style="bold green")
        echo(f"  ID: {token_id}")
        echo(f"  Type: {token_type}")
        echo(f"  Token: {token}")

        if token_type == 'machine':
            echo(f"\nSet environment variables:")
            echo(f"  export MACHINE_ID={token_data['machine_id']}")
            echo(f"  export MACHINE_TOKEN={token}")

        elif token_type == 'agent':
            echo(f"\nSet environment variables:")
            echo(f"  export AGENTOS_MACHINE={target}")
            echo(f"  export AGENTOS_TOKEN={token}")

        return

    # Create via relay API
    relay_url = relay or cfg.relay_api_url

    try:
        client = SyncRelayAPIClient(relay_url, cfg.api_token)

        if token_type == 'machine':
            machine_id = machine or f'new-machine-{secrets.token_hex(4)}'
            result = client.create_machine_token(machine_id, name)

        else:  # agent
            result = client.create_agent_token(target, name, expires)

        token = result.get('token', '')
        token_id = result.get('id', 'unknown')

        echo(f"\nToken created!", style="bold green")
        echo(f"  ID: {token_id}")
        echo(f"  Type: {token_type}")
        echo(f"  Token: {token}")

        if token_type == 'machine':
            machine_id = result.get('machine_id', machine)
            echo(f"\nSet environment variables:")
            echo(f"  export MACHINE_ID={machine_id}")
            echo(f"  export MACHINE_TOKEN={token}")

        elif token_type == 'agent':
            echo(f"\nSet environment variables:")
            echo(f"  export AGENTOS_MACHINE={target}")
            echo(f"  export AGENTOS_TOKEN={token}")

    except RelayAPIError as e:
        echo(f"Error: {e}", style="bold red")
        sys.exit(1)


@tokens.command('list')
@click.option('--relay', '-r', help='Relay server API URL')
@click.option('--local', '-l', is_flag=True, help='List local tokens only')
@click.option('--json', 'as_json', is_flag=True, help='Output as JSON')
@click.pass_context
def list_tokens(ctx, relay, local, as_json):
    """List all tokens."""
    cfg = ctx.obj['config']

    if local:
        _list_local_tokens(as_json)
        return

    relay_url = relay or cfg.relay_api_url

    try:
        client = SyncRelayAPIClient(relay_url, cfg.api_token)
        tokens = client.list_tokens()

        if as_json:
            import json
            click.echo(json.dumps(tokens, indent=2))
            return

        if not tokens:
            echo("No tokens found", style="dim")
            return

        if RICH_AVAILABLE:
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("ID")
            table.add_column("Type")
            table.add_column("Name")
            table.add_column("Target")
            table.add_column("Created")

            for t in tokens:
                table.add_row(
                    t.get('id', '-')[:12],
                    t.get('type', '-'),
                    t.get('name', '-'),
                    t.get('target_machine', t.get('machine_id', '-')),
                    t.get('created_at', '-')[:19]
                )

            console.print(table)
        else:
            for t in tokens:
                click.echo(f"[{t.get('id', '?')[:12]}] {t.get('type', '?')} - {t.get('name', '?')}")

    except RelayAPIError as e:
        if 'Connection' in str(e):
            echo(f"Relay server not reachable at {relay_url}", style="yellow")
            echo("Showing local tokens...\n")
            _list_local_tokens(as_json)
        else:
            echo(f"Error: {e}", style="bold red")
            sys.exit(1)


def _list_local_tokens(as_json):
    """List tokens from local storage."""
    tokens_dir = Path.home() / '.agentos' / 'tokens'

    if not tokens_dir.exists():
        if as_json:
            click.echo("[]")
        else:
            echo("No local tokens found", style="dim")
        return

    import json
    tokens = []

    for token_file in tokens_dir.glob('*.json'):
        try:
            with open(token_file) as f:
                token_data = json.load(f)
                # Hide the actual token in listings
                token_data['token'] = token_data.get('token', '')[:20] + '...'
                tokens.append(token_data)
        except Exception:
            pass

    if as_json:
        click.echo(json.dumps(tokens, indent=2))
        return

    if not tokens:
        echo("No local tokens found", style="dim")
        return

    if RICH_AVAILABLE:
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("ID")
        table.add_column("Type")
        table.add_column("Name")
        table.add_column("Created")

        for t in tokens:
            table.add_row(
                t.get('id', '-')[:12],
                t.get('type', '-'),
                t.get('name', '-'),
                t.get('created_at', '-')[:19]
            )

        console.print(table)
    else:
        for t in tokens:
            click.echo(f"[{t.get('id', '?')[:12]}] {t.get('type', '?')} - {t.get('name', '?')}")


@tokens.command('revoke')
@click.argument('token_id')
@click.option('--relay', '-r', help='Relay server API URL')
@click.option('--local', '-l', is_flag=True, help='Revoke local token only')
@click.option('--force', '-f', is_flag=True, help='Skip confirmation')
@click.pass_context
def revoke_token(ctx, token_id, relay, local, force):
    """Revoke a token."""
    cfg = ctx.obj['config']

    if not force:
        if not click.confirm(f"Revoke token {token_id}?"):
            return

    if local:
        tokens_dir = Path.home() / '.agentos' / 'tokens'
        token_file = tokens_dir / f"{token_id}.json"

        if token_file.exists():
            token_file.unlink()
            echo(f"Token {token_id} revoked", style="green")
        else:
            echo(f"Token not found: {token_id}", style="bold red")
            sys.exit(1)
        return

    relay_url = relay or cfg.relay_api_url

    try:
        client = SyncRelayAPIClient(relay_url, cfg.api_token)
        client.revoke_token(token_id)
        echo(f"Token {token_id} revoked", style="green")

    except RelayAPIError as e:
        echo(f"Error: {e}", style="bold red")
        sys.exit(1)


@tokens.command('show')
@click.argument('token_id')
@click.option('--local', '-l', is_flag=True, help='Show local token')
@click.pass_context
def show_token(ctx, token_id, local):
    """Show token details (including the full token value)."""
    if local:
        tokens_dir = Path.home() / '.agentos' / 'tokens'
        token_file = tokens_dir / f"{token_id}.json"

        if not token_file.exists():
            echo(f"Token not found: {token_id}", style="bold red")
            sys.exit(1)

        import json
        with open(token_file) as f:
            token_data = json.load(f)

        echo(f"\nToken: {token_id}", style="bold blue")
        for key, value in token_data.items():
            echo(f"  {key}: {value}")

    else:
        echo("Use --local flag to view local tokens", style="yellow")
        echo("Remote token details are not available for security reasons")
