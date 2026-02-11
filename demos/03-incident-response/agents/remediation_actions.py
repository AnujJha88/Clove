"""Remediation execution engine with safety validation.

Provides three execution modes:
- log_only: Records what would happen (current behavior)
- sandbox_exec: Builds real commands, executes with echo prefix
- real_exec: Actually executes commands via Clove SDK

Key classes:
- SafetyValidator: Validates actions before execution
- CommandBuilder: Builds shell commands for remediation actions
- RemediationExecutor: Executes remediation based on mode
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from clove_sdk import CloveClient


# Protected users that should never have their sessions revoked
PROTECTED_USERS = frozenset([
    "root", "www-data", "postgres", "mysql",
    "nobody", "daemon", "systemd-network", "systemd-resolve",
    "sshd", "messagebus", "avahi", "cups", "dbus",
])


@dataclass
class ValidationResult:
    """Result of safety validation."""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """Result of a remediation execution."""
    success: bool
    action: str
    command: str = ""
    mode: str = "log_only"
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    error: str = ""
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    execution_time_ms: int = 0


class SafetyValidator:
    """Validates remediation actions before execution.

    Enforces safety rules:
    - Never block internal IPs (10.x, 172.16.x, 192.168.x, 127.x)
    - Never revoke system user sessions
    - Rate limiting (max blocks per minute)
    - Path validation for cleanup actions
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        safety_config = config.get("safety", {})
        self.block_internal_ips = safety_config.get("block_internal_ips", False)
        self.revoke_system_users = safety_config.get("revoke_system_users", False)
        self.max_blocks_per_minute = safety_config.get("max_blocks_per_minute", 10)

        # Track recent blocks for rate limiting
        self._recent_blocks: List[float] = []

    def is_internal_ip(self, ip: str) -> bool:
        """Check if IP is in private/internal ranges."""
        if not ip:
            return False

        # Validate IP format first
        if not self.is_valid_ip(ip):
            return False

        parts = ip.split(".")
        if len(parts) != 4:
            return False

        try:
            octets = [int(p) for p in parts]
        except ValueError:
            return False

        # Check private ranges
        # 10.0.0.0/8
        if octets[0] == 10:
            return True
        # 172.16.0.0/12
        if octets[0] == 172 and 16 <= octets[1] <= 31:
            return True
        # 192.168.0.0/16
        if octets[0] == 192 and octets[1] == 168:
            return True
        # 127.0.0.0/8 (loopback)
        if octets[0] == 127:
            return True

        return False

    def is_valid_ip(self, ip: str) -> bool:
        """Validate IP address format."""
        if not ip:
            return False

        pattern = r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$"
        match = re.match(pattern, ip)
        if not match:
            return False

        return all(0 <= int(g) <= 255 for g in match.groups())

    def is_protected_user(self, user: str) -> bool:
        """Check if user is a protected system user."""
        if not user:
            return False
        return user.lower() in PROTECTED_USERS

    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits for blocking actions."""
        now = time.time()
        # Remove blocks older than 60 seconds
        self._recent_blocks = [t for t in self._recent_blocks if now - t < 60]
        return len(self._recent_blocks) < self.max_blocks_per_minute

    def _record_block(self) -> None:
        """Record a block action for rate limiting."""
        self._recent_blocks.append(time.time())

    def validate_action(self, action: str, incident: Dict[str, Any]) -> ValidationResult:
        """Validate a remediation action before execution.

        Args:
            action: The action name (e.g., "block_ip", "revoke_session")
            incident: The incident data containing details like source_ip, user

        Returns:
            ValidationResult with valid flag and any errors/warnings
        """
        errors: List[str] = []
        warnings: List[str] = []

        source_ip = incident.get("source_ip", "")
        user = incident.get("user", "")

        # Validate IP-based actions
        if action in ("block_ip", "monitor_ip"):
            if not source_ip:
                errors.append(f"Action '{action}' requires source_ip but none provided")
            elif not self.is_valid_ip(source_ip):
                errors.append(f"Invalid IP address format: {source_ip}")
            elif self.is_internal_ip(source_ip) and not self.block_internal_ips:
                errors.append(f"Cannot block internal IP: {source_ip} (safety rule)")

        # Validate user-based actions
        if action in ("revoke_session", "kill_user_sessions"):
            if not user:
                errors.append(f"Action '{action}' requires user but none provided")
            elif self.is_protected_user(user) and not self.revoke_system_users:
                errors.append(f"Cannot revoke session for protected user: {user} (safety rule)")

        # Rate limiting for blocking actions
        if action == "block_ip":
            if not self._check_rate_limit():
                errors.append(f"Rate limit exceeded: max {self.max_blocks_per_minute} blocks/minute")
            else:
                self._record_block()

        # Validate path-based actions
        if action == "cleanup":
            path = incident.get("path", "")
            if not path:
                errors.append("Cleanup action requires 'path' in incident")
            elif ".." in path:
                errors.append(f"Path traversal not allowed in cleanup: {path}")

        # Action-specific warnings
        if action == "isolate_host":
            warnings.append("Host isolation is a high-impact action - requires approval")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def requires_approval(self, action: str, severity: str) -> bool:
        """Check if an action requires manual approval.

        High-impact actions like host isolation always require approval.
        Critical severity actions may also require approval based on config.
        """
        # Actions that always require approval
        high_impact_actions = {"isolate_host", "cleanup"}
        if action in high_impact_actions:
            return True

        # Check config for severity-based approval requirements
        approval_config = self.config.get("approval", {})
        require_approval_for_critical = approval_config.get("require_for_critical", False)

        if require_approval_for_critical and severity == "critical":
            return True

        return False


class CommandBuilder:
    """Builds shell commands for remediation actions.

    Each method returns a command string that can be executed
    via the Clove SDK's exec() function.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        exec_config = config.get("execution", {})
        self.working_dir = exec_config.get("working_dir", "/tmp/clove-remediation")

    def block_ip(self, ip: str) -> str:
        """Generate command to block an IP via iptables."""
        return f"iptables -I INPUT -s {ip} -j DROP"

    def unblock_ip(self, ip: str) -> str:
        """Generate command to unblock an IP via iptables."""
        return f"iptables -D INPUT -s {ip} -j DROP"

    def monitor_ip(self, ip: str) -> str:
        """Generate command to add IP to fail2ban monitoring."""
        return f"fail2ban-client set sshd banip {ip}"

    def kill_user_sessions(self, user: str) -> str:
        """Generate command to kill all sessions for a user."""
        return f"pkill -u {user}"

    def rate_limit(self, port: int, limit: int = 100) -> str:
        """Generate command to apply rate limiting to a port."""
        return (
            f"iptables -A INPUT -p tcp --dport {port} "
            f"-m limit --limit {limit}/min -j ACCEPT"
        )

    def enable_ddos_protection(self, port: int = 80) -> str:
        """Generate command to enable DDoS protection on a port."""
        # Multiple rules for comprehensive protection
        commands = [
            # Rate limit new connections
            f"iptables -A INPUT -p tcp --dport {port} -m conntrack --ctstate NEW "
            f"-m limit --limit 60/s --limit-burst 20 -j ACCEPT",
            # Drop excess
            f"iptables -A INPUT -p tcp --dport {port} -m conntrack --ctstate NEW -j DROP",
        ]
        return " && ".join(commands)

    def collect_forensics(self, incident_id: str) -> str:
        """Generate command to collect forensic data."""
        output_dir = f"{self.working_dir}/forensics/{incident_id}"
        commands = [
            f"mkdir -p {output_dir}",
            f"ps aux > {output_dir}/processes.txt",
            f"netstat -tulpn > {output_dir}/network.txt 2>/dev/null || ss -tulpn > {output_dir}/network.txt",
            f"lsof -i > {output_dir}/open_files.txt 2>/dev/null || true",
            f"echo 'Forensics collected at $(date)' > {output_dir}/timestamp.txt",
        ]
        return " && ".join(commands)

    def safe_cleanup(self, path: str, days: int = 7) -> str:
        """Generate command for safe file cleanup."""
        # Only allow cleanup in specific directories
        safe_prefixes = ["/tmp/", "/var/log/", "/var/cache/"]
        if not any(path.startswith(p) for p in safe_prefixes):
            return f"echo 'Cleanup not allowed for path: {path}'"

        return f"find {path} -type f -mtime +{days} -delete"

    def isolate_host(self, interface: str = "eth0") -> str:
        """Generate command to isolate a host (drop all except SSH)."""
        commands = [
            # Flush existing rules
            "iptables -F",
            # Allow established connections
            "iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT",
            # Allow SSH for management
            "iptables -A INPUT -p tcp --dport 22 -j ACCEPT",
            # Allow loopback
            "iptables -A INPUT -i lo -j ACCEPT",
            # Drop everything else
            "iptables -A INPUT -j DROP",
            "iptables -A OUTPUT -j DROP",
        ]
        return " && ".join(commands)

    def investigate(self, incident_id: str) -> str:
        """Generate command for basic investigation (read-only)."""
        return self.collect_forensics(incident_id)

    def scale_resources(self, service: str = "web") -> str:
        """Generate placeholder command for resource scaling."""
        return f"echo 'Would scale resources for service: {service}'"

    def build_command(self, action: str, incident: Dict[str, Any]) -> str:
        """Build the appropriate command for an action.

        Args:
            action: The action name
            incident: Incident data with parameters

        Returns:
            Command string to execute
        """
        source_ip = incident.get("source_ip", "")
        user = incident.get("user", "")
        incident_id = incident.get("id", "unknown")
        path = incident.get("path", "/tmp")
        port = incident.get("port", 80)

        command_map = {
            "block_ip": lambda: self.block_ip(source_ip),
            "unblock_ip": lambda: self.unblock_ip(source_ip),
            "monitor_ip": lambda: self.monitor_ip(source_ip),
            "revoke_session": lambda: self.kill_user_sessions(user),
            "kill_user_sessions": lambda: self.kill_user_sessions(user),
            "enable_ddos_protection": lambda: self.enable_ddos_protection(port),
            "rate_limit": lambda: self.rate_limit(port),
            "investigate": lambda: self.investigate(incident_id),
            "collect_forensics": lambda: self.collect_forensics(incident_id),
            "cleanup": lambda: self.safe_cleanup(path),
            "isolate_host": lambda: self.isolate_host(),
            "scale_resources": lambda: self.scale_resources(),
        }

        builder = command_map.get(action)
        if builder:
            return builder()

        return f"echo 'Unknown action: {action}'"


