"""Agent: auditor - compiles incident report and audit summary.

Supports:
- Original finalize report functionality
- Periodic reports: every 5 minutes in continuous mode
- Statistics aggregation across all incidents

All configuration is read from the init message config.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Any

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

AGENT_NAME = "auditor"


class ReportAggregator:
    """Aggregates statistics for periodic reports."""

    def __init__(self):
        self.incidents: List[str] = []
        self.triage_events: Dict[str, Dict] = {}
        self.remediation_events: Dict[str, Dict] = {}
        self.health_alerts: List[Dict] = []

        # Counters
        self.by_severity: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        self.by_system: Dict[str, int] = {}
        self.remediations_logged = 0
        self.remediations_skipped = 0

        # Timing
        self.start_time = time.time()
        self.last_report_time = time.time()
        self.report_count = 0

    def record_incident(self, incident_id: str, severity: str, system: str) -> None:
        """Record an incident."""
        self.incidents.append(incident_id)
        sev = severity.lower()
        if sev in self.by_severity:
            self.by_severity[sev] += 1
        self.by_system[system] = self.by_system.get(system, 0) + 1

    def record_triage(self, incident_id: str, triage: Dict) -> None:
        """Record a triage event."""
        self.triage_events[incident_id] = triage

    def record_remediation(self, incident_id: str, event: Dict) -> None:
        """Record a remediation event."""
        self.remediation_events[incident_id] = event
        status = event.get("status", "unknown")
        if status == "logged":
            self.remediations_logged += 1
        elif status in ("no_playbook", "not_required"):
            self.remediations_skipped += 1

    def record_health_alert(self, alert: Dict) -> None:
        """Record a health alert."""
        self.health_alerts.append(alert)

    def generate_summary(self) -> Dict[str, Any]:
        """Generate a summary for reporting."""
        elapsed = time.time() - self.start_time
        return {
            "total_incidents": len(self.incidents),
            "by_severity": dict(self.by_severity),
            "by_system": dict(self.by_system),
            "remediations": {
                "logged": self.remediations_logged,
                "skipped": self.remediations_skipped,
            },
            "health_alerts": len(self.health_alerts),
            "runtime_seconds": elapsed,
            "report_count": self.report_count,
        }

    def reset_for_period(self) -> None:
        """Reset counters for a new period (but keep totals)."""
        self.last_report_time = time.time()
        self.report_count += 1


def main() -> int:
    client = CloveClient()
    if not client.connect():
        log(AGENT_NAME, "ERROR", "Failed to connect to Clove kernel")
        return 1

    aggregator = ReportAggregator()

    try:
        client.register_name(AGENT_NAME)

        try:
            init = wait_for_message(client, expected_type="init", timeout_s=30.0)
        except TimeoutError as e:
            log(AGENT_NAME, "ERROR", f"Timeout waiting for init: {e}")
            return 1

        run_id = init.get("run_id", "run_000")
        logs_dir = Path(init.get("logs_dir", "logs"))
        reports_dir = Path(init.get("reports_dir", logs_dir))
        mode = init.get("mode", "file")
        base_dir = lab_root()
        config = init.get("config", {})

        # Get config values
        service_config = config.get("service", {})
        heartbeat_interval = service_config.get("heartbeat_interval_seconds", 5)

        # Validate run_id doesn't contain path traversal
        if ".." in run_id or "/" in run_id or "\\" in run_id:
            log(AGENT_NAME, "ERROR", f"Invalid run_id contains path characters: {run_id}")
            return 1

        # Send init acknowledgment
        client.send_message({"type": "init_ack", "agent": AGENT_NAME}, to_name="orchestrator")

        last_heartbeat = time.time()

        while True:
            current_time = time.time()

            # Send heartbeat in continuous mode
            if mode == "continuous" and current_time - last_heartbeat >= heartbeat_interval:
                client.send_message({
                    "type": "heartbeat",
                    "agent": AGENT_NAME,
                    "incidents_tracked": len(aggregator.incidents),
                    "reports_generated": aggregator.report_count,
                }, to_name="orchestrator")
                last_heartbeat = current_time

            timeout = 0.5 if mode == "continuous" else 60.0
            try:
                message = wait_for_message(client, timeout_s=timeout)
            except TimeoutError:
                if mode == "continuous":
                    continue
                log(AGENT_NAME, "WARN", "Timeout waiting for message, continuing...")
                continue

            msg_type = message.get("type")

            if msg_type == "scan_complete":
                # File mode: record incidents from scan
                incident_ids = list(message.get("incidents", []))
                aggregator.incidents.extend(incident_ids)
                log(AGENT_NAME, "INFO", f"Received scan_complete with {len(incident_ids)} incidents")

            elif msg_type == "triage_event":
                incident_id = message.get("incident_id")
                if incident_id:
                    aggregator.record_triage(incident_id, message)
                    severity = message.get("severity", "low")
                    # Approximate system from incident_id or use 'unknown'
                    system = message.get("system", "unknown")
                    if incident_id not in aggregator.incidents:
                        aggregator.record_incident(incident_id, severity, system)
                    log(AGENT_NAME, "DEBUG", f"Recorded triage event for {incident_id}")

            elif msg_type == "remediation_event":
                incident_id = message.get("incident_id")
                if incident_id:
                    aggregator.record_remediation(incident_id, message)
                    log(AGENT_NAME, "DEBUG", f"Recorded remediation event for {incident_id}")

            elif msg_type == "health_alert":
                aggregator.record_health_alert(message)

            elif msg_type == "generate_report":
                # Periodic report request
                report_type = message.get("report_type", "periodic")
                stats_from_orchestrator = message.get("stats", {})
                requested_reports_dir = message.get("reports_dir")
                if requested_reports_dir:
                    reports_dir = Path(requested_reports_dir)

                report = generate_report(
                    client, run_id, aggregator, report_type,
                    reports_dir, base_dir, stats_from_orchestrator
                )

                if report.get("success"):
                    log(AGENT_NAME, "INFO", f"Generated {report_type} report: {report.get('path')}")
                    client.send_message({
                        "type": "periodic_report",
                        "run_id": run_id,
                        "report_type": report_type,
                        "path": report.get("path"),
                    }, to_name="orchestrator")
                else:
                    log(AGENT_NAME, "ERROR", f"Failed to generate report: {report.get('error')}")

                aggregator.reset_for_period()

            elif msg_type == "finalize":
                # Original finalize behavior
                expected_count = message.get("incident_count", 0)
                log(AGENT_NAME, "INFO", f"Finalize received, expected_count={expected_count}")

                # Wait briefly for any in-flight messages
                drain_deadline = time.time() + 0.5
                while time.time() < drain_deadline:
                    try:
                        drain_msg = wait_for_message(client, timeout_s=0.1)
                        drain_type = drain_msg.get("type")
                        if drain_type == "triage_event":
                            incident_id = drain_msg.get("incident_id")
                            if incident_id:
                                aggregator.record_triage(incident_id, drain_msg)
                        elif drain_type == "remediation_event":
                            incident_id = drain_msg.get("incident_id")
                            if incident_id:
                                aggregator.record_remediation(incident_id, drain_msg)
                    except TimeoutError:
                        break

                report = {
                    "run_id": run_id,
                    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "incident_count": len(aggregator.incidents),
                    "incidents": [],
                    "triage": aggregator.triage_events,
                    "remediation": aggregator.remediation_events,
                }

                for incident_id in aggregator.incidents:
                    fetched = client.fetch(f"incident:{run_id}:{incident_id}")
                    if fetched.get("success") and fetched.get("exists"):
                        report["incidents"].append(fetched.get("value"))

                audit_log = client.get_audit_log(limit=50)
                if audit_log.get("success"):
                    report["audit_log_sample"] = audit_log.get("entries", [])[:10]

                report_path = logs_dir / run_id / "incident_report.json"

                try:
                    validate_path_within(report_path, base_dir)
                except ValueError as e:
                    log(AGENT_NAME, "ERROR", f"Path validation failed: {e}")
                    client.send_message({
                        "type": "audit_report",
                        "run_id": run_id,
                        "error": "path validation failed"
                    }, to_name="orchestrator")
                    continue

                payload = json.dumps(report, indent=2, sort_keys=True)
                write_result = client.write_file(str(report_path), payload)

                if not write_result.get("success"):
                    log(AGENT_NAME, "ERROR", f"Failed to write report: {write_result.get('error')}")
                    client.send_message({
                        "type": "audit_report",
                        "run_id": run_id,
                        "error": write_result.get("error", "write failed")
                    }, to_name="orchestrator")
                else:
                    log(AGENT_NAME, "INFO", f"Report written to {report_path}")
                    client.send_message({
                        "type": "audit_report",
                        "run_id": run_id,
                        "path": str(report_path)
                    }, to_name="orchestrator")

            elif msg_type == "shutdown":
                log(AGENT_NAME, "INFO", "Received shutdown")
                break

    except TimeoutError as e:
        log(AGENT_NAME, "ERROR", f"Fatal timeout: {e}")
        return 1
    finally:
        client.disconnect()

    return 0


def generate_report(
    client: CloveClient,
    run_id: str,
    aggregator: ReportAggregator,
    report_type: str,
    reports_dir: Path,
    base_dir: Path,
    orchestrator_stats: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate a periodic or final report."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_filename = f"report_{report_type}_{timestamp}.json"
    report_path = reports_dir / run_id / report_filename

    try:
        validate_path_within(report_path, base_dir)
    except ValueError as e:
        return {"success": False, "error": f"path validation failed: {e}"}

    # Combine local aggregator stats with orchestrator stats
    summary = aggregator.generate_summary()

    # Use orchestrator stats if available (they have dashboard-accurate counts)
    if orchestrator_stats:
        summary["orchestrator_stats"] = orchestrator_stats
        if "total_events" in orchestrator_stats:
            summary["total_events"] = orchestrator_stats["total_events"]
        if "events_by_severity" in orchestrator_stats:
            summary["events_by_severity"] = orchestrator_stats["events_by_severity"]

    report = {
        "run_id": run_id,
        "report_type": report_type,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": summary,
        "recent_incidents": [],
        "recent_triage": list(aggregator.triage_events.values())[-20:],
        "recent_remediation": list(aggregator.remediation_events.values())[-20:],
        "health_alerts": aggregator.health_alerts[-10:],
    }

    # Fetch recent incidents from store
    for incident_id in aggregator.incidents[-50:]:
        fetched = client.fetch(f"incident:{run_id}:{incident_id}")
        if fetched.get("success") and fetched.get("exists"):
            report["recent_incidents"].append(fetched.get("value"))

    # Add audit log sample
    audit_log = client.get_audit_log(limit=20)
    if audit_log.get("success"):
        report["audit_log_sample"] = audit_log.get("entries", [])[:10]

    payload = json.dumps(report, indent=2, sort_keys=True, default=str)
    write_result = client.write_file(str(report_path), payload)

    if not write_result.get("success"):
        return {"success": False, "error": write_result.get("error", "write failed")}

    return {"success": True, "path": str(report_path)}


if __name__ == "__main__":
    raise SystemExit(main())
