/**
 * Socket transport for Clove kernel communication.
 *
 * Handles low-level socket connection, message serialization, and I/O.
 */

import * as net from "node:net";
import {
  Message,
  SyscallOp,
  HEADER_SIZE,
  MAGIC_BYTES,
  DEFAULT_SOCKET_PATH,
  serializeMessage,
} from "./protocol.js";
import { ConnectionError, ProtocolError } from "./exceptions.js";

/**
 * Low-level socket transport for kernel communication.
 *
 * Manages the Unix domain socket connection and provides methods
 * for sending/receiving wire protocol messages.
 */
export class Transport {
  private socket: net.Socket | null = null;
  private _agentId: number = 0;
  private receiveBuffer: Buffer = Buffer.alloc(0);
  public readonly socketPath: string;

  constructor(socketPath: string = DEFAULT_SOCKET_PATH) {
    this.socketPath = socketPath;
  }

  get agentId(): number {
    return this._agentId;
  }

  get connected(): boolean {
    return this.socket !== null && !this.socket.destroyed;
  }

  /**
   * Connect to the Clove kernel.
   */
  async connect(): Promise<void> {
    if (this.socket !== null) {
      return; // Already connected
    }

    return new Promise((resolve, reject) => {
      this.socket = net.createConnection(this.socketPath);

      this.socket.once("connect", () => {
        resolve();
      });

      this.socket.once("error", (err) => {
        this.socket = null;
        reject(new ConnectionError(`Failed to connect to ${this.socketPath}: ${err.message}`));
      });
    });
  }

  /**
   * Disconnect from kernel.
   */
  disconnect(): void {
    if (this.socket) {
      this.socket.destroy();
      this.socket = null;
    }
    this.receiveBuffer = Buffer.alloc(0);
  }

  /**
   * Send a message to the kernel.
   */
  async send(opcode: SyscallOp, payload: Buffer | string | Record<string, unknown> = Buffer.alloc(0)): Promise<void> {
    if (!this.socket || this.socket.destroyed) {
      throw new ConnectionError("Not connected to kernel");
    }

    let payloadBuffer: Buffer;
    if (typeof payload === "string") {
      payloadBuffer = Buffer.from(payload, "utf-8");
    } else if (Buffer.isBuffer(payload)) {
      payloadBuffer = payload;
    } else {
      payloadBuffer = Buffer.from(JSON.stringify(payload), "utf-8");
    }

    const msg: Message = {
      agentId: this._agentId,
      opcode,
      payload: payloadBuffer,
    };

    return new Promise((resolve, reject) => {
      const data = serializeMessage(msg);
      this.socket!.write(data, (err) => {
        if (err) {
          reject(new ConnectionError(`Send failed: ${err.message}`));
        } else {
          resolve();
        }
      });
    });
  }

  /**
   * Receive a message from the kernel.
   */
  async recv(): Promise<Message> {
    if (!this.socket || this.socket.destroyed) {
      throw new ConnectionError("Not connected to kernel");
    }

    return new Promise((resolve, reject) => {
      const onData = (chunk: Buffer) => {
        this.receiveBuffer = Buffer.concat([this.receiveBuffer, chunk]);
        tryParse();
      };

      const onError = (err: Error) => {
        cleanup();
        reject(new ConnectionError(`Receive failed: ${err.message}`));
      };

      const onClose = () => {
        cleanup();
        reject(new ConnectionError("Connection closed by kernel"));
      };

      const cleanup = () => {
        this.socket?.off("data", onData);
        this.socket?.off("error", onError);
        this.socket?.off("close", onClose);
      };

      const tryParse = () => {
        // Need at least header to continue
        if (this.receiveBuffer.length < HEADER_SIZE) {
          return;
        }

        const magic = this.receiveBuffer.readUInt32LE(0);
        if (magic !== MAGIC_BYTES) {
          cleanup();
          reject(new ProtocolError(`Invalid magic bytes: 0x${magic.toString(16)}`));
          return;
        }

        const agentId = this.receiveBuffer.readUInt32LE(4);
        const opcode = this.receiveBuffer.readUInt8(8);
        const payloadSize = Number(this.receiveBuffer.readBigUInt64LE(9));

        // Check if we have the full message
        if (this.receiveBuffer.length < HEADER_SIZE + payloadSize) {
          return; // Wait for more data
        }

        // Extract the message
        const payload = this.receiveBuffer.subarray(HEADER_SIZE, HEADER_SIZE + payloadSize);
        this.receiveBuffer = this.receiveBuffer.subarray(HEADER_SIZE + payloadSize);

        // Update agent ID from response
        this._agentId = agentId;

        cleanup();
        resolve({
          agentId,
          opcode: opcode as SyscallOp,
          payload: Buffer.from(payload),
        });
      };

      this.socket!.on("data", onData);
      this.socket!.on("error", onError);
      this.socket!.on("close", onClose);

      // Try to parse from existing buffer first
      tryParse();
    });
  }

  /**
   * Send request and wait for response.
   */
  async call(opcode: SyscallOp, payload: Buffer | string | Record<string, unknown> = Buffer.alloc(0)): Promise<Message> {
    await this.send(opcode, payload);
    return this.recv();
  }

  /**
   * Send request with JSON payload and parse JSON response.
   */
  async callJson(opcode: SyscallOp, payload: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    const response = await this.call(opcode, payload);

    try {
      return JSON.parse(response.payload.toString("utf-8"));
    } catch (e) {
      throw new ProtocolError(`Invalid JSON response: ${e}`);
    }
  }
}
