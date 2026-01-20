#!/usr/bin/env python3
"""
AgentOS CLI - One-command deploy and manage AgentOS kernels

Usage:
    agentos deploy docker --name dev-kernel
    agentos deploy aws --region us-east-1
    agentos status
    agentos agent run my_agent.py --machine aws-us-east-1-abc123
"""

import click
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from cli.config import Config, get_config
from cli.commands import deploy, status, machines, agent, tokens


@click.group()
@click.option('--config', '-c', type=click.Path(), help='Config file path')
@click.option('--relay', '-r', help='Override relay URL')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.pass_context
def cli(ctx, config, relay, verbose):
    """AgentOS CLI - Deploy and manage AgentOS kernels anywhere."""
    ctx.ensure_object(dict)

    # Load configuration
    cfg = get_config(config)
    ctx.obj['config'] = cfg
    ctx.obj['verbose'] = verbose

    # Override relay URL if provided
    if relay:
        cfg.relay_url = relay


# Register command groups
cli.add_command(deploy.deploy)
cli.add_command(status.status)
cli.add_command(machines.machines)
cli.add_command(agent.agent)
cli.add_command(tokens.tokens)


@cli.command()
@click.pass_context
def config(ctx):
    """Show current configuration."""
    cfg = ctx.obj['config']
    click.echo("AgentOS Configuration:")
    click.echo(f"  Config file: {cfg.config_path}")
    click.echo(f"  Relay URL: {cfg.relay_url}")
    click.echo(f"  Default region (AWS): {cfg.aws_region}")
    click.echo(f"  Default zone (GCP): {cfg.gcp_zone}")


@cli.command('config-set')
@click.argument('key')
@click.argument('value')
@click.pass_context
def config_set(ctx, key, value):
    """Set a configuration value."""
    cfg = ctx.obj['config']

    valid_keys = ['relay_url', 'aws_region', 'gcp_zone', 'gcp_project',
                  'default_instance_type', 'ssh_key_path']

    if key not in valid_keys:
        click.echo(f"Error: Unknown config key '{key}'", err=True)
        click.echo(f"Valid keys: {', '.join(valid_keys)}", err=True)
        sys.exit(1)

    setattr(cfg, key, value)
    cfg.save()
    click.echo(f"Set {key} = {value}")


@cli.command()
def version():
    """Show version information."""
    click.echo("AgentOS CLI v0.1.0")
    click.echo("AgentOS Kernel v0.1.0")


def main():
    """Main entry point."""
    cli(obj={})


if __name__ == '__main__':
    main()
