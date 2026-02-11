/**
 * Clove wire protocol definitions.
 *
 * Binary protocol for communication between agents and the kernel.
 */

// Protocol constants
export const MAGIC_BYTES = 0x41474e54; // "AGNT" in hex
export const HEADER_SIZE = 17;
export const MAX_PAYLOAD_SIZE = 1024 * 1024; // 1MB
export const DEFAULT_SOCKET_PATH = "/tmp/clove.sock";
export const DEFAULT_TIMEOUT = 30000; // 30 seconds in ms

/**
 * System call operations supported by the kernel.
 */
export enum SyscallOp {
  // Core operations
  SYS_NOOP = 0x00, // For testing / echo
  SYS_THINK = 0x01, // Send prompt to LLM
  SYS_EXEC = 0x02, // Execute shell command
  SYS_READ = 0x03, // Read file
  SYS_WRITE = 0x04, // Write file

  // Agent lifecycle
  SYS_SPAWN = 0x10, // Spawn a sandboxed agent
  SYS_KILL = 0x11, // Kill an agent
  SYS_LIST = 0x12, // List running agents
  SYS_PAUSE = 0x14, // Pause an agent
  SYS_RESUME = 0x15, // Resume a paused agent

  // IPC - Inter-Agent Communication
  SYS_SEND = 0x20, // Send message to another agent
  SYS_RECV = 0x21, // Receive pending messages
  SYS_BROADCAST = 0x22, // Broadcast message to all agents
  SYS_REGISTER = 0x23, // Register agent name

  // State Store
  SYS_STORE = 0x30, // Store key-value pair
  SYS_FETCH = 0x31, // Retrieve value by key
  SYS_DELETE = 0x32, // Delete a key
  SYS_KEYS = 0x33, // List keys with optional prefix

  // Permissions
  SYS_GET_PERMS = 0x40, // Get own permissions
  SYS_SET_PERMS = 0x41, // Set agent permissions

  // Network
  SYS_HTTP = 0x50, // Make HTTP request

  // Events (Pub/Sub)
  SYS_SUBSCRIBE = 0x60, // Subscribe to event types
  SYS_UNSUBSCRIBE = 0x61, // Unsubscribe from events
  SYS_POLL_EVENTS = 0x62, // Get pending events
  SYS_EMIT = 0x63, // Emit custom event

  // Execution Recording & Replay
  SYS_RECORD_START = 0x70, // Start recording execution
  SYS_RECORD_STOP = 0x71, // Stop recording
  SYS_RECORD_STATUS = 0x72, // Get recording status
  SYS_REPLAY_START = 0x73, // Start replay
  SYS_REPLAY_STATUS = 0x74, // Get replay status

  // Audit Logging
  SYS_GET_AUDIT_LOG = 0x76, // Get audit log entries
  SYS_SET_AUDIT_CONFIG = 0x77, // Configure audit logging

  // Async Results
  SYS_ASYNC_POLL = 0x80, // Poll async syscall results

  // World Simulation
  SYS_WORLD_CREATE = 0xa0, // Create world from config
  SYS_WORLD_DESTROY = 0xa1, // Destroy world
  SYS_WORLD_LIST = 0xa2, // List active worlds
  SYS_WORLD_JOIN = 0xa3, // Join agent to world
  SYS_WORLD_LEAVE = 0xa4, // Remove agent from world
  SYS_WORLD_EVENT = 0xa5, // Inject chaos event
  SYS_WORLD_STATE = 0xa6, // Get world metrics
  SYS_WORLD_SNAPSHOT = 0xa7, // Save world state
  SYS_WORLD_RESTORE = 0xa8, // Restore from snapshot

  // Remote Connectivity (Tunnel)
  SYS_TUNNEL_CONNECT = 0xb0, // Connect kernel to relay server
  SYS_TUNNEL_DISCONNECT = 0xb1, // Disconnect from relay
  SYS_TUNNEL_STATUS = 0xb2, // Get tunnel connection status
  SYS_TUNNEL_LIST_REMOTES = 0xb3, // List connected remote agents
  SYS_TUNNEL_CONFIG = 0xb4, // Configure tunnel settings

  // Metrics
  SYS_METRICS_SYSTEM = 0xc0, // Get system-wide metrics
  SYS_METRICS_AGENT = 0xc1, // Get metrics for specific agent
  SYS_METRICS_ALL_AGENTS = 0xc2, // Get metrics for all agents
  SYS_METRICS_CGROUP = 0xc3, // Get cgroup metrics

  // Kernel info / capabilities
  SYS_LLM_REPORT = 0xf0, // Report SDK LLM usage to kernel
  SYS_HELLO = 0xfe, // Handshake / capability query
  SYS_EXIT = 0xff, // Graceful shutdown
}

/**
 * Clove wire protocol message.
 *
 * Wire format (17-byte header + variable payload):
 *   [Magic:4B "AGNT"] [Agent ID:4B] [Opcode:1B] [Payload Length:8B] [Payload:var]
 */
export interface Message {
  agentId: number;
  opcode: SyscallOp;
  payload: Buffer;
}

/**
 * Serialize message to wire format.
 */
export function serializeMessage(msg: Message): Buffer {
  const header = Buffer.alloc(HEADER_SIZE);

  // Little-endian: uint32, uint32, uint8, uint64
  header.writeUInt32LE(MAGIC_BYTES, 0);
  header.writeUInt32LE(msg.agentId, 4);
  header.writeUInt8(msg.opcode, 8);
  header.writeBigUInt64LE(BigInt(msg.payload.length), 9);

  return Buffer.concat([header, msg.payload]);
}

/**
 * Deserialize message from wire format.
 * Returns null if data is invalid or incomplete.
 */
export function deserializeMessage(data: Buffer): Message | null {
  if (data.length < HEADER_SIZE) {
    return null;
  }

  const magic = data.readUInt32LE(0);
  const agentId = data.readUInt32LE(4);
  const opcode = data.readUInt8(8);
  const payloadSize = Number(data.readBigUInt64LE(9));

  if (magic !== MAGIC_BYTES) {
    return null;
  }

  if (payloadSize > MAX_PAYLOAD_SIZE) {
    return null;
  }

  if (data.length < HEADER_SIZE + payloadSize) {
    return null;
  }

  const payload = data.subarray(HEADER_SIZE, HEADER_SIZE + payloadSize);

  return {
    agentId,
    opcode: opcode as SyscallOp,
    payload: Buffer.from(payload),
  };
}

/**
 * Get payload as UTF-8 string.
 */
export function payloadToString(msg: Message): string {
  return msg.payload.toString("utf-8");
}

/**
 * Create a message with JSON payload.
 */
export function createJsonMessage(
  agentId: number,
  opcode: SyscallOp,
  data: Record<string, unknown>
): Message {
  return {
    agentId,
    opcode,
    payload: Buffer.from(JSON.stringify(data), "utf-8"),
  };
}
