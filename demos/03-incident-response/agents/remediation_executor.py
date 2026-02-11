"""Agent: remediation_executor - executes remediation actions with multiple modes.

Supports three execution modes:
- log_only: Records what actions WOULD be taken without executing them
- sandbox_exec: Builds real commands, executes with echo prefix (dry run)
- real_exec: Actually executes commands via Clove SDK

Features:
- Safety validation (blocks internal IPs, protects system users)
- Rate limiting for blocking actions
- Auto-expiration tracking for blocks
- Detailed audit trail for all decisions

All configuration is read from the init message config.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils import (
    ensure_sdk_on_path,
    wait_for_message,
    validate_path_within,
    log,
    lab_root,
)

ensure_sdk_on_path()
from clove_sdk import CloveClient  # noqa: E402

# Import the new execution engine
from remediation_actions import (
    RemediationExecutor,
    SafetyValidator,
    ExecutionResult,
)

AGENT_NAME = "remediation_executor"


def append_to_log(client: CloveClient, log_path: Path, message: str) -> dict:
    """Safely append message to log file using SDK write_file."""
    read_result = client.read_file(str(log_path))
    existing = ""
    if read_result.get("success") and read_result.get("content"):
        existing = read_result.get("content", "")

    new_content = existing + message + "\n" if existing else message + "\n"
    return client.write_file(str(log_path), new_content)


def build_log_entry(
    action_name: str,
    action_desc: str,
    incident: Dict[str, Any],
    result: ExecutionResult,
    remediation_mode: str,
) -> str:
    """Build a detailed log entry for the remediation action."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    incident_id = incident.get("id", "unknown")
    system = incident.get("system", "unknown")

    # Determine status label based on mode and result
    if remediation_mode == "log_only":
        status_label = "WOULD_EXECUTE"
    elif remediation_mode == "sandbox_exec":
        status_label = "DRY_RUN"
    else:
        status_label = "EXECUTED" if result.success else "FAILED"

    log_entry = (
        f"[{timestamp}] {status_label}: {action_name}\n"
        f"  Incident: {incident_id}\n"
        f"  System: {system}\n"
        f"  Description: {action_desc}\n"
        f"  Incident Type: {incident.get('type', 'unknown')}\n"
        f"  Severity: {incident.get('severity', 'unknown')}\n"
        f"  Source IP: {incident.get('source_ip', 'N/A')}\n"
        f"  User: {incident.get('user', 'N/A')}\n"
        f"  Mode: {remediation_mode}\n"
    )

    # Add command and execution details for non-log_only modes
    if remediation_mode != "log_only" and result.command:
        log_entry += f"  Command: {result.command}\n"
        if result.exit_code != 0:
            log_entry += f"  Exit Code: {result.exit_code}\n"
        if result.stderr:
            log_entry += f"  Stderr: {result.stderr[:200]}\n"
        log_entry += f"  Execution Time: {result.execution_time_ms}ms\n"

    if not result.success and result.error:
        log_entry += f"  Error: {result.error}\n"

    log_entry += "---"
    return log_entry


