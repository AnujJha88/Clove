/**
 * Clove TypeScript SDK - Main Client.
 *
 * Provides a unified API for communicating with the Clove kernel.
 *
 * @example
 * ```typescript
 * import { CloveClient } from '@clove/sdk';
 *
 * const client = new CloveClient();
 * await client.connect();
 *
 * const info = await client.hello();
 * console.log(`Connected to kernel v${info.version}`);
 *
 * const result = await client.filesystem.exec({ command: 'ls -la' });
 * console.log(result.stdout);
 *
 * await client.disconnect();
 * ```
 */

import { SyscallOp, DEFAULT_SOCKET_PATH, Message, payloadToString } from "./protocol.js";
import { Transport } from "./transport.js";
import { KernelInfo } from "./models.js";
import { AgentsAPI } from "./api/agents.js";
import { FilesystemAPI } from "./api/filesystem.js";
import { IPCAPI } from "./api/ipc.js";
import { StateAPI } from "./api/state.js";
import { EventsAPI } from "./api/events.js";
import { MetricsAPI } from "./api/metrics.js";

/**
 * Client for communicating with the Clove kernel.
 *
 * Provides a unified API for all kernel operations through domain-specific API objects.
 */
export class CloveClient {
  private transport: Transport;

  /** Agent management operations */
  public readonly agents: AgentsAPI;
  /** Filesystem and command execution operations */
  public readonly filesystem: FilesystemAPI;
  /** Inter-process communication operations */
  public readonly ipc: IPCAPI;
  /** State store operations */
  public readonly state: StateAPI;
  /** Event pub/sub operations */
  public readonly events: EventsAPI;
  /** Metrics collection operations */
  public readonly metrics: MetricsAPI;

  constructor(socketPath: string = DEFAULT_SOCKET_PATH) {
    this.transport = new Transport(socketPath);

    // Initialize API modules
    this.agents = new AgentsAPI(this.transport);
    this.filesystem = new FilesystemAPI(this.transport);
    this.ipc = new IPCAPI(this.transport);
    this.state = new StateAPI(this.transport);
    this.events = new EventsAPI(this.transport);
    this.metrics = new MetricsAPI(this.transport);
  }

  /** Get the socket path. */
  get socketPath(): string {
    return this.transport.socketPath;
  }

  /** Get the agent ID assigned by kernel. */
  get agentId(): number {
    return this.transport.agentId;
  }

  /** Check if client is connected to kernel. */
  get connected(): boolean {
    return this.transport.connected;
  }

  /**
   * Connect to the Clove kernel.
   */
  async connect(): Promise<void> {
    await this.transport.connect();
  }

  /**
   * Disconnect from the kernel.
   */
  disconnect(): void {
    this.transport.disconnect();
  }

  /**
   * Query kernel version and capabilities.
   */
  async hello(): Promise<KernelInfo> {
    const result = await this.transport.callJson(SyscallOp.SYS_HELLO, {});

    return {
      version: (result.version as string) ?? "unknown",
      capabilities: (result.capabilities as string[]) ?? [],
      agentId: (result.agent_id as number) ?? this.agentId,
      uptimeSeconds: (result.uptime as number) ?? 0,
    };
  }

  /**
   * Echo a message (for testing).
   */
  async echo(message: string): Promise<string | null> {
    const response = await this.transport.call(SyscallOp.SYS_NOOP, message);
    return payloadToString(response);
  }

  /**
   * Alias for echo - send a NOOP message (for testing).
   */
  async noop(message: string): Promise<string | null> {
    return this.echo(message);
  }

  /**
   * Request graceful exit.
   */
  async exit(): Promise<boolean> {
    try {
      await this.transport.call(SyscallOp.SYS_EXIT);
      return true;
    } catch {
      return false;
    }
  }

  // ========== Low-level methods ==========

  /**
   * Send a message to the kernel (low-level).
   */
  async send(opcode: SyscallOp, payload: Buffer | string = Buffer.alloc(0)): Promise<boolean> {
    try {
      await this.transport.send(opcode, payload);
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Receive a message from the kernel (low-level).
   */
  async recv(): Promise<Message | null> {
    try {
      return await this.transport.recv();
    } catch {
      return null;
    }
  }

  /**
   * Send a message and wait for response (low-level).
   */
  async call(opcode: SyscallOp, payload: Buffer | string = Buffer.alloc(0)): Promise<Message | null> {
    try {
      return await this.transport.call(opcode, payload);
    } catch {
      return null;
    }
  }

  /**
   * Send request with JSON payload and parse JSON response (low-level).
   */
  async callJson(opcode: SyscallOp, payload: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    return this.transport.callJson(opcode, payload);
  }
}

/**
 * Create and connect a client.
 */
export async function connect(socketPath: string = DEFAULT_SOCKET_PATH): Promise<CloveClient> {
  const client = new CloveClient(socketPath);
  await client.connect();
  return client;
}
