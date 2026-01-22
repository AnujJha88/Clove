# Clove CLI

Command-line tool for managing Clove fleets across local Docker containers and cloud infrastructure.

## Installation

```bash
cd cli
pip install -e .

# Or install dependencies manually
pip install -r requirements.txt
```

## Configuration

Configuration is stored in `~/.clove/config.yaml`.

```bash
# Set relay server URL
clove config set relay_url http://localhost:8766

# Set default region for cloud deployments
clove config set default_region us-east-1

# View all configuration
clove config show
```

## Commands

### Deploy

Deploy Clove kernels to various environments.

#### Docker

```bash
# Deploy a local Docker container
clove deploy docker --name my-kernel

# With custom relay URL
clove deploy docker --name my-kernel --relay-url ws://relay.example.com:8765
```

#### AWS

```bash
# Deploy to AWS EC2
clove deploy aws --region us-east-1

# With custom instance type
clove deploy aws --region us-west-2 --instance-type t3.small

# With custom name
clove deploy aws --region us-east-1 --name production-kernel
```

#### GCP

```bash
# Deploy to GCP Compute Engine
clove deploy gcp --zone us-central1-a

# With custom machine type
clove deploy gcp --zone europe-west1-b --machine-type n1-standard-2
```

### Status

View fleet status.

```bash
$ clove status

 Clove Fleet Status
┏━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Machine ID            ┃ Provider   ┃ Status      ┃ Agents      ┃
┡━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ docker-dev-abc123     │ docker     │ connected   │ 2           │
│ aws-i-0def456-us-e1   │ aws        │ connected   │ 0           │
│ gcp-inst-xyz-us-c1    │ gcp        │ disconnected│ 0           │
└───────────────────────┴────────────┴─────────────┴─────────────┘
```

### Machines

Manage fleet machines.

```bash
# List all machines
clove machines list

# Show detailed info for a machine
clove machines show docker-dev-abc123

# Remove a machine from the fleet
clove machines remove docker-dev-abc123

# SSH into a machine (cloud only)
clove machines ssh aws-i-0def456-us-e1

# View machine logs
clove machines logs docker-dev-abc123
```

### Agents

Run and manage agents.

```bash
# Run agent on a specific machine
clove agent run my_agent.py --machine docker-dev-abc123

# Run agent on all connected machines
clove agent run health_check.py --all

# Run with arguments
clove agent run my_agent.py --machine m1 -- --verbose --count 10

# List running agents
clove agent list

# List agents on a specific machine
clove agent list --machine docker-dev-abc123

# Stop an agent
clove agent stop docker-dev-abc123 42

# Create a new agent template
clove agent create my_new_agent
```

### Tokens

Manage authentication tokens.

```bash
# Create a machine token (for new kernels)
clove tokens create machine --name production-server

# Create an agent token
clove tokens create agent --target-machine docker-dev-abc123

# Create an admin token
clove tokens create admin --name fleet-admin

# List all tokens
clove tokens list

# Revoke a token
clove tokens revoke tok_abc123def456
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `RELAY_API_URL` | Relay server REST API URL | `http://localhost:8766` |
| `AGENTOS_API_TOKEN` | Authentication token | (none) |
| `AWS_REGION` | Default AWS region | `us-east-1` |
| `GCP_PROJECT` | GCP project ID | (none) |
| `GCP_ZONE` | Default GCP zone | `us-central1-a` |

## File Structure

```
cli/
├── clove.py           # Main entry point
├── config.py            # Configuration management
├── relay_api.py         # REST API client
├── requirements.txt     # Python dependencies
├── setup.py             # Package setup
└── commands/
    ├── deploy.py        # deploy docker|aws|gcp
    ├── status.py        # status display
    ├── machines.py      # machines list|show|remove|ssh|logs
    ├── agent.py         # agent run|list|stop|create
    └── tokens.py        # tokens create|list|revoke
```

## REST API Endpoints

The CLI communicates with the relay server via REST API.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check |
| `/api/v1/status` | GET | Fleet status |
| `/api/v1/machines` | GET | List machines |
| `/api/v1/machines/{id}` | GET | Get machine |
| `/api/v1/machines/{id}` | DELETE | Remove machine |
| `/api/v1/agents` | GET | List agents |
| `/api/v1/agents/deploy` | POST | Deploy agent |
| `/api/v1/agents/{id}/stop` | POST | Stop agent |
| `/api/v1/tokens` | GET | List tokens |
| `/api/v1/tokens` | POST | Create token |
| `/api/v1/tokens/{id}` | DELETE | Revoke token |

## Examples

### Deploy and Run

```bash
# Deploy a kernel
clove deploy docker --name dev

# Run an agent
clove agent run agents/examples/hello_agent.py --machine docker-dev-*

# Check status
clove status
```

### Multi-Machine Deployment

```bash
# Deploy multiple machines
clove deploy docker --name worker-1
clove deploy docker --name worker-2
clove deploy docker --name worker-3

# Run health check on all
clove agent run agents/examples/health_check.py --all
```

### Cloud Deployment

```bash
# Deploy to AWS
clove deploy aws --region us-east-1 --name prod-east

# Deploy to GCP
clove deploy gcp --zone europe-west1-b --name prod-europe

# View fleet
clove status
```

## Troubleshooting

### Connection Refused

```
Error: Connection refused to http://localhost:8766
```

Start the relay server:
```bash
cd relay && python relay_server.py
```

### Authentication Failed

```
Error: Authentication failed
```

Create and configure a token:
```bash
clove tokens create admin --name my-admin
# Copy the displayed token
clove config set api_token <token>
```

### Machine Not Found

```
Error: Machine docker-dev-abc123 not found
```

Check machine status:
```bash
clove machines list
```

The machine may be disconnected. Check the kernel logs on that machine.
