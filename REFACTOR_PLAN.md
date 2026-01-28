# CLOVE Kernel Refactor Plan

## Goals
- Improve modularity and SOLID adherence.
- Reduce the Kernel class surface area.
- Keep behavior stable while enabling scalability improvements.

## Staged Plan
1) Baseline inventory: map syscall groups, shared state structures, and blocking operations to define refactor boundaries and priorities.
2) Introduce SyscallRouter and register handlers; keep existing handler methods but remove the giant switch for OCP compliance.
3) Extract cross-cutting stores/services (StateStore, EventBus, Mailbox/Registry, Permissions) from Kernel into dedicated classes with clear interfaces.
4) Split syscall handlers into module classes (e.g., FileSyscalls, AgentSyscalls, IPCSyscalls, NetworkSyscalls, WorldSyscalls, MetricsSyscalls, ReplaySyscalls).
5) Add async execution layer for blocking work (EXEC/HTTP/LLM) using worker threads or a task queue; keep the reactor non-blocking.
6) Improve configuration + dependency injection (construct services outside Kernel, pass via interfaces, enable testing).
7) Add/adjust tests for the new boundaries and update SYSTEM_DESIGN.md to match the modular architecture.

## Notes
- Each step should be independently buildable and testable.
- Preserve external behavior until step 5 introduces async execution.
