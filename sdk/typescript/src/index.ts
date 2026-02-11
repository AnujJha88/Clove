/**
 * Clove TypeScript SDK
 *
 * A TypeScript SDK for the Clove microkernel runtime.
 *
 * @example
 * ```typescript
 * import { CloveClient, connect } from '@clove/sdk';
 *
 * // Using connect helper
 * const client = await connect();
 * const info = await client.hello();
 * console.log(`Kernel v${info.version}`);
 *
 * // Or manual connection
 * const client = new CloveClient();
 * await client.connect();
 * // ... use client
 * client.disconnect();
 * ```
 *
 * @packageDocumentation
 */

// Main client
export { CloveClient, connect } from "./client.js";

// Protocol
export {
  SyscallOp,
  Message,
  MAGIC_BYTES,
  HEADER_SIZE,
  MAX_PAYLOAD_SIZE,
  DEFAULT_SOCKET_PATH,
  DEFAULT_TIMEOUT,
  serializeMessage,
  deserializeMessage,
  payloadToString,
  createJsonMessage,
} from "./protocol.js";

// Transport
export { Transport } from "./transport.js";

// Models
export {
  // Core
  KernelInfo,
  ExecResult,
  FileContent,
  WriteResult,
  // Agents
  AgentState,
  AgentInfo,
  SpawnResult,
  SpawnOptions,
  ResourceLimits,
  // IPC
  IPCMessage,
  SendResult,
  RecvResult,
  BroadcastResult,
  RegisterResult,
  // State
  StoreResult,
  FetchResult,
  DeleteResult,
  KeysResult,
  // Permissions
  PermissionsInfo,
  // HTTP
  HttpResult,
  // Events
  KernelEvent,
  SubscribeResult,
  PollEventsResult,
  EmitResult,
  // Async
  AsyncResult,
  PollAsyncResult,
  // Metrics
  SystemMetrics,
  AgentMetrics,
  AllAgentsMetrics,
  CgroupMetrics,
  // World
  WorldInfo,
  WorldCreateResult,
  WorldListResult,
  WorldState,
  WorldSnapshot,
  // Tunnel
  TunnelStatus,
  TunnelRemotesResult,
  // Audit
  AuditEntry,
  AuditLogResult,
  AuditConfigResult,
  // Recording
  RecordingStatus,
  ReplayStatus,
  // Generic
  OperationResult,
} from "./models.js";

// Exceptions
export {
  CloveError,
  ConnectionError,
  ProtocolError,
  SyscallError,
  AgentNotFoundError,
  ValidationError,
  TimeoutError,
} from "./exceptions.js";

// API modules
export {
  AgentsAPI,
  FilesystemAPI,
  IPCAPI,
  StateAPI,
  EventsAPI,
  MetricsAPI,
  type ExecOptions,
  type StateScope,
  type StoreOptions,
} from "./api/index.js";
