/**
 * Response models for Clove SDK.
 *
 * Typed interfaces for all kernel responses.
 */

// ========== Core ==========

export interface KernelInfo {
  version: string;
  capabilities: string[];
  agentId: number;
  uptimeSeconds: number;
}

export interface ExecResult {
  success: boolean;
  stdout: string;
  stderr: string;
  exitCode: number;
  durationMs?: number;
  asyncRequestId?: number;
}

export interface FileContent {
  success: boolean;
  content: string;
  size: number;
  error?: string;
}

export interface WriteResult {
  success: boolean;
  bytesWritten: number;
  error?: string;
}

// ========== Agents ==========

export enum AgentState {
  RUNNING = "running",
  PAUSED = "paused",
  STOPPED = "stopped",
  STARTING = "starting",
  CRASHED = "crashed",
}

export interface AgentInfo {
  id: number;
  name: string;
  pid: number;
  state: AgentState;
  uptimeSeconds: number;
  memoryBytes?: number;
  cpuPercent?: number;
}

export interface SpawnResult {
  success: boolean;
  agentId?: number;
  pid?: number;
  error?: string;
}

export interface SpawnOptions {
  name: string;
  script: string;
  sandboxed?: boolean;
  network?: boolean;
  limits?: ResourceLimits;
  restartPolicy?: "never" | "on_failure" | "always";
  maxRestarts?: number;
  restartWindow?: number;
}

export interface ResourceLimits {
  memoryMb?: number;
  cpuPercent?: number;
  maxPids?: number;
}

// ========== IPC ==========

export interface IPCMessage {
  fromAgent: number;
  fromName?: string;
  message: Record<string, unknown>;
  timestamp: number;
}

export interface SendResult {
  success: boolean;
  delivered: boolean;
  error?: string;
}

export interface RecvResult {
  success: boolean;
  messages: IPCMessage[];
  count: number;
  error?: string;
}

export interface BroadcastResult {
  success: boolean;
  deliveredCount: number;
  error?: string;
}

export interface RegisterResult {
  success: boolean;
  error?: string;
}

// ========== State Store ==========

export interface StoreResult {
  success: boolean;
  error?: string;
}

export interface FetchResult {
  success: boolean;
  value: unknown;
  found: boolean;
  error?: string;
}

export interface DeleteResult {
  success: boolean;
  deleted: boolean;
  error?: string;
}

export interface KeysResult {
  success: boolean;
  keys: string[];
  count: number;
  error?: string;
}

// ========== Permissions ==========

export interface PermissionsInfo {
  success: boolean;
  level?: string;
  paths: string[];
  commands: string[];
  domains: string[];
  error?: string;
}

// ========== HTTP ==========

export interface HttpResult {
  success: boolean;
  statusCode: number;
  body: string;
  headers: Record<string, string>;
  error?: string;
  asyncRequestId?: number;
}

// ========== Events ==========

export interface KernelEvent {
  eventType: string;
  data: Record<string, unknown>;
  timestamp: number;
  sourceAgent?: number;
}

export interface SubscribeResult {
  success: boolean;
  subscribed: string[];
  error?: string;
}

export interface PollEventsResult {
  success: boolean;
  events: KernelEvent[];
  count: number;
  error?: string;
}

export interface EmitResult {
  success: boolean;
  deliveredTo: number;
  error?: string;
}

// ========== Async ==========

export interface AsyncResult {
  requestId: number;
  opcode: number;
  success: boolean;
  result: Record<string, unknown>;
  error?: string;
}

export interface PollAsyncResult {
  success: boolean;
  results: AsyncResult[];
  count: number;
  error?: string;
}

// ========== Metrics ==========

export interface SystemMetrics {
  success: boolean;
  cpuPercent: number;
  memoryUsedBytes: number;
  memoryTotalBytes: number;
  memoryPercent: number;
  diskUsedBytes: number;
  diskTotalBytes: number;
  diskPercent: number;
  networkRxBytes: number;
  networkTxBytes: number;
  loadAverage: number[];
  error?: string;
}

export interface AgentMetrics {
  agentId: number;
  name: string;
  cpuPercent: number;
  memoryBytes: number;
  memoryPercent: number;
  syscallsCount: number;
  uptimeSeconds: number;
  state: string;
}

export interface AllAgentsMetrics {
  success: boolean;
  agents: AgentMetrics[];
  count: number;
  error?: string;
}

export interface CgroupMetrics {
  success: boolean;
  cpuUsageUsec: number;
  memoryCurrent: number;
  memoryLimit: number;
  pidsCurrent: number;
  pidsLimit: number;
  error?: string;
}

// ========== World ==========

export interface WorldInfo {
  id: string;
  name: string;
  agentCount: number;
  createdAt: number;
}

export interface WorldCreateResult {
  success: boolean;
  worldId?: string;
  error?: string;
}

export interface WorldListResult {
  success: boolean;
  worlds: WorldInfo[];
  count: number;
  error?: string;
}

export interface WorldState {
  success: boolean;
  id: string;
  name: string;
  agents: number[];
  metrics: Record<string, unknown>;
  chaosEventsInjected: number;
  error?: string;
}

export interface WorldSnapshot {
  success: boolean;
  snapshotId?: string;
  snapshotData?: string;
  error?: string;
}

// ========== Tunnel ==========

export interface TunnelStatus {
  success: boolean;
  connected: boolean;
  relayUrl?: string;
  machineId?: string;
  latencyMs?: number;
  connectedSince?: number;
  error?: string;
}

export interface TunnelRemotesResult {
  success: boolean;
  agents: Record<string, unknown>[];
  count: number;
  error?: string;
}

// ========== Audit ==========

export interface AuditEntry {
  id: number;
  timestamp: number;
  category: string;
  agentId?: number;
  action: string;
  details: Record<string, unknown>;
}

export interface AuditLogResult {
  success: boolean;
  entries: AuditEntry[];
  count: number;
  error?: string;
}

export interface AuditConfigResult {
  success: boolean;
  config: Record<string, unknown>;
  error?: string;
}

// ========== Recording ==========

export interface RecordingStatus {
  success: boolean;
  active: boolean;
  entryCount: number;
  startedAt?: number;
  recordingData?: string;
  error?: string;
}

export interface ReplayStatus {
  success: boolean;
  active: boolean;
  progress: number;
  totalEntries: number;
  entriesReplayed: number;
  entriesSkipped: number;
  errors: string[];
  error?: string;
}

// ========== Generic ==========

export interface OperationResult {
  success: boolean;
  error?: string;
  data?: Record<string, unknown>;
}
