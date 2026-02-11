/**
 * Metrics API.
 *
 * Provides system and agent metrics collection.
 */

import { SyscallOp } from "../protocol.js";
import { Transport } from "../transport.js";
import {
  SystemMetrics,
  AgentMetrics,
  AllAgentsMetrics,
  CgroupMetrics,
} from "../models.js";

export class MetricsAPI {
  constructor(private transport: Transport) {}

  /**
   * Get system-wide metrics.
   */
  async getSystemMetrics(): Promise<SystemMetrics> {
    const result = await this.transport.callJson(SyscallOp.SYS_METRICS_SYSTEM, {});

    return {
      success: (result.success as boolean) ?? true,
      cpuPercent: (result.cpu_percent as number) ?? 0,
      memoryUsedBytes: (result.memory_used_bytes as number) ?? 0,
      memoryTotalBytes: (result.memory_total_bytes as number) ?? 0,
      memoryPercent: (result.memory_percent as number) ?? 0,
      diskUsedBytes: (result.disk_used_bytes as number) ?? 0,
      diskTotalBytes: (result.disk_total_bytes as number) ?? 0,
      diskPercent: (result.disk_percent as number) ?? 0,
      networkRxBytes: (result.network_rx_bytes as number) ?? 0,
      networkTxBytes: (result.network_tx_bytes as number) ?? 0,
      loadAverage: (result.load_average as number[]) ?? [],
      error: result.error as string | undefined,
    };
  }

  /**
   * Get metrics for a specific agent.
   */
  async getAgentMetrics(agentId: number): Promise<AgentMetrics> {
    const result = await this.transport.callJson(SyscallOp.SYS_METRICS_AGENT, {
      agent_id: agentId,
    });

    return {
      agentId: (result.agent_id as number) ?? agentId,
      name: (result.name as string) ?? "",
      cpuPercent: (result.cpu_percent as number) ?? 0,
      memoryBytes: (result.memory_bytes as number) ?? 0,
      memoryPercent: (result.memory_percent as number) ?? 0,
      syscallsCount: (result.syscalls_count as number) ?? 0,
      uptimeSeconds: (result.uptime_seconds as number) ?? 0,
      state: (result.state as string) ?? "unknown",
    };
  }

  /**
   * Get metrics for all agents.
   */
  async getAllAgentsMetrics(): Promise<AllAgentsMetrics> {
    const result = await this.transport.callJson(SyscallOp.SYS_METRICS_ALL_AGENTS, {});

    const agentsData = (result.agents as Record<string, unknown>[]) ?? [];
    const agents: AgentMetrics[] = agentsData.map((a) => ({
      agentId: (a.agent_id as number) ?? 0,
      name: (a.name as string) ?? "",
      cpuPercent: (a.cpu_percent as number) ?? 0,
      memoryBytes: (a.memory_bytes as number) ?? 0,
      memoryPercent: (a.memory_percent as number) ?? 0,
      syscallsCount: (a.syscalls_count as number) ?? 0,
      uptimeSeconds: (a.uptime_seconds as number) ?? 0,
      state: (a.state as string) ?? "unknown",
    }));

    return {
      success: (result.success as boolean) ?? false,
      agents,
      count: (result.count as number) ?? agents.length,
      error: result.error as string | undefined,
    };
  }

  /**
   * Get cgroup metrics.
   */
  async getCgroupMetrics(agentId?: number): Promise<CgroupMetrics> {
    const payload: Record<string, unknown> = {};
    if (agentId !== undefined) {
      payload.agent_id = agentId;
    }

    const result = await this.transport.callJson(SyscallOp.SYS_METRICS_CGROUP, payload);

    return {
      success: (result.success as boolean) ?? false,
      cpuUsageUsec: (result.cpu_usage_usec as number) ?? 0,
      memoryCurrent: (result.memory_current as number) ?? 0,
      memoryLimit: (result.memory_limit as number) ?? 0,
      pidsCurrent: (result.pids_current as number) ?? 0,
      pidsLimit: (result.pids_limit as number) ?? 0,
      error: result.error as string | undefined,
    };
  }
}
