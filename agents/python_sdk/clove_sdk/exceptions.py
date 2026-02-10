"""Clove SDK exceptions.

Exception hierarchy for the Clove SDK providing typed error handling.
"""


class CloveError(Exception):
    """Base exception for all Clove SDK errors."""
    pass


class ConnectionError(CloveError):
    """Failed to connect to kernel or connection lost."""
    pass


class ProtocolError(CloveError):
    """Invalid protocol message, magic bytes, or malformed response."""
    pass


class TimeoutError(CloveError):
    """Operation timed out."""
    pass


class SyscallError(CloveError):
    """Syscall returned an error from the kernel.

    Attributes:
        opcode: The syscall opcode that failed
        details: Additional error details from kernel response
    """
    def __init__(self, message: str, opcode: int = None, details: dict = None):
        super().__init__(message)
        self.opcode = opcode
        self.details = details or {}


class PermissionDenied(SyscallError):
    """Agent lacks required permissions for the requested operation."""
    pass


class AgentNotFound(SyscallError):
    """Target agent does not exist or has terminated."""
    pass


class StateKeyNotFound(SyscallError):
    """Key not found in state store."""
    pass


class WorldNotFound(SyscallError):
    """World does not exist."""
    pass


class TunnelError(SyscallError):
    """Tunnel connection or relay error."""
    pass


class ValidationError(CloveError):
    """Invalid input parameters."""
    pass
