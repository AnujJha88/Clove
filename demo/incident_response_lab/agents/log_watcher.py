"""Agent: log_watcher - monitors real log sources and emits anomaly alerts.

Supports two modes:
- File scan mode: Reads log file and detects incidents (original)
- Continuous mode: Actively tails real log files and journalctl

All configuration is read from the init message config.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils import (
    ensure_sdk_on_path,
    wait_for_message,
    MultiSourceLogTailer,
    parse_syslog_line,
    extract_ip_from_log,
    extract_user_from_log,
)

ensure_sdk_on_path()
from clove_sdk import CloveClient  # noqa: E402

AGENT_NAME = "log_watcher"


def extract_value(line: str, key: str) -> str | None:
    match = re.search(rf"{re.escape(key)}=([^\s\"]+)", line)
    if match:
        return match.group(1).strip('"')
    return None


def detect_incident(line: str, rules: dict) -> tuple[str, dict] | None:
    """Check if a log line matches any detection rule."""
    for keyword, rule in rules.items():
        if keyword.lower() in line.lower():
            rule_data = rule if isinstance(rule, dict) else {"severity": rule}
            return keyword, rule_data
    return None


def determine_system_from_source(source: str, line: str) -> str:
    """Determine which system a log entry belongs to based on source and content."""
    # Check source path
    if "auth" in source.lower():
        return "auth"
    if "syslog" in source.lower():
        # Parse the line to determine system
        parsed = parse_syslog_line(line)
        process = parsed.get("process", "").lower()
        if process in ("sshd", "sudo", "su", "login", "pam"):
            return "auth"
        if process in ("nginx", "apache", "httpd"):
            return "web"
        if process in ("mysql", "postgres", "mongodb"):
            return "database"
        return "network"

    # Check journalctl units
    if "journal" in source.lower():
        parsed = parse_syslog_line(line)
        process = parsed.get("process", "").lower()
        if "ssh" in process or "auth" in process:
            return "auth"
        if "nginx" in process or "apache" in process:
            return "web"
        if "docker" in process or "container" in process:
            return "network"

    return "network"


def log(msg: str) -> None:
    """Debug logging to stderr."""
    print(f"[log_watcher] {msg}", file=sys.stderr, flush=True)


def main() -> int:
    log("Starting")
    client = CloveClient()
    if not client.connect():
        log("ERROR: Failed to connect to Clove kernel")
        return 1

    tailer = None

    try:
        reg_result = client.register_name(AGENT_NAME)
        log(f"Registered: {reg_result}")

        log("Waiting for init...")
        try:
            init = wait_for_message(client, expected_type="init", timeout_s=30.0)
        except TimeoutError as e:
            log(f"ERROR: Timeout waiting for init: {e}")
            return 1

        run_id = init.get("run_id", "run_000")
        rules = init.get("rules", {})
        reply_to = init.get("reply_to", "orchestrator")
        mode = init.get("mode", "file")  # "file" or "continuous"
        config = init.get("config", {})

        # Get config values
        service_config = config.get("service", {})
        heartbeat_interval = service_config.get("heartbeat_interval_seconds", 5)
        log_sources_config = config.get("log_sources", {})

        log(f"Got init: run_id={run_id}, mode={mode}, rules={list(rules.keys())}, reply_to={reply_to}")

        # Send init acknowledgment
        client.send_message({"type": "init_ack", "agent": AGENT_NAME}, to_name="orchestrator")

        # Continuous mode state
        event_counter = 0
        last_heartbeat = time.time()
        last_status_report = time.time()

        # Initialize log tailer for continuous mode
        if mode == "continuous":
            tailer = MultiSourceLogTailer(log_sources_config)
            status = tailer.get_status()
            log(f"Log tailer initialized: files={status['files']['count']}, journal={status['journal']['running']}")

            # Report initial log source status
            client.send_message({
                "type": "log_source_status",
                "status": status,
            }, to_name="orchestrator")

        while True:
            current_time = time.time()

            # Send heartbeat in continuous mode
            if mode == "continuous" and current_time - last_heartbeat >= heartbeat_interval:
                client.send_message({
                    "type": "heartbeat",
                    "agent": AGENT_NAME,
                    "events_processed": event_counter,
                }, to_name="orchestrator")
                last_heartbeat = current_time

            # Periodic status report for log sources
            if mode == "continuous" and tailer and current_time - last_status_report >= 60:
                status = tailer.get_status()
                client.send_message({
                    "type": "log_source_status",
                    "status": status,
                }, to_name="orchestrator")
                last_status_report = current_time

            # Check for IPC messages (short timeout to not block log polling)
            try:
                message = wait_for_message(client, timeout_s=0.1)
                msg_type = message.get("type")
                log(f"Got message type={msg_type}")

                if msg_type == "scan_logs":
                    # File scan mode (original behavior)
                    log_path = message.get("log_path")
                    log(f"scan_logs: path={log_path}")
                    if not log_path:
                        log("ERROR: missing log_path")
                        client.send_message({
                            "type": "scan_complete",
                            "run_id": run_id,
                            "count": 0,
                            "incidents": [],
                            "error": "missing log_path"
                        }, to_name=reply_to)
                        continue

                    log(f"Reading file: {log_path}")
                    read_result = client.read_file(log_path)
                    log(f"read_file result: success={read_result.get('success')}, size={read_result.get('size', 0)}")
                    if not read_result.get("success"):
                        log(f"ERROR: read failed: {read_result.get('error')}")
                        client.send_message({
                            "type": "scan_complete",
                            "run_id": run_id,
                            "count": 0,
                            "incidents": [],
                            "error": read_result.get("error", "read failed")
                        }, to_name=reply_to)
                        continue

                    content = read_result.get("content", "")
                    log(f"Content lines: {len(content.splitlines())}")
                    incidents = []
                    counter = 0
                    for line in content.splitlines():
                        detected = detect_incident(line, rules)
                        if not detected:
                            continue
                        counter += 1
                        incident_type, rule_data = detected
                        incident_id = f"inc_{run_id}_{counter:02d}"
                        log(f"Detected incident: {incident_id} ({incident_type})")
                        incident = {
                            "id": incident_id,
                            "run_id": run_id,
                            "type": incident_type,
                            "severity": rule_data.get("severity", "low"),
                            "title": rule_data.get("title", incident_type),
                            "line": line,
                            "source_ip": extract_value(line, "src") or extract_ip_from_log(line),
                            "user": extract_value(line, "user") or extract_user_from_log(line),
                            "detected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "status": "detected"
                        }
                        incidents.append(incident_id)
                        client.store(f"incident:{run_id}:{incident_id}", incident, scope="global")
                        client.send_message({
                            "type": "anomaly_detected",
                            "incident": incident
                        }, to_name="anomaly_triager")

                    log(f"Sending scan_complete to {reply_to} with {len(incidents)} incidents")
                    send_result = client.send_message({
                        "type": "scan_complete",
                        "run_id": run_id,
                        "count": len(incidents),
                        "incidents": incidents
                    }, to_name=reply_to)
                    log(f"scan_complete send result: {send_result}")

                elif msg_type == "shutdown":
                    log("Received shutdown")
                    break

                else:
                    log(f"Ignoring unknown message type: {msg_type}")

            except TimeoutError:
                # Normal in continuous mode - proceed to poll logs
                pass

            # Continuous mode: poll real log sources
            if mode == "continuous" and tailer:
                entries = tailer.poll(timeout_ms=50)

                for entry in entries:
                    # Check for incidents
                    detected = detect_incident(entry.line, rules)
                    if not detected:
                        continue

                    event_counter += 1
                    incident_type, rule_data = detected
                    incident_id = f"inc_{run_id}_{event_counter:04d}"
                    event_id = f"evt_{run_id}_{event_counter:06d}"

                    # Determine system from log source
                    system = determine_system_from_source(entry.source, entry.line)

                    # Extract context from log line
                    parsed = parse_syslog_line(entry.line)
                    source_ip = extract_ip_from_log(entry.line)
                    user = extract_user_from_log(entry.line)

                    incident = {
                        "id": incident_id,
                        "event_id": event_id,
                        "run_id": run_id,
                        "type": incident_type,
                        "severity": rule_data.get("severity", "low"),
                        "title": rule_data.get("title", incident_type),
                        "system": system,
                        "message": parsed.get("message", entry.line),
                        "line": entry.line,
                        "source": entry.source,
                        "source_type": entry.source_type,
                        "source_ip": source_ip,
                        "user": user,
                        "process": parsed.get("process"),
                        "detected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "detected",
                    }

                    # Store incident
                    client.store(f"incident:{run_id}:{incident_id}", incident, scope="global")

                    # Send to anomaly_triager
                    client.send_message({
                        "type": "anomaly_detected",
                        "incident": incident,
                    }, to_name="anomaly_triager")

                    # Also notify orchestrator for dashboard
                    client.send_message({
                        "type": "log_event",
                        "incident_id": incident_id,
                        "severity": incident["severity"],
                        "system": system,
                        "event_type": incident_type,
                        "source": entry.source,
                    }, to_name="orchestrator")

                    log(f"Detected: {incident_id} [{incident['severity']}] {incident_type} from {entry.source}")

            # Small sleep to prevent CPU spin
            time.sleep(0.05)

    except TimeoutError as e:
        log(f"ERROR: Fatal timeout: {e}")
        return 1
    finally:
        if tailer:
            tailer.close()
        log("Disconnecting")
        client.disconnect()

    log("Exiting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
