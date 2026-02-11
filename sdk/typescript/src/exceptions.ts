/**
 * Exception classes for Clove SDK.
 */

import { SyscallOp } from "./protocol.js";

/**
 * Base class for all Clove SDK errors.
 */
export class CloveError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CloveError";
  }
}

/**
 * Connection-related errors.
 */
export class ConnectionError extends CloveError {
  constructor(message: string) {
    super(message);
    this.name = "ConnectionError";
  }
}

/**
 * Protocol-related errors (invalid messages, etc).
 */
export class ProtocolError extends CloveError {
  constructor(message: string) {
    super(message);
    this.name = "ProtocolError";
  }
}

/**
 * Syscall execution errors.
 */
export class SyscallError extends CloveError {
  public readonly opcode?: SyscallOp;

  constructor(message: string, opcode?: SyscallOp) {
    super(message);
    this.name = "SyscallError";
    this.opcode = opcode;
  }
}

/**
 * Agent not found error.
 */
export class AgentNotFoundError extends SyscallError {
  constructor(message: string, opcode?: SyscallOp) {
    super(message, opcode);
    this.name = "AgentNotFoundError";
  }
}

/**
 * Validation error for invalid parameters.
 */
export class ValidationError extends CloveError {
  constructor(message: string) {
    super(message);
    this.name = "ValidationError";
  }
}

/**
 * Timeout error.
 */
export class TimeoutError extends CloveError {
  constructor(message: string = "Operation timed out") {
    super(message);
    this.name = "TimeoutError";
  }
}
