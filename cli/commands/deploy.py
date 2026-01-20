#!/usr/bin/env python3
"""
AgentOS CLI - Deploy Commands

Deploy AgentOS kernels to Docker, AWS, or GCP.
"""

import click
import subprocess
import json
import secrets
import sys
import os
import time
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

console = Console() if RICH_AVAILABLE else None


def echo(message, style=None):
    """Print message with optional rich styling."""
    if RICH_AVAILABLE and style:
        console.print(message, style=style)
    else:
        click.echo(message)


def generate_machine_id(provider: str, name: str) -> str:
    """Generate a unique machine ID."""
    suffix = secrets.token_hex(4)
    return f"{provider}-{name}-{suffix}"


def generate_token() -> str:
    """Generate a secure token."""
    return secrets.token_urlsafe(32)


@click.group()
def deploy():
    """Deploy AgentOS kernels to various platforms."""
    pass


# =============================================================================
# Docker Deployment
# =============================================================================

@deploy.command('docker')
@click.option('--name', '-n', default='kernel', help='Container name')
@click.option('--port', '-p', default=9000, type=int, help='Host port')
@click.option('--relay', '-r', help='Relay server URL')
@click.option('--build', '-b', is_flag=True, help='Build kernel first')
@click.option('--detach/--no-detach', default=True, help='Run in background')
@click.pass_context
def deploy_docker(ctx, name, port, relay, build, detach):
    """Deploy AgentOS kernel in a Docker container."""
    cfg = ctx.obj['config']

    machine_id = generate_machine_id('docker', name)
    token = generate_token()

    echo(f"\nDeploying AgentOS kernel to Docker...", style="bold blue")
    echo(f"  Container name: agentos-{name}")
    echo(f"  Machine ID: {machine_id}")

    # Check if Docker is available
    try:
        subprocess.run(['docker', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        echo("Error: Docker is not installed or not running", style="bold red")
        sys.exit(1)

    # Build kernel if requested
    if build:
        echo("\nBuilding AgentOS kernel...")
        project_root = Path(__file__).parent.parent.parent
        build_result = subprocess.run(
            ['cmake', '--build', str(project_root / 'build')],
            cwd=project_root
        )
        if build_result.returncode != 0:
            echo("Error: Build failed", style="bold red")
            sys.exit(1)

    # Check if Dockerfile exists
    project_root = Path(__file__).parent.parent.parent
    dockerfile = project_root / 'deploy' / 'docker' / 'Dockerfile'

    if not dockerfile.exists():
        echo(f"Error: Dockerfile not found at {dockerfile}", style="bold red")
        echo("Run 'agentos deploy docker --build' first or create the Dockerfile")
        sys.exit(1)

    # Build the Docker image
    echo("\nBuilding Docker image...")
    build_cmd = [
        'docker', 'build',
        '-t', f'agentos/kernel:{name}',
        '-f', str(dockerfile),
        str(project_root)
    ]

    result = subprocess.run(build_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        echo(f"Error building Docker image: {result.stderr}", style="bold red")
        sys.exit(1)

    # Stop existing container if running
    subprocess.run(
        ['docker', 'rm', '-f', f'agentos-{name}'],
        capture_output=True
    )

    # Determine relay URL
    relay_url = relay or cfg.relay_url

    # Run the container
    echo("\nStarting container...")
    run_cmd = [
        'docker', 'run',
        '--name', f'agentos-{name}',
        '-e', f'MACHINE_ID={machine_id}',
        '-e', f'MACHINE_TOKEN={token}',
        '-e', f'RELAY_URL={relay_url}',
        '-p', f'{port}:9000',
        '--restart', 'unless-stopped',
    ]

    if detach:
        run_cmd.append('-d')

    run_cmd.append(f'agentos/kernel:{name}')

    result = subprocess.run(run_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        echo(f"Error starting container: {result.stderr}", style="bold red")
        sys.exit(1)

    container_id = result.stdout.strip()[:12]

    # Save machine info
    cfg.add_machine(machine_id, {
        'provider': 'docker',
        'name': name,
        'container_id': container_id,
        'token': token,
        'port': port,
        'relay_url': relay_url,
        'status': 'running'
    })

    echo(f"\n{'='*50}", style="green")
    echo("AgentOS kernel deployed successfully!", style="bold green")
    echo(f"{'='*50}", style="green")
    echo(f"\n  Machine ID: {machine_id}")
    echo(f"  Container: agentos-{name}")
    echo(f"  Port: {port}")
    echo(f"  Token: {token[:20]}...")
    echo(f"\nTo connect an agent:")
    echo(f"  export AGENTOS_MACHINE={machine_id}")
    echo(f"  export AGENTOS_TOKEN={token}")
    echo(f"  python my_agent.py")


# =============================================================================
# AWS Deployment
# =============================================================================

@deploy.command('aws')
@click.option('--region', '-r', help='AWS region (default: us-east-1)')
@click.option('--instance-type', '-t', default='t3.micro', help='EC2 instance type')
@click.option('--name', '-n', default='kernel', help='Instance name')
@click.option('--key-name', '-k', help='SSH key pair name')
@click.option('--security-group', '-sg', help='Security group ID')
@click.option('--subnet', '-s', help='Subnet ID')
@click.option('--relay', help='Relay server URL')
@click.pass_context
def deploy_aws(ctx, region, instance_type, name, key_name, security_group, subnet, relay):
    """Deploy AgentOS kernel to AWS EC2."""
    cfg = ctx.obj['config']

    region = region or cfg.aws_region
    machine_id = generate_machine_id('aws', name)
    token = generate_token()

    echo(f"\nDeploying AgentOS kernel to AWS EC2...", style="bold blue")
    echo(f"  Region: {region}")
    echo(f"  Instance type: {instance_type}")
    echo(f"  Machine ID: {machine_id}")

    # Check if AWS CLI is available
    try:
        subprocess.run(['aws', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        echo("Error: AWS CLI is not installed", style="bold red")
        echo("Install with: pip install awscli && aws configure")
        sys.exit(1)

    # Check if Terraform is available
    try:
        subprocess.run(['terraform', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        echo("Error: Terraform is not installed", style="bold red")
        echo("Install from: https://www.terraform.io/downloads")
        sys.exit(1)

    # Get the Terraform directory
    project_root = Path(__file__).parent.parent.parent
    tf_dir = project_root / 'deploy' / 'terraform' / 'aws'

    if not tf_dir.exists():
        echo(f"Error: Terraform directory not found at {tf_dir}", style="bold red")
        sys.exit(1)

    # Determine relay URL
    relay_url = relay or cfg.relay_url

    # Create tfvars file
    tfvars = {
        'machine_id': machine_id,
        'machine_token': token,
        'relay_url': relay_url,
        'instance_type': instance_type,
        'region': region,
        'instance_name': f'agentos-{name}'
    }

    if key_name:
        tfvars['key_name'] = key_name
    if security_group:
        tfvars['security_group_id'] = security_group
    if subnet:
        tfvars['subnet_id'] = subnet

    tfvars_file = tf_dir / 'terraform.tfvars.json'
    with open(tfvars_file, 'w') as f:
        json.dump(tfvars, f, indent=2)

    # Initialize Terraform
    echo("\nInitializing Terraform...")
    init_result = subprocess.run(
        ['terraform', 'init'],
        cwd=tf_dir,
        capture_output=True,
        text=True
    )

    if init_result.returncode != 0:
        echo(f"Error: Terraform init failed: {init_result.stderr}", style="bold red")
        sys.exit(1)

    # Apply Terraform
    echo("Provisioning AWS resources...")
    apply_result = subprocess.run(
        ['terraform', 'apply', '-auto-approve'],
        cwd=tf_dir,
        capture_output=True,
        text=True
    )

    if apply_result.returncode != 0:
        echo(f"Error: Terraform apply failed: {apply_result.stderr}", style="bold red")
        sys.exit(1)

    # Get outputs
    output_result = subprocess.run(
        ['terraform', 'output', '-json'],
        cwd=tf_dir,
        capture_output=True,
        text=True
    )

    outputs = json.loads(output_result.stdout) if output_result.stdout else {}

    instance_id = outputs.get('instance_id', {}).get('value', 'unknown')
    public_ip = outputs.get('public_ip', {}).get('value', 'unknown')

    # Save machine info
    cfg.add_machine(machine_id, {
        'provider': 'aws',
        'name': name,
        'instance_id': instance_id,
        'public_ip': public_ip,
        'region': region,
        'instance_type': instance_type,
        'token': token,
        'relay_url': relay_url,
        'status': 'running'
    })

    echo(f"\n{'='*50}", style="green")
    echo("AgentOS kernel deployed to AWS!", style="bold green")
    echo(f"{'='*50}", style="green")
    echo(f"\n  Machine ID: {machine_id}")
    echo(f"  Instance ID: {instance_id}")
    echo(f"  Public IP: {public_ip}")
    echo(f"  Region: {region}")
    echo(f"  Token: {token[:20]}...")

    if key_name:
        echo(f"\nSSH access:")
        echo(f"  ssh -i ~/.ssh/{key_name}.pem ubuntu@{public_ip}")


# =============================================================================
# GCP Deployment
# =============================================================================

@deploy.command('gcp')
@click.option('--project', '-p', help='GCP project ID')
@click.option('--zone', '-z', help='GCP zone (default: us-central1-a)')
@click.option('--machine-type', '-t', default='n1-standard-1', help='Machine type')
@click.option('--name', '-n', default='kernel', help='Instance name')
@click.option('--relay', help='Relay server URL')
@click.pass_context
def deploy_gcp(ctx, project, zone, machine_type, name, relay):
    """Deploy AgentOS kernel to Google Cloud Platform."""
    cfg = ctx.obj['config']

    project = project or cfg.gcp_project
    zone = zone or cfg.gcp_zone
    machine_id = generate_machine_id('gcp', name)
    token = generate_token()

    if not project:
        echo("Error: GCP project ID is required", style="bold red")
        echo("Set with: agentos config-set gcp_project YOUR_PROJECT_ID")
        sys.exit(1)

    echo(f"\nDeploying AgentOS kernel to GCP...", style="bold blue")
    echo(f"  Project: {project}")
    echo(f"  Zone: {zone}")
    echo(f"  Machine type: {machine_type}")
    echo(f"  Machine ID: {machine_id}")

    # Check if gcloud is available
    try:
        subprocess.run(['gcloud', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        echo("Error: Google Cloud SDK is not installed", style="bold red")
        echo("Install from: https://cloud.google.com/sdk/docs/install")
        sys.exit(1)

    # Check if Terraform is available
    try:
        subprocess.run(['terraform', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        echo("Error: Terraform is not installed", style="bold red")
        echo("Install from: https://www.terraform.io/downloads")
        sys.exit(1)

    # Get the Terraform directory
    project_root = Path(__file__).parent.parent.parent
    tf_dir = project_root / 'deploy' / 'terraform' / 'gcp'

    if not tf_dir.exists():
        echo(f"Error: Terraform directory not found at {tf_dir}", style="bold red")
        sys.exit(1)

    # Determine relay URL
    relay_url = relay or cfg.relay_url

    # Create tfvars file
    tfvars = {
        'machine_id': machine_id,
        'machine_token': token,
        'relay_url': relay_url,
        'project_id': project,
        'zone': zone,
        'machine_type': machine_type,
        'instance_name': f'agentos-{name}'
    }

    tfvars_file = tf_dir / 'terraform.tfvars.json'
    with open(tfvars_file, 'w') as f:
        json.dump(tfvars, f, indent=2)

    # Initialize Terraform
    echo("\nInitializing Terraform...")
    init_result = subprocess.run(
        ['terraform', 'init'],
        cwd=tf_dir,
        capture_output=True,
        text=True
    )

    if init_result.returncode != 0:
        echo(f"Error: Terraform init failed: {init_result.stderr}", style="bold red")
        sys.exit(1)

    # Apply Terraform
    echo("Provisioning GCP resources...")
    apply_result = subprocess.run(
        ['terraform', 'apply', '-auto-approve'],
        cwd=tf_dir,
        capture_output=True,
        text=True
    )

    if apply_result.returncode != 0:
        echo(f"Error: Terraform apply failed: {apply_result.stderr}", style="bold red")
        sys.exit(1)

    # Get outputs
    output_result = subprocess.run(
        ['terraform', 'output', '-json'],
        cwd=tf_dir,
        capture_output=True,
        text=True
    )

    outputs = json.loads(output_result.stdout) if output_result.stdout else {}

    instance_name = outputs.get('instance_name', {}).get('value', f'agentos-{name}')
    external_ip = outputs.get('external_ip', {}).get('value', 'unknown')

    # Save machine info
    cfg.add_machine(machine_id, {
        'provider': 'gcp',
        'name': name,
        'instance_name': instance_name,
        'external_ip': external_ip,
        'project': project,
        'zone': zone,
        'machine_type': machine_type,
        'token': token,
        'relay_url': relay_url,
        'status': 'running'
    })

    echo(f"\n{'='*50}", style="green")
    echo("AgentOS kernel deployed to GCP!", style="bold green")
    echo(f"{'='*50}", style="green")
    echo(f"\n  Machine ID: {machine_id}")
    echo(f"  Instance: {instance_name}")
    echo(f"  External IP: {external_ip}")
    echo(f"  Zone: {zone}")
    echo(f"  Token: {token[:20]}...")
    echo(f"\nSSH access:")
    echo(f"  gcloud compute ssh {instance_name} --zone={zone}")
