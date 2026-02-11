/**
 * Events (Pub/Sub) API.
 *
 * Provides event subscription and emission.
 */

import { SyscallOp } from "../protocol.js";
import { Transport } from "../transport.js";
import {
  KernelEvent,
  SubscribeResult,
  PollEventsResult,
  EmitResult,
  OperationResult,
} from "../models.js";

export class EventsAPI {
  constructor(private transport: Transport) {}

  /**
   * Subscribe to event types.
   */
  async subscribe(eventTypes: string[]): Promise<SubscribeResult> {
    const result = await this.transport.callJson(SyscallOp.SYS_SUBSCRIBE, {
      event_types: eventTypes,
    });

    return {
      success: (result.success as boolean) ?? false,
      subscribed: (result.subscribed as string[]) ?? [],
      error: result.error as string | undefined,
    };
  }

  /**
   * Unsubscribe from event types.
   */
  async unsubscribe(eventTypes: string[]): Promise<OperationResult> {
    const result = await this.transport.callJson(SyscallOp.SYS_UNSUBSCRIBE, {
      event_types: eventTypes,
    });

    return {
      success: (result.success as boolean) ?? false,
      error: result.error as string | undefined,
    };
  }

  /**
   * Poll for pending events.
   */
  async poll(maxEvents?: number): Promise<PollEventsResult> {
    const payload: Record<string, unknown> = {};
    if (maxEvents !== undefined) {
      payload.max = maxEvents;
    }

    const result = await this.transport.callJson(SyscallOp.SYS_POLL_EVENTS, payload);

    const eventsData = (result.events as Record<string, unknown>[]) ?? [];
    const events: KernelEvent[] = eventsData.map((e) => ({
      eventType: (e.event_type as string) ?? "",
      data: (e.data as Record<string, unknown>) ?? {},
      timestamp: (e.timestamp as number) ?? 0,
      sourceAgent: e.source_agent as number | undefined,
    }));

    return {
      success: (result.success as boolean) ?? false,
      events,
      count: (result.count as number) ?? events.length,
      error: result.error as string | undefined,
    };
  }

  /**
   * Emit a custom event.
   */
  async emit(eventType: string, data: Record<string, unknown>): Promise<EmitResult> {
    const result = await this.transport.callJson(SyscallOp.SYS_EMIT, {
      event_type: eventType,
      data,
    });

    return {
      success: (result.success as boolean) ?? false,
      deliveredTo: (result.delivered_to as number) ?? 0,
      error: result.error as string | undefined,
    };
  }
}