class RemediationExecutor:
    """Executes remediation actions based on configured mode.

    Modes:
    - log_only: Just log what would happen
    - sandbox_exec: Execute with echo prefix (dry run)
    - real_exec: Actually execute the commands
    """

    def __init__(self, client: "CloveClient", mode: str, config: Dict[str, Any]):
        self.client = client
        self.mode = mode
        self.config = config

        self.validator = SafetyValidator(config)
        self.command_builder = CommandBuilder(config)

        exec_config = config.get("execution", {})
        self.timeout_ms = exec_config.get("timeout_ms", 5000)
        self.dry_run_prefix = exec_config.get("dry_run_prefix", "echo '[DRY-RUN]'")

    def execute(self, action: str, incident: Dict[str, Any]) -> ExecutionResult:
        """Execute a remediation action.

        Args:
            action: The action name to execute
            incident: Incident data with parameters

        Returns:
            ExecutionResult with success status and details
        """
        start_time = time.time()
        incident_id = incident.get("id", "unknown")

        # Validate action first
        validation = self.validator.validate_action(action, incident)
        if not validation.valid:
            return ExecutionResult(
                success=False,
                action=action,
                mode=self.mode,
                error=f"Validation failed: {'; '.join(validation.errors)}",
                execution_time_ms=int((time.time() - start_time) * 1000)
            )

        # Build the command
        command = self.command_builder.build_command(action, incident)

        # Execute based on mode
        if self.mode == "log_only":
            return self._execute_log_only(action, command, incident_id, start_time)
        elif self.mode == "sandbox_exec":
            return self._execute_sandbox(action, command, incident_id, start_time)
        elif self.mode == "real_exec":
            return self._execute_real(action, command, incident_id, start_time)
        else:
            return ExecutionResult(
                success=False,
                action=action,
                command=command,
                mode=self.mode,
                error=f"Unknown execution mode: {self.mode}",
                execution_time_ms=int((time.time() - start_time) * 1000)
            )

    def _execute_log_only(
        self, action: str, command: str, incident_id: str, start_time: float
    ) -> ExecutionResult:
        """Log-only mode: just record what would happen."""
        return ExecutionResult(
            success=True,
            action=action,
            command=command,
            mode="log_only",
            stdout=f"[LOG-ONLY] Would execute: {command}",
            exit_code=0,
            execution_time_ms=int((time.time() - start_time) * 1000)
        )

    def _execute_sandbox(
        self, action: str, command: str, incident_id: str, start_time: float
    ) -> ExecutionResult:
        """Sandbox mode: execute with echo prefix for dry run."""
        sandbox_command = f"{self.dry_run_prefix} {command}"
        return self._execute_via_clove(action, sandbox_command, "sandbox_exec", start_time)

    def _execute_real(
        self, action: str, command: str, incident_id: str, start_time: float
    ) -> ExecutionResult:
        """Real mode: actually execute the command."""
        return self._execute_via_clove(action, command, "real_exec", start_time)

    def _execute_via_clove(
        self, action: str, command: str, mode: str, start_time: float
    ) -> ExecutionResult:
        """Execute a command via Clove SDK's exec() function.

        Args:
            action: The action name
            command: The command to execute
            mode: The execution mode for logging
            start_time: Start time for duration calculation

        Returns:
            ExecutionResult with execution details
        """
        try:
            result = self.client.exec(command=command, timeout=self.timeout_ms)

            execution_time_ms = int((time.time() - start_time) * 1000)

            if result.get("success"):
                return ExecutionResult(
                    success=True,
                    action=action,
                    command=command,
                    mode=mode,
                    stdout=result.get("stdout", ""),
                    stderr=result.get("stderr", ""),
                    exit_code=result.get("exit_code", 0),
                    execution_time_ms=execution_time_ms
                )
            else:
                return ExecutionResult(
                    success=False,
                    action=action,
                    command=command,
                    mode=mode,
                    stdout=result.get("stdout", ""),
                    stderr=result.get("stderr", ""),
                    exit_code=result.get("exit_code", -1),
                    error=result.get("error", "Execution failed"),
                    execution_time_ms=execution_time_ms
                )

        except Exception as e:
            return ExecutionResult(
                success=False,
                action=action,
                command=command,
                mode=mode,
                error=str(e),
                execution_time_ms=int((time.time() - start_time) * 1000)
            )

    def track_block(
        self, ip: str, incident_id: str, duration_minutes: int = 60
    ) -> Dict[str, Any]:
        """Track an IP block in distributed state for auto-expiration.

        Args:
            ip: The blocked IP address
            incident_id: Associated incident ID
            duration_minutes: How long until the block expires

        Returns:
            Result of the store operation
        """
        now = time.time()
        expires_at = now + (duration_minutes * 60)

        block_data = {
            "ip": ip,
            "blocked_at": now,
            "expires_at": expires_at,
            "incident_id": incident_id,
            "status": "active"
        }

        ttl = duration_minutes * 60
        return self.client.store(
            f"block:{ip}",
            block_data,
            scope="global",
            ttl=ttl
        )

    def check_expirations(self) -> List[Dict[str, Any]]:
        """Check for expired blocks and unblock them.

        Returns:
            List of unblocked IPs with their details
        """
        unblocked = []
        now = time.time()

        # List all block keys
        keys_result = self.client.list_keys(prefix="block:")
        if not keys_result.get("success"):
            return unblocked

        for key in keys_result.get("keys", []):
            # Fetch block data
            data_result = self.client.fetch(key)
            if not data_result.get("success"):
                continue

            block_data = data_result.get("value", {})
            expires_at = block_data.get("expires_at", 0)

            if expires_at > 0 and now >= expires_at:
                ip = block_data.get("ip", "")
                if ip and self.mode == "real_exec":
                    # Actually unblock
                    unblock_cmd = self.command_builder.unblock_ip(ip)
                    self._execute_via_clove("unblock_ip", unblock_cmd, "real_exec", time.time())

                # Remove from tracking
                self.client.delete_key(key)

                unblocked.append({
                    "ip": ip,
                    "incident_id": block_data.get("incident_id"),
                    "blocked_at": block_data.get("blocked_at"),
                    "unblocked_at": now
                })

        return unblocked
