/**
 * State Store API.
 *
 * Provides key-value storage operations.
 */

import { SyscallOp } from "../protocol.js";
import { Transport } from "../transport.js";
import { StoreResult, FetchResult, DeleteResult, KeysResult } from "../models.js";

export type StateScope = "agent" | "global" | "world";

export interface StoreOptions {
  key: string;
  value: unknown;
  scope?: StateScope;
  ttl?: number; // TTL in seconds
}

export class StateAPI {
  constructor(private transport: Transport) {}

  /**
   * Store a key-value pair.
   */
  async store(options: StoreOptions): Promise<StoreResult> {
    const payload: Record<string, unknown> = {
      key: options.key,
      value: options.value,
      scope: options.scope ?? "agent",
    };

    if (options.ttl !== undefined) {
      payload.ttl = options.ttl;
    }

    const result = await this.transport.callJson(SyscallOp.SYS_STORE, payload);

    return {
      success: (result.success as boolean) ?? false,
      error: result.error as string | undefined,
    };
  }

  /**
   * Retrieve a value by key.
   */
  async fetch(key: string, scope: StateScope = "agent"): Promise<FetchResult> {
    const result = await this.transport.callJson(SyscallOp.SYS_FETCH, { key, scope });

    return {
      success: (result.success as boolean) ?? false,
      value: result.value,
      found: (result.found as boolean) ?? false,
      error: result.error as string | undefined,
    };
  }

  /**
   * Delete a key.
   */
  async delete(key: string, scope: StateScope = "agent"): Promise<DeleteResult> {
    const result = await this.transport.callJson(SyscallOp.SYS_DELETE, { key, scope });

    return {
      success: (result.success as boolean) ?? false,
      deleted: (result.deleted as boolean) ?? false,
      error: result.error as string | undefined,
    };
  }

  /**
   * List keys with optional prefix.
   */
  async keys(prefix?: string, scope: StateScope = "agent"): Promise<KeysResult> {
    const payload: Record<string, unknown> = { scope };
    if (prefix !== undefined) {
      payload.prefix = prefix;
    }

    const result = await this.transport.callJson(SyscallOp.SYS_KEYS, payload);

    return {
      success: (result.success as boolean) ?? false,
      keys: (result.keys as string[]) ?? [],
      count: (result.count as number) ?? 0,
      error: result.error as string | undefined,
    };
  }

  // Convenience methods

  /**
   * Get a value (returns undefined if not found).
   */
  async get<T = unknown>(key: string, scope: StateScope = "agent"): Promise<T | undefined> {
    const result = await this.fetch(key, scope);
    return result.found ? (result.value as T) : undefined;
  }

  /**
   * Set a value.
   */
  async set(key: string, value: unknown, scope: StateScope = "agent"): Promise<boolean> {
    const result = await this.store({ key, value, scope });
    return result.success;
  }
}
