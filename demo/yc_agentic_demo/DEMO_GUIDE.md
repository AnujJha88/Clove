# CloveOS YC Demo Guide

## What It Demonstrates

**4 Agent Types:**
- **Scout Agents** - LLM-powered researchers investigating subtopics
- **Critic Agent** - Fact-checks and verifies findings
- **Synthesizer Agent** - Compiles verified findings into a report
- **Auditor Agent** - Silently observes and logs everything

**Core CloveOS Features:**
1. **Isolation** - Each agent in its own sandbox (namespaces, cgroups v2)
2. **Fair LLM Scheduling** - Kernel-mediated round-robin queue
3. **Auto-Recovery** - Use `--chaos` flag to kill an agent mid-mission and watch it restart
4. **Full Auditability** - Every action logged and replayable

## Demo Flow (~2 min)

```
0:00 - Start with research query
0:10 - Agents spawn (visible in TUI)
0:20 - Scouts research (LLM calls)
0:40 - Critic verifies findings
1:00 - [Optional] Chaos: kill an agent
1:10 - Auto-recovery kicks in
1:30 - Synthesizer compiles report
2:00 - Complete
```

## To Run It

```bash
# Terminal 1: Start kernel
./build/clove_kernel

# Terminal 2: Run demo
cd demo/yc_agentic_demo
./run_demo.sh "What are the latest breakthroughs in protein folding?"

# Or with chaos injection
./run_demo.sh --chaos
```
