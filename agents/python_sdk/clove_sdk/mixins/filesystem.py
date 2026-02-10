"""Filesystem and execution syscalls.

Provides file I/O and shell command execution.
"""

from typing import Optional, TYPE_CHECKING

from ..protocol import SyscallOp
from ..models import ExecResult, FileContent, WriteResult

if TYPE_CHECKING:
    from ..transport import Transport


class FilesystemMixin:
    """Mixin for file and command execution operations.

    Requires _transport attribute of type Transport.
    """

    _transport: 'Transport'

    def exec(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 30,
        async_: bool = False,
        request_id: Optional[int] = None
    ) -> ExecResult:
        """Execute a shell command.

        Args:
            command: Shell command to execute
            cwd: Working directory (default: agent's cwd)
            timeout: Timeout in seconds
            async_: Run asynchronously (poll with poll_async)
            request_id: ID for async result tracking

        Returns:
            ExecResult with stdout, stderr, exit_code
        """
        payload = {
            "command": command,
            "timeout": timeout,
            "async": async_
        }
        if cwd:
            payload["cwd"] = cwd
        if request_id is not None:
            payload["request_id"] = request_id

        result = self._transport.call_json(SyscallOp.SYS_EXEC, payload)

        return ExecResult(
            success=result.get("success", False),
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
            exit_code=result.get("exit_code", -1),
            duration_ms=result.get("duration_ms"),
            async_request_id=result.get("request_id")
        )

    def read_file(self, path: str) -> FileContent:
        """Read a file's contents.

        Args:
            path: Path to file (absolute or relative to agent's cwd)

        Returns:
            FileContent with content and size
        """
        result = self._transport.call_json(SyscallOp.SYS_READ, {"path": path})

        return FileContent(
            success=result.get("success", False),
            content=result.get("content", ""),
            size=result.get("size", 0),
            error=result.get("error")
        )

    def write_file(
        self,
        path: str,
        content: str,
        mode: str = "write"
    ) -> WriteResult:
        """Write content to a file.

        Args:
            path: Path to file
            content: Content to write
            mode: "write" (overwrite) or "append"

        Returns:
            WriteResult with bytes_written
        """
        payload = {
            "path": path,
            "content": content,
            "mode": mode
        }
        result = self._transport.call_json(SyscallOp.SYS_WRITE, payload)

        return WriteResult(
            success=result.get("success", False),
            bytes_written=result.get("bytes_written", 0),
            error=result.get("error")
        )

    def read(self, path: str) -> str:
        """Read file and return content string.

        Convenience method that returns just the content.

        Args:
            path: Path to file

        Returns:
            File content as string

        Raises:
            IOError: If read fails
        """
        result = self.read_file(path)
        if not result.success:
            raise IOError(result.error or "Read failed")
        return result.content

    def write(self, path: str, content: str, mode: str = "write") -> WriteResult:
        """Write content to file.

        Alias for write_file.

        Args:
            path: Path to file
            content: Content to write
            mode: "write" (overwrite) or "append"

        Returns:
            WriteResult with bytes_written
        """
        return self.write_file(path, content, mode)
