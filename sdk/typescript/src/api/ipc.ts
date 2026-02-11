/**
 * Inter-Process Communication (IPC) API.
 *
 * Provides messaging between agents.
 */

import { SyscallOp } from "../protocol.js";
import { Transport } from "../transport.js";
import {
  IPCMessage,
  SendResult,
  RecvResult,
  BroadcastResult,
  RegisterResult,
} from "../models.js";

export class IPCAPI {
  constructor(private transport: Transport) {}

  /**
   * Send a message to another agent.
   */
  async send(
    target: { name?: string; agentId?: number },
    message: Record<string, unknown>
  ): Promise<SendResult> {
    const payload: Record<string, unknown> = { message };

    if (target.name) {
      payload.target_name = target.name;
    } else if (target.agentId !== undefined) {
      payload.target_id = target.agentId;
    }

    const result = await this.transport.callJson(SyscallOp.SYS_SEND, payload);

    return {
      success: (result.success as boolean) ?? false,
      delivered: (result.delivered as boolean) ?? false,
      error: result.error as string | undefined,
    };
  }

  /**
   * Receive pending messages.
   */
  async recv(maxMessages?: number): Promise<RecvResult> {
    const payload: Record<string, unknown> = {};
    if (maxMessages !== undefined) {
      payload.max = maxMessages;
    }

    const result = await this.transport.callJson(SyscallOp.SYS_RECV, payload);

    const messagesData = (result.messages as Record<string, unknown>[]) ?? [];
    const messages: IPCMessage[] = messagesData.map((m) => ({
      fromAgent: (m.from_agent as number) ?? 0,
      fromName: m.from_name as string | undefined,
      message: (m.message as Record<string, unknown>) ?? {},
      timestamp: (m.timestamp as number) ?? 0,
    }));

    return {
      success: (result.success as boolean) ?? false,
      messages,
      count: (result.count as number) ?? messages.length,
      error: result.error as string | undefined,
    };
  }

  /**
   * Broadcast a message to all agents.
   */
  async broadcast(message: Record<string, unknown>): Promise<BroadcastResult> {
    const result = await this.transport.callJson(SyscallOp.SYS_BROADCAST, { message });

    return {
      success: (result.success as boolean) ?? false,
      deliveredCount: (result.delivered_count as number) ?? 0,
      error: result.error as string | undefined,
    };
  }

  /**
   * Register this agent's name for routing.
   */
  async register(name: string): Promise<RegisterResult> {
    const result = await this.transport.callJson(SyscallOp.SYS_REGISTER, { name });

    return {
      success: (result.success as boolean) ?? false,
      error: result.error as string | undefined,
    };
  }
}