def main() -> int:
    client = CloveClient()
    if not client.connect():
        log(AGENT_NAME, "ERROR", "Failed to connect to Clove kernel")
        return 1

    try:
        client.register_name(AGENT_NAME)

        try:
            init = wait_for_message(client, expected_type="init", timeout_s=30.0)
        except TimeoutError as e:
            log(AGENT_NAME, "ERROR", f"Timeout waiting for init: {e}")
            return 1

        run_id = init.get("run_id", "run_000")
        artifacts_dir = Path(init.get("artifacts_dir", "artifacts"))
        mode = init.get("mode", "file")
        base_dir = lab_root()
        config = init.get("config", {})

        # Get config values
        remediation_config = config.get("remediation", {})
        remediation_mode = remediation_config.get("mode", "log_only")

        # Expiration tracking config
        expiration_config = remediation_config.get("expiration", {})
        expiration_enabled = expiration_config.get("enabled", True)
        expiration_check_interval = expiration_config.get("check_interval_seconds", 30)

        # Safety config
        safety_config = remediation_config.get("safety", {})
        default_block_duration = safety_config.get("default_block_duration_minutes", 60)

        service_config = config.get("service", {})
        heartbeat_interval = service_config.get("heartbeat_interval_seconds", 5)

        # Validate run_id doesn't contain path traversal
        if ".." in run_id or "/" in run_id or "\\" in run_id:
            log(AGENT_NAME, "ERROR", f"Invalid run_id contains path characters: {run_id}")
            return 1

        # Initialize the execution engine
        executor = RemediationExecutor(client, remediation_mode, remediation_config)
        validator = SafetyValidator(remediation_config)

        # Send init acknowledgment
        client.send_message({"type": "init_ack", "agent": AGENT_NAME}, to_name="orchestrator")

        last_heartbeat = time.time()
        last_expiration_check = time.time()
        remediations_executed = 0
        remediations_blocked = 0
        remediations_skipped = 0

        log(AGENT_NAME, "INFO", f"Running in {remediation_mode} mode")

        while True:
            current_time = time.time()

            # Send heartbeat in continuous mode
            if mode == "continuous" and current_time - last_heartbeat >= heartbeat_interval:
                client.send_message({
                    "type": "heartbeat",
                    "agent": AGENT_NAME,
                    "remediations_executed": remediations_executed,
                    "remediations_blocked": remediations_blocked,
                    "remediations_skipped": remediations_skipped,
                    "mode": remediation_mode,
                }, to_name="orchestrator")
                last_heartbeat = current_time

            # Check for expired blocks
            if expiration_enabled and current_time - last_expiration_check >= expiration_check_interval:
                unblocked = executor.check_expirations()
                for item in unblocked:
                    log(AGENT_NAME, "INFO", f"Auto-unblocked expired IP: {item.get('ip')}")
                    client.send_message({
                        "type": "remediation_event",
                        "incident_id": item.get("incident_id", ""),
                        "system": "network",
                        "status": "unblocked",
                        "action": "unblock_ip",
                        "mode": remediation_mode,
                        "ip": item.get("ip"),
                    }, to_name="auditor")
                last_expiration_check = current_time

            timeout = 0.5 if mode == "continuous" else 60.0
            try:
                message = wait_for_message(client, timeout_s=timeout)
            except TimeoutError:
                if mode == "continuous":
                    continue
                log(AGENT_NAME, "WARN", "Timeout waiting for message, continuing...")
                continue

            msg_type = message.get("type")

            if msg_type == "remediate":
                incident = message.get("incident", {})
                action = message.get("action")
                incident_id = incident.get("id", "unknown")
                system = incident.get("system", "unknown")
                severity = incident.get("severity", "medium")

                # No action specified
                if not action:
                    remediations_skipped += 1
                    client.send_message({
                        "type": "remediation_event",
                        "incident_id": incident_id,
                        "system": system,
                        "status": "no_playbook",
                        "action": None
                    }, to_name="auditor")

                    client.send_message({
                        "type": "remediation_event",
                        "incident_id": incident_id,
                        "system": system,
                        "status": "no_playbook",
                        "action": "none",
                    }, to_name="orchestrator")
                    continue

                action_name = action.get("action", "unknown")
                action_desc = action.get("description", "")
                action_path = artifacts_dir / run_id / "remediation_actions.log"

                # Validate path is within allowed directory
                try:
                    validate_path_within(action_path, base_dir)
                except ValueError as e:
                    log(AGENT_NAME, "ERROR", f"Path validation failed: {e}")
                    client.send_message({
                        "type": "remediation_event",
                        "incident_id": incident_id,
                        "system": system,
                        "status": "failed",
                        "action": action_name,
                        "error": "path validation failed"
                    }, to_name="auditor")
                    continue

                # Pre-validate action with safety validator
                validation = validator.validate_action(action_name, incident)
                if not validation.valid:
                    remediations_blocked += 1
                    log(AGENT_NAME, "WARN", f"Action blocked by safety validator: {validation.errors}")

                    client.send_message({
                        "type": "remediation_blocked",
                        "incident_id": incident_id,
                        "system": system,
                        "action": action_name,
                        "errors": validation.errors,
                        "mode": remediation_mode,
                    }, to_name="auditor")

                    client.send_message({
                        "type": "remediation_event",
                        "incident_id": incident_id,
                        "system": system,
                        "status": "blocked",
                        "action": action_name,
                    }, to_name="orchestrator")
                    continue

                # Check if approval is required
                if validator.requires_approval(action_name, severity):
                    log(AGENT_NAME, "INFO", f"Action {action_name} requires approval (not auto-executing)")
                    client.send_message({
                        "type": "approval_required",
                        "incident_id": incident_id,
                        "system": system,
                        "action": action_name,
                        "severity": severity,
                        "reason": f"High-impact action '{action_name}' requires manual approval",
                    }, to_name="auditor")

                    client.send_message({
                        "type": "remediation_event",
                        "incident_id": incident_id,
                        "system": system,
                        "status": "pending_approval",
                        "action": action_name,
                    }, to_name="orchestrator")
                    continue

                # Execute the remediation action
                result = executor.execute(action_name, incident)

                if result.success:
                    remediations_executed += 1

                    # Track blocks for auto-expiration
                    if action_name == "block_ip" and remediation_mode in ("sandbox_exec", "real_exec"):
                        source_ip = incident.get("source_ip", "")
                        if source_ip:
                            executor.track_block(source_ip, incident_id, default_block_duration)

                    # Build and write log entry
                    log_entry = build_log_entry(action_name, action_desc, incident, result, remediation_mode)
                    write_result = append_to_log(client, action_path, log_entry)

                    if not write_result.get("success"):
                        log(AGENT_NAME, "ERROR", f"Failed to write remediation log: {write_result.get('error')}")

                    # Determine status based on mode
                    if remediation_mode == "log_only":
                        status = "logged"
                    elif remediation_mode == "sandbox_exec":
                        status = "dry_run"
                    else:
                        status = "executed"

                    # Store record in distributed state
                    store_record = {
                        "incident_id": incident_id,
                        "run_id": run_id,
                        "system": system,
                        "action": action_name,
                        "description": action_desc,
                        "log_path": str(action_path),
                        "write_result": write_result,
                        "status": status,
                        "mode": remediation_mode,
                        "timestamp": result.timestamp,
                        "command": result.command,
                        "exit_code": result.exit_code,
                        "execution_time_ms": result.execution_time_ms,
                        "incident_type": incident.get("type"),
                        "incident_severity": incident.get("severity"),
                    }
                    client.store(f"remediation:{run_id}:{incident_id}", store_record, scope="global")

                    # Notify auditor with full execution details
                    client.send_message({
                        "type": "remediation_event",
                        "incident_id": incident_id,
                        "system": system,
                        "status": status,
                        "action": action_name,
                        "mode": remediation_mode,
                        "command": result.command if remediation_mode != "log_only" else "",
                        "exit_code": result.exit_code,
                        "execution_time_ms": result.execution_time_ms,
                        "write_result": {
                            "success": write_result.get("success"),
                            "error": write_result.get("error")
                        }
                    }, to_name="auditor")

                    # Notify orchestrator for dashboard
                    client.send_message({
                        "type": "remediation_event",
                        "incident_id": incident_id,
                        "system": system,
                        "status": status,
                        "action": action_name,
                        "mode": remediation_mode,
                        "command": result.command[:50] if result.command else "",
                        "exit_code": result.exit_code,
                    }, to_name="orchestrator")

                    mode_label = {
                        "log_only": "(would execute)",
                        "sandbox_exec": "(dry run)",
                        "real_exec": "(executed)",
                    }.get(remediation_mode, "")

                    log(AGENT_NAME, "INFO", f"Remediation {action_name} for {incident_id} {mode_label}")

                else:
                    # Execution failed
                    log(AGENT_NAME, "ERROR", f"Remediation failed: {result.error}")

                    client.send_message({
                        "type": "remediation_failed",
                        "incident_id": incident_id,
                        "system": system,
                        "action": action_name,
                        "mode": remediation_mode,
                        "error": result.error,
                        "command": result.command,
                        "stderr": result.stderr[:500] if result.stderr else "",
                        "exit_code": result.exit_code,
                    }, to_name="auditor")

                    client.send_message({
                        "type": "remediation_event",
                        "incident_id": incident_id,
                        "system": system,
                        "status": "failed",
                        "action": action_name,
                    }, to_name="orchestrator")

            elif msg_type == "approve_action":
                # Handle manual approval of pending actions
                incident_id = message.get("incident_id")
                action_name = message.get("action")
                incident = message.get("incident", {})

                log(AGENT_NAME, "INFO", f"Received approval for {action_name} on {incident_id}")

                # Execute the approved action
                result = executor.execute(action_name, incident)

                status = "executed" if result.success else "failed"
                client.send_message({
                    "type": "remediation_event",
                    "incident_id": incident_id,
                    "system": incident.get("system", "unknown"),
                    "status": status,
                    "action": action_name,
                    "mode": remediation_mode,
                    "approved": True,
                }, to_name="auditor")

            elif msg_type == "shutdown":
                log(AGENT_NAME, "INFO", "Received shutdown")
                break

    except TimeoutError as e:
        log(AGENT_NAME, "ERROR", f"Fatal timeout: {e}")
        return 1
    finally:
        client.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
