# CloveOS YC Agentic Demo

Multi-agent research system demonstrating CloveOS's core capabilities for YC interview.

## Quick Start

```bash
# 1. Start the CloveOS kernel (in another terminal)
cd /path/to/CLOVE/build
./clove_kernel

# 2. Run the demo
cd demo/yc_agentic_demo
./run_demo.sh "What are the latest breakthroughs in protein folding?"

# Or with chaos injection (shows auto-recovery)
./run_demo.sh --chaos
```

## What This Demo Shows

### 1. Multi-Agent Coordination
- **Scout Agents** - LLM-powered researchers that investigate subtopics
- **Critic Agent** - Fact-checks and verifies findings
- **Synthesizer Agent** - Compiles verified findings into a coherent report
- **Auditor Agent** - Silently observes and logs everything

### 2. Isolation & Resource Governance
Each agent runs in its own sandbox with:
- Linux namespace isolation (PID, NET, MNT)
- cgroups v2 resource limits (CPU, memory)
- Automatic restart on failure

### 3. Fair LLM Scheduling
When multiple agents need LLM access:
- Round-robin queue ensures no agent starves
- Kernel mediates all LLM calls
- Quota enforcement per agent

### 4. Auto-Recovery
Use `--chaos` flag to demonstrate:
- Agent gets killed mid-mission
- CloveOS detects the failure
- Automatic restart with backoff
- Mission continues without interruption

### 5. Full Auditability
Every action is logged:
- Agent lifecycle events
- IPC messages
- LLM calls and responses
- Resource usage

## Demo Flow (2 minutes)

```
0:00 - Start mission with research query
0:10 - Agents spawn with resource limits (visible in TUI)
0:20 - Scouts begin researching subtopics (LLM calls)
0:40 - Critic verifies findings as they arrive
1:00 - [Optional] Chaos injection - kill an agent
1:10 - Agent auto-recovers and continues
1:30 - Synthesizer compiles final report
1:45 - Audit log generated
2:00 - Mission complete, show outputs
```

## CLI Commands

```bash
# Start a mission
python cli/clove_demo.py mission "Your query here"

# Show agent status
python cli/clove_demo.py status

# Inject chaos (kill and watch recovery)
python cli/clove_demo.py chaos scout_1

# View audit log
python cli/clove_demo.py audit

# Launch TUI dashboard
python cli/clove_demo.py dashboard
```

## Files

```
yc_agentic_demo/
├── mission_control.py      # Main orchestrator
├── run_demo.sh            # Quick-start script
├── agents/
│   ├── scout.py           # Research agent
│   ├── critic.py          # Verification agent
│   ├── synthesizer.py     # Report compiler
│   └── auditor.py         # Observer/logger
├── cli/
│   └── clove_demo.py      # Demo CLI wrapper
├── dashboard/
│   └── mission_tui.py     # Real-time TUI
├── configs/
│   └── limits.json        # Resource limits
└── outputs/               # Generated reports
```

## Key Differentiators vs. Plain Kubernetes

| Feature | Kubernetes | CloveOS |
|---------|------------|---------|
| Isolation granularity | Container-level | Process-level |
| Agent communication | External service mesh | Kernel-mediated IPC |
| LLM access | Each pod manages own | Fair scheduling queue |
| Auto-recovery | Pod restart | In-place process restart |
| Audit trail | Scattered logs | Unified, replayable |
| Resource limits | Per-pod | Per-agent with cgroups |

## Tips for Demo

1. **Start with dashboard visible** - Split terminal, run `python cli/clove_demo.py dashboard`
2. **Use a compelling query** - Something visual like protein folding or AI research
3. **Trigger chaos mid-mission** - Shows reliability in action
4. **Show the final report** - Proves agents produced real output
5. **Quick audit glimpse** - Demonstrates enterprise readiness
