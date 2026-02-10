"""Metrics syscalls.

Provides system and agent metrics collection.
"""

from typing import Optional, List, TYPE_CHECKING

from ..protocol import SyscallOp
from ..models import (
    SystemMetrics,
    AgentMetrics,
    AllAgentsMetrics,
    CgroupMetrics,
)

if TYPE_CHECKING:
    from ..transport import Transport


class MetricsMixin:
    """Mixin for metrics collection operations.

    Requires _transport attribute of type Transport.
    """

    _transport: 'Transport'

    def get_system_metrics(self) -> SystemMetrics:
        """Get system-wide metrics (CPU, memory, disk, network).

        Returns:
            SystemMetrics with current system stats
        """
        result = self._transport.call_json(SyscallOp.SYS_METRICS_SYSTEM, {})

        # Kernel wraps response in "metrics" object with nested structure
        metrics = result.get("metrics", result)
        cpu = metrics.get("cpu", {})
        memory = metrics.get("memory", {})
        disk = metrics.get("disk", {})
        network = metrics.get("network", {})

        return SystemMetrics(
            success=result.get("success", True),
            cpu_percent=cpu.get("percent", 0.0),
            memory_used_bytes=memory.get("used", 0),
            memory_total_bytes=memory.get("total", 0),
            memory_percent=memory.get("percent", 0.0),
            disk_used_bytes=disk.get("read_bytes", 0) + disk.get("write_bytes", 0),
            disk_total_bytes=0,  # Not provided by kernel
            disk_percent=0.0,  # Not provided by kernel
            network_rx_bytes=network.get("bytes_recv", 0),
            network_tx_bytes=network.get("bytes_sent", 0),
            load_average=cpu.get("load_avg", []),
            error=result.get("error")
        )

    def get_agent_metrics(self, agent_id: Optional[int] = None) -> AgentMetrics:
        """Get metrics for a specific agent.

        Args:
            agent_id: Target agent ID (default: self)

        Returns:
            AgentMetrics with agent-specific stats
        """
        payload = {}
        if agent_id is not None:
            payload["agent_id"] = agent_id

        result = self._transport.call_json(SyscallOp.SYS_METRICS_AGENT, payload)

        # Kernel wraps response in "metrics" object with nested structure
        metrics = result.get("metrics", result)
        process = metrics.get("process", {})
        process_cpu = process.get("cpu", {})
        process_mem = process.get("memory", {})
        kernel_stats = metrics.get("kernel_stats", {})

        return AgentMetrics(
            agent_id=metrics.get("agent_id", agent_id or 0),
            name=metrics.get("name", ""),
            cpu_percent=process_cpu.get("percent", 0.0),
            memory_bytes=process_mem.get("rss", 0),
            memory_percent=process_mem.get("percent", 0.0),
            syscalls_count=kernel_stats.get("syscall_count", 0),
            uptime_seconds=metrics.get("uptime_ms", 0) / 1000.0,
            state=metrics.get("status", "unknown")
        )

    def get_all_agent_metrics(self) -> AllAgentsMetrics:
        """Get metrics for all running agents.

        Returns:
            AllAgentsMetrics with list of agent metrics
        """
        result = self._transport.call_json(SyscallOp.SYS_METRICS_ALL_AGENTS, {})

        # Kernel returns agents array with each item as agent metrics.to_json()
        agents: List[AgentMetrics] = []
        for agent_data in result.get("agents", []):
            process = agent_data.get("process", {})
            process_cpu = process.get("cpu", {})
            process_mem = process.get("memory", {})
            kernel_stats = agent_data.get("kernel_stats", {})

            agents.append(AgentMetrics(
                agent_id=agent_data.get("agent_id", 0),
                name=agent_data.get("name", ""),
                cpu_percent=process_cpu.get("percent", 0.0),
                memory_bytes=process_mem.get("rss", 0),
                memory_percent=process_mem.get("percent", 0.0),
                syscalls_count=kernel_stats.get("syscall_count", 0),
                uptime_seconds=agent_data.get("uptime_ms", 0) / 1000.0,
                state=agent_data.get("status", "unknown")
            ))

        return AllAgentsMetrics(
            success=result.get("success", False),
            agents=agents,
            count=result.get("count", len(agents)),
            error=result.get("error")
        )

    def get_cgroup_metrics(self, cgroup_path: Optional[str] = None) -> CgroupMetrics:
        """Get cgroup metrics for a sandboxed process.

        Args:
            cgroup_path: Path to cgroup (default: own cgroup)

        Returns:
            CgroupMetrics with resource usage
        """
        payload = {}
        if cgroup_path:
            payload["cgroup_path"] = cgroup_path

        result = self._transport.call_json(SyscallOp.SYS_METRICS_CGROUP, payload)

        # Kernel wraps response in "metrics" object with nested structure
        metrics = result.get("metrics", result)
        cpu = metrics.get("cpu", {})
        memory = metrics.get("memory", {})
        pids = metrics.get("pids", {})

        return CgroupMetrics(
            success=result.get("success", False),
            cpu_usage_usec=cpu.get("usage_usec", 0),
            memory_current=memory.get("current", 0),
            memory_limit=memory.get("max", 0),
            pids_current=pids.get("current", 0),
            pids_limit=pids.get("max", 0),
            error=result.get("error")
        )
