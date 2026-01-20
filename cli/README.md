# AgentOS CLI

Command-line tool for managing AgentOS fleets across local Docker containers and cloud infrastructure.

## Installation

```bash
cd cli
pip install -e .

# Or install dependencies manually
pip install -r requirements.txt
```

## Configuration

Configuration is stored in `~/.agentos/config.yaml`.

```bash
# Set relay server URL
agentos config set relay_url http://localhost:8766

# Set default region for cloud deployments
agentos config set default_region us-east-1

# View all configuration
agentos config show
```

## Commands

### Deploy

Deploy AgentOS kernels to various environments.

#### Docker

```bash
# Deploy a local Docker container
agentos deploy docker --name my-kernel

# With custom relay URL
agentos deploy docker --name my-kernel --relay-url ws://relay.example.com:8765
```

#### AWS

```bash
# Deploy to AWS EC2
agentos deploy aws --region us-east-1

# With custom instance type
agentos deploy aws --region us-west-2 --instance-type t3.small

# With custom name
agentos deploy aws --region us-east-1 --name production-kernel
```

#### GCP

```bash
# Deploy to GCP Compute Engine
agentos deploy gcp --zone us-central1-a

# With custom machine type
agentos deploy gcp --zone europe-west1-b --machine-type n1-standard-2
```

### Status

View fleet status.

```bash
$ agentos status

 AgentOS Fleet Status
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
agentos machines list

# Show detailed info for a machine
agentos machines show docker-dev-abc123

# Remove a machine from the fleet
agentos machines remove docker-dev-abc123

# SSH into a machine (cloud only)
agentos machines ssh aws-i-0def456-us-e1

# View machine logs
agentos machines logs docker-dev-abc123
```

### Agents

Run and manage agents.

```bash
# Run agent on a specific machine
agentos agent run my_agent.py --machine docker-dev-abc123

# Run agent on all connected machines
agentos agent run health_check.py --all

# Run with arguments
agentos agent run my_agent.py --machine m1 -- --verbose --count 10

# List running agents
agentos agent list

# List agents on a specific machine
agentos agent list --machine docker-dev-abc123

# Stop an agent
agentos agent stop docker-dev-abc123 42

# Create a new agent template
agentos agent create my_new_agent
```

### Tokens

Manage authentication tokens.

```bash
# Create a machine token (for new kernels)
agentos tokens create machine --name production-server

# Create an agent token
agentos tokens create agent --target-machine docker-dev-abc123

# Create an admin token
agentos tokens create admin --name fleet-admin

# List all tokens
agentos tokens list

# Revoke a token
agentos tokens revoke tok_abc123def456
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
├── agentos.py           # Main entry point
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
agentos deploy docker --name dev

# Run an agent
agentos agent run agents/examples/hello_agent.py --machine docker-dev-*

# Check status
agentos status
```

### Multi-Machine Deployment

```bash
# Deploy multiple machines
agentos deploy docker --name worker-1
agentos deploy docker --name worker-2
agentos deploy docker --name worker-3

# Run health check on all
agentos agent run agents/examples/health_check.py --all
```

### Cloud Deployment

```bash
# Deploy to AWS
agentos deploy aws --region us-east-1 --name prod-east

# Deploy to GCP
agentos deploy gcp --zone europe-west1-b --name prod-europe

# View fleet
agentos status
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
agentos tokens create admin --name my-admin
# Copy the displayed token
agentos config set api_token <token>
```

### Machine Not Found

```
Error: Machine docker-dev-abc123 not found
```

Check machine status:
```bash
agentos machines list
```

The machine may be disconnected. Check the kernel logs on that machine.
