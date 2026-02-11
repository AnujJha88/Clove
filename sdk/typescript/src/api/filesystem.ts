/**
 * Filesystem and execution API.
 *
 * Provides file I/O and shell command execution.
 */

import { SyscallOp } from "../protocol.js";
import { Transport } from "../transport.js";
import { ExecResult, FileContent, WriteResult } from "../models.js";

export interface ExecOptions {
  command: string;
  cwd?: string;
  timeout?: number;
  async?: boolean;
  requestId?: number;
}

export class FilesystemAPI {
  constructor(private transport: Transport) {}

  /**
   * Execute a shell command.
   */
  async exec(options: ExecOptions): Promise<ExecResult> {
    const payload: Record<string, unknown> = {
      command: options.command,
      timeout: options.timeout ?? 30,
      async: options.async ?? false,
    };

    if (options.cwd) {
      payload.cwd = options.cwd;
    }
    if (options.requestId !== undefined) {
      payload.request_id = options.requestId;
    }

    const result = await this.transport.callJson(SyscallOp.SYS_EXEC, payload);

    return {
      success: (result.success as boolean) ?? false,
      stdout: (result.stdout as string) ?? "",
      stderr: (result.stderr as string) ?? "",
      exitCode: (result.exit_code as number) ?? -1,
      durationMs: result.duration_ms as number | undefined,
      asyncRequestId: result.request_id as number | undefined,
    };
  }

  /**
   * Read a file's contents.
   */
  async readFile(path: string): Promise<FileContent> {
    const result = await this.transport.callJson(SyscallOp.SYS_READ, { path });

    return {
      success: (result.success as boolean) ?? false,
      content: (result.content as string) ?? "",
      size: (result.size as number) ?? 0,
      error: result.error as string | undefined,
    };
  }

  /**
   * Write content to a file.
   */
  async writeFile(
    path: string,
    content: string,
    mode: "write" | "append" = "write"
  ): Promise<WriteResult> {
    const payload = { path, content, mode };
    const result = await this.transport.callJson(SyscallOp.SYS_WRITE, payload);

    return {
      success: (result.success as boolean) ?? false,
      bytesWritten: (result.bytes_written as number) ?? 0,
      error: result.error as string | undefined,
    };
  }

  /**
   * Read file and return content string.
   * Throws on failure.
   */
  async read(path: string): Promise<string> {
    const result = await this.readFile(path);
    if (!result.success) {
      throw new Error(result.error ?? "Read failed");
    }
    return result.content;
  }

  /**
   * Write content to file (alias for writeFile).
   */
  async write(
    path: string,
    content: string,
    mode: "write" | "append" = "write"
  ): Promise<WriteResult> {
    return this.writeFile(path, content, mode);
  }
}
