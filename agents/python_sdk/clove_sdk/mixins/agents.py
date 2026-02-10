"""Agent management syscalls.

Provides agent lifecycle operations: spawn, kill, pause, resume, list.
"""

from typing import Optional, List, Dict, Any, TYPE_CHECKING

from ..protocol import SyscallOp
from ..models import AgentInfo, SpawnResult, AgentState
from ..exceptions import SyscallError, AgentNotFound, ValidationError

if TYPE_CHECKING:
    from ..transport import Transport


class AgentsMixin:
    """Mixin for agent lifecycle management.

    Requires _transport attribute of type Transport.
    """

    _transport: 'Transport'

    def spawn(
        self,
        name: str,
        script: str,
        sandboxed: bool = True,
        network: bool = False,
        limits: Optional[Dict[str, Any]] = None,
        restart_policy: str = "never",
        max_restarts: int = 5,
        restart_window: int = 300
    ) -> SpawnResult:
        """Spawn a new sandboxed agent.

        Args:
            name: Unique name for the agent
            script: Python script path or inline code
            sandboxed: Enable Linux namespace isolation
            network: Allow network access
            limits: Resource limits dict, e.g. {"memory_mb": 512, "cpu_percent": 50}
            restart_policy: "never", "on_failure", or "always"
            max_restarts: Max restart attempts within window
            restart_window: Restart window in seconds

        Returns:
            SpawnResult with agent_id and pid on success

        Raises:
            SyscallError: If spawn fails
        """
        payload = {
            "name": name,
            "script": script,
            "sandboxed": sandboxed,
            "network": network,
            "restart_policy": restart_policy,
            "max_restarts": max_restarts,
            "restart_window": restart_window
        }
        if limits:
            payload["limits"] = limits

        result = self._transport.call_json(SyscallOp.SYS_SPAWN, payload)

        # Kernel returns "id", not "agent_id"
        # Success is implied if "id" is present (no explicit success field on success)
        agent_id = result.get("id") or result.get("agent_id")
        success = agent_id is not None and "error" not in result

        return SpawnResult(
            success=success,
            agent_id=agent_id,
            pid=result.get("pid"),
            error=result.get("error")
        )

    def kill(self, name: str = None, agent_id: int = None) -> bool:
        """Kill a running agent.

        Args:
            name: Agent name (mutually exclusive with agent_id)
            agent_id: Agent ID (mutually exclusive with name)

        Returns:
            True if agent was killed

        Raises:
            ValidationError: If neither name nor agent_id provided
            AgentNotFound: If agent doesn't exist
        """
        if not name and agent_id is None:
            raise ValidationError("Must provide either name or agent_id")

        payload = {"name": name} if name else {"id": agent_id}
        result = self._transport.call_json(SyscallOp.SYS_KILL, payload)

        if not result.get("killed", False):
            error = result.get("error", "Agent not found")
            raise AgentNotFound(error, opcode=SyscallOp.SYS_KILL)

        return True

    def pause(self, name: str = None, agent_id: int = None) -> bool:
        """Pause a running agent (SIGSTOP).

        Args:
            name: Agent name (mutually exclusive with agent_id)
            agent_id: Agent ID (mutually exclusive with name)

        Returns:
            True if agent was paused

        Raises:
            ValidationError: If neither name nor agent_id provided
            SyscallError: If pause fails
        """
        if not name and agent_id is None:
            raise ValidationError("Must provide either name or agent_id")

        payload = {"name": name} if name else {"id": agent_id}
        result = self._transport.call_json(SyscallOp.SYS_PAUSE, payload)

        if not result.get("success", False):
            raise SyscallError(
                result.get("error", "Pause failed"),
                opcode=SyscallOp.SYS_PAUSE
            )
        return True

    def resume(self, name: str = None, agent_id: int = None) -> bool:
        """Resume a paused agent (SIGCONT).

        Args:
            name: Agent name (mutually exclusive with agent_id)
            agent_id: Agent ID (mutually exclusive with name)

        Returns:
            True if agent was resumed

        Raises:
            ValidationError: If neither name nor agent_id provided
            SyscallError: If resume fails
        """
        if not name and agent_id is None:
            raise ValidationError("Must provide either name or agent_id")

        payload = {"name": name} if name else {"id": agent_id}
        result = self._transport.call_json(SyscallOp.SYS_RESUME, payload)

        if not result.get("success", False):
            raise SyscallError(
                result.get("error", "Resume failed"),
                opcode=SyscallOp.SYS_RESUME
            )
        return True

    def list_agents(self) -> List[AgentInfo]:
        """List all running agents.

        Returns:
            List of AgentInfo objects
        """
        result = self._transport.call_json(SyscallOp.SYS_LIST, {})

        # Handle both list and dict responses
        agents_data = result if isinstance(result, list) else result.get("agents", [])

        agents = []
        for item in agents_data:
            state_str = item.get("state", "running")
            try:
                state = AgentState(state_str)
            except ValueError:
                state = AgentState.RUNNING

            agents.append(AgentInfo(
                id=item.get("id", 0),
                name=item.get("name", ""),
                pid=item.get("pid", 0),
                state=state,
                uptime_seconds=item.get("uptime", 0),
                memory_bytes=item.get("memory"),
                cpu_percent=item.get("cpu")
            ))

        return agents
