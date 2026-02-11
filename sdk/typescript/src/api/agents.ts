/**
 * Agent management API.
 *
 * Provides agent lifecycle operations: spawn, kill, pause, resume, list.
 */

import { SyscallOp } from "../protocol.js";
import { Transport } from "../transport.js";
import {
  AgentInfo,
  AgentState,
  SpawnResult,
  SpawnOptions,
} from "../models.js";
import { SyscallError, AgentNotFoundError, ValidationError } from "../exceptions.js";

export class AgentsAPI {
  constructor(private transport: Transport) {}

  /**
   * Spawn a new sandboxed agent.
   */
  async spawn(options: SpawnOptions): Promise<SpawnResult> {
    const payload: Record<string, unknown> = {
      name: options.name,
      script: options.script,
      sandboxed: options.sandboxed ?? true,
      network: options.network ?? false,
      restart_policy: options.restartPolicy ?? "never",
      max_restarts: options.maxRestarts ?? 5,
      restart_window: options.restartWindow ?? 300,
    };

    if (options.limits) {
      payload.limits = {
        memory_mb: options.limits.memoryMb,
        cpu_percent: options.limits.cpuPercent,
        max_pids: options.limits.maxPids,
      };
    }

    const result = await this.transport.callJson(SyscallOp.SYS_SPAWN, payload);

    const agentId = (result.id ?? result.agent_id) as number | undefined;
    const success = agentId !== undefined && !("error" in result);

    return {
      success,
      agentId,
      pid: result.pid as number | undefined,
      error: result.error as string | undefined,
    };
  }

  /**
   * Kill a running agent.
   */
  async kill(options: { name?: string; agentId?: number }): Promise<boolean> {
    if (!options.name && options.agentId === undefined) {
      throw new ValidationError("Must provide either name or agentId");
    }

    const payload = options.name ? { name: options.name } : { id: options.agentId };
    const result = await this.transport.callJson(SyscallOp.SYS_KILL, payload);

    if (!result.killed) {
      const error = (result.error as string) || "Agent not found";
      throw new AgentNotFoundError(error, SyscallOp.SYS_KILL);
    }

    return true;
  }

  /**
   * Pause a running agent (SIGSTOP).
   */
  async pause(options: { name?: string; agentId?: number }): Promise<boolean> {
    if (!options.name && options.agentId === undefined) {
      throw new ValidationError("Must provide either name or agentId");
    }

    const payload = options.name ? { name: options.name } : { id: options.agentId };
    const result = await this.transport.callJson(SyscallOp.SYS_PAUSE, payload);

    if (!result.success) {
      throw new SyscallError(
        (result.error as string) || "Pause failed",
        SyscallOp.SYS_PAUSE
      );
    }
    return true;
  }

  /**
   * Resume a paused agent (SIGCONT).
   */
  async resume(options: { name?: string; agentId?: number }): Promise<boolean> {
    if (!options.name && options.agentId === undefined) {
      throw new ValidationError("Must provide either name or agentId");
    }

    const payload = options.name ? { name: options.name } : { id: options.agentId };
    const result = await this.transport.callJson(SyscallOp.SYS_RESUME, payload);

    if (!result.success) {
      throw new SyscallError(
        (result.error as string) || "Resume failed",
        SyscallOp.SYS_RESUME
      );
    }
    return true;
  }

  /**
   * List all running agents.
   */
  async list(): Promise<AgentInfo[]> {
    const result = await this.transport.callJson(SyscallOp.SYS_LIST, {});

    const agentsData = Array.isArray(result) ? result : (result.agents as Record<string, unknown>[]) ?? [];

    return agentsData.map((item: Record<string, unknown>) => {
      const stateStr = (item.state as string) || "running";
      let state: AgentState;
      try {
        state = stateStr as AgentState;
      } catch {
        state = AgentState.RUNNING;
      }

      return {
        id: (item.id as number) ?? 0,
        name: (item.name as string) ?? "",
        pid: (item.pid as number) ?? 0,
        state,
        uptimeSeconds: (item.uptime as number) ?? 0,
        memoryBytes: item.memory as number | undefined,
        cpuPercent: item.cpu as number | undefined,
      };
    });
  }
}
