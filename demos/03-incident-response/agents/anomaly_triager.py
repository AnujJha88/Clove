"""Agent: anomaly_triager - assigns severity and escalation decisions.

Supports:
- Triage and severity assignment
- Velocity tracking: detects incident bursts
- Priority-based escalation
- ML-based severity scoring (optional)
- Threat intel enrichment (optional)
- Alert escalation to webhooks (optional)

All configuration is read from the init message config.
"""
from __future__ import annotations

import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils import ensure_sdk_on_path, wait_for_message, log

ensure_sdk_on_path()
from clove_sdk import CloveClient  # noqa: E402

AGENT_NAME = "anomaly_triager"


class VelocityTracker:
    """Tracks incident velocity per system."""

    def __init__(self, window_seconds: float = 60.0):
        self.window = window_seconds
        self.timestamps: Dict[str, List[float]] = defaultdict(list)

    def record(self, system: str) -> None:
        """Record an incident for a system."""
        now = time.time()
        self.timestamps[system].append(now)
        # Prune old entries
        cutoff = now - self.window
        self.timestamps[system] = [t for t in self.timestamps[system] if t > cutoff]

    def get_velocity(self, system: str) -> int:
        """Get incidents per minute for a system."""
        now = time.time()
        cutoff = now - self.window
        self.timestamps[system] = [t for t in self.timestamps[system] if t > cutoff]
        return len(self.timestamps[system])

    def get_all_velocities(self) -> Dict[str, int]:
        """Get velocities for all systems."""
        return {system: self.get_velocity(system) for system in self.timestamps}


class MLScorer:
    """Wrapper for ML severity scoring."""

    def __init__(self, config: Dict[str, Any]):
        self.enabled = config.get("enabled", False)
        self.confidence_threshold = config.get("confidence_threshold", 0.7)
        self.fallback_to_rules = config.get("fallback_to_rules", True)
        self.scorer = None
        self.ml_scored_count = 0
        self.ml_override_count = 0

        if self.enabled:
            model_path = config.get("model_path")
            if model_path:
                try:
                    # Import here to avoid dependency if not used
                    from ml.score import SeverityScorer
                    self.scorer = SeverityScorer(Path(model_path))
                    log(AGENT_NAME, "INFO", f"ML scorer loaded from {model_path}")
                except Exception as e:
                    log(AGENT_NAME, "WARN", f"Failed to load ML model: {e}")
                    self.enabled = False

    def score(
        self,
        incident: Dict[str, Any],
        context: Dict[str, Any],
        rule_severity: str
    ) -> Dict[str, Any]:
        """Score incident with ML model.

        Returns:
            {
                "severity": str,       # Final severity
                "ml_used": bool,       # Whether ML was used
                "ml_confidence": float, # ML confidence if used
                "ml_override": bool,   # Whether ML overrode rules
            }
        """
        if not self.scorer:
            return {"severity": rule_severity, "ml_used": False}

        try:
            result = self.scorer.score(incident, context)
            self.ml_scored_count += 1

            # Check if confidence meets threshold
            if result["confidence"] >= self.confidence_threshold:
                ml_severity = result["severity"]
                ml_override = ml_severity != rule_severity

                if ml_override:
                    self.ml_override_count += 1

                return {
                    "severity": ml_severity,
                    "ml_used": True,
                    "ml_confidence": result["confidence"],
                    "ml_override": ml_override,
                    "rule_severity": rule_severity,
                    "probabilities": result.get("probabilities", {}),
                }
            else:
                # Low confidence, use rules
                return {
                    "severity": rule_severity,
                    "ml_used": True,
                    "ml_confidence": result["confidence"],
                    "ml_override": False,
                    "low_confidence": True,
                }

        except Exception as e:
            log(AGENT_NAME, "ERROR", f"ML scoring failed: {e}")
            if self.fallback_to_rules:
                return {"severity": rule_severity, "ml_used": False, "error": str(e)}
            raise

    def get_stats(self) -> Dict[str, Any]:
        return {
            "ml_enabled": self.enabled,
            "ml_scored_count": self.ml_scored_count,
            "ml_override_count": self.ml_override_count,
        }


def request_enrichment(
    client: CloveClient,
    incident: Dict[str, Any],
    timeout_s: float = 2.0
) -> Optional[Dict[str, Any]]:
    """Request threat intel enrichment for an incident."""
    source_ip = incident.get("source_ip")
    if not source_ip:
        return None

    # Send enrichment request
    request_id = f"enrich_{incident.get('id', 'unknown')}_{time.time()}"
    client.send_message({
        "type": "enrich_incident",
        "incident": incident,
        "request_id": request_id,
        "reply_to": AGENT_NAME,
    }, to_name="threat_intel")

    # Wait for response (with timeout)
    try:
        response = wait_for_message(
            client,
            expected_type="enrichment_result",
            timeout_s=timeout_s
        )
        if response.get("request_id") == request_id:
            return response
    except TimeoutError:
        log(AGENT_NAME, "WARN", f"Threat intel timeout for {source_ip}")

    return None


def request_escalation(
    client: CloveClient,
    incident: Dict[str, Any],
    triage: Dict[str, Any],
    enrichment: Optional[Dict[str, Any]] = None
) -> None:
    """Request alert escalation to webhooks."""
    client.send_message({
        "type": "escalate_alert",
        "incident": incident,
        "triage": triage,
        "enrichment": enrichment,
        "reply_to": "auditor",
    }, to_name="alert_escalator")


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
        playbook = init.get("remediation_playbook", {})
        mode = init.get("mode", "file")
        config = init.get("config", {})

        # Get config values
        triage_config = config.get("triage", {})
        severity_priority = triage_config.get("severity_priority_map", {
            "low": "P4",
            "medium": "P3",
            "high": "P2",
            "critical": "P1",
        })
        velocity_thresholds = triage_config.get("velocity_thresholds", {
            "high": 20,
            "critical": 50,
        })
        velocity_window = triage_config.get("velocity_window_seconds", 60.0)

        service_config = config.get("service", {})
        heartbeat_interval = service_config.get("heartbeat_interval_seconds", 5)

        # ML scoring configuration
        ml_config = config.get("ml_scoring", {})
        ml_scorer = MLScorer(ml_config)

        # Threat intel configuration
        threat_intel_config = config.get("threat_intel", {})
        threat_intel_enabled = threat_intel_config.get("enabled", False)
        enrichment_timeout = threat_intel_config.get("enrichment_timeout_s", 2.0)
        ips_enriched = 0
        malicious_ips = 0

        # Alert escalation configuration
        escalation_config = config.get("alert_escalation", {})
        escalation_enabled = escalation_config.get("enabled", False)
        escalation_severities = set(escalation_config.get("escalate_severities", ["high", "critical"]))
        alerts_escalated = 0

        velocity_tracker = VelocityTracker(window_seconds=velocity_window)

        # Send init acknowledgment
        client.send_message({"type": "init_ack", "agent": AGENT_NAME}, to_name="orchestrator")

        last_heartbeat = time.time()
        incidents_triaged = 0

        while True:
            current_time = time.time()

            # Send heartbeat in continuous mode
            if mode == "continuous" and current_time - last_heartbeat >= heartbeat_interval:
                ml_stats = ml_scorer.get_stats()
                client.send_message({
                    "type": "heartbeat",
                    "agent": AGENT_NAME,
                    "incidents_triaged": incidents_triaged,
                    "velocities": velocity_tracker.get_all_velocities(),
                    "ips_enriched": ips_enriched,
                    "malicious_ips": malicious_ips,
                    "alerts_escalated": alerts_escalated,
                    **ml_stats,
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

            if msg_type == "health_alert":
                # Health alerts can trigger remediation
                system = message.get("system")
                metric = message.get("metric")
                value = message.get("value")

                # Create a synthetic incident for health alerts
                incident_id = f"health_{run_id}_{int(current_time)}"
                incident = {
                    "id": incident_id,
                    "run_id": run_id,
                    "type": f"HIGH_{metric.upper()}",
                    "severity": "high",
                    "title": f"Health alert: {metric} = {value}",
                    "system": system,
                    "detected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }

                # Store and forward
                client.store(f"incident:{run_id}:{incident_id}", incident, scope="global")
                client.send_message({
                    "type": "triage_event",
                    "incident_id": incident_id,
                    "severity": "high",
                    "priority": "P2",
                    "status": "triaged",
                }, to_name="auditor")

                # High severity triggers remediation
                action = playbook.get(f"HIGH_{metric.upper()}")
                if action:
                    client.send_message({
                        "type": "remediate",
                        "incident": incident,
                        "triage": {"priority": "P2", "status": "triaged"},
                        "action": action,
                    }, to_name="remediation_executor")

            elif msg_type == "anomaly_detected":
                incident = message.get("incident", {})
                incident_id = incident.get("id")
                incidents_triaged += 1

                # Validate incident_id is present
                if not incident_id:
                    log(AGENT_NAME, "WARN", "Received anomaly without incident_id, skipping")
                    continue

                rule_severity = incident.get("severity", "low")
                system = incident.get("system", "unknown")
                priority = severity_priority.get(rule_severity, "P4")

                # Track velocity
                velocity_tracker.record(system)
                current_velocity = velocity_tracker.get_velocity(system)

                # Check for velocity-based severity escalation
                velocity_alert = None
                critical_thresh = velocity_thresholds.get("critical", 50)
                high_thresh = velocity_thresholds.get("high", 20)

                if current_velocity > critical_thresh:
                    velocity_alert = "critical"
                    if rule_severity == "low":
                        rule_severity = "medium"
                        priority = severity_priority.get("medium", "P3")
                elif current_velocity > high_thresh:
                    velocity_alert = "high"

                # Step 1: Request threat intel enrichment
                enrichment = None
                if threat_intel_enabled and incident.get("source_ip"):
                    enrichment = request_enrichment(client, incident, enrichment_timeout)
                    if enrichment and enrichment.get("enriched"):
                        ips_enriched += 1
                        rep = enrichment.get("reputation", {})
                        if rep.get("is_malicious"):
                            malicious_ips += 1
                            # Boost severity for malicious IPs
                            if rule_severity == "low":
                                rule_severity = "medium"
                            elif rule_severity == "medium":
                                rule_severity = "high"

                # Step 2: ML scoring (if enabled)
                ml_result = None
                severity = rule_severity
                if ml_scorer.enabled:
                    context = {"velocity": current_velocity}
                    ml_result = ml_scorer.score(incident, context, rule_severity)
                    severity = ml_result["severity"]
                    priority = severity_priority.get(severity, priority)

                # Build triage result
                triage = {
                    "incident_id": incident_id,
                    "run_id": run_id,
                    "severity": severity,
                    "priority": priority,
                    "status": "triaged",
                    "velocity": current_velocity,
                    "velocity_alert": velocity_alert,
                }

                # Add ML info if used
                if ml_result and ml_result.get("ml_used"):
                    triage["ml_confidence"] = ml_result.get("ml_confidence")
                    triage["ml_override"] = ml_result.get("ml_override", False)

                # Add threat intel info if available
                if enrichment and enrichment.get("enriched"):
                    rep = enrichment.get("reputation", {})
                    triage["threat_score"] = rep.get("score")
                    triage["threat_is_malicious"] = rep.get("is_malicious")

                client.store(f"triage:{run_id}:{incident_id}", triage, scope="global")

                client.send_message({
                    "type": "triage_event",
                    "incident_id": incident_id,
                    "severity": severity,
                    "priority": priority,
                    "status": "triaged",
                    "velocity": current_velocity,
                    "ml_confidence": triage.get("ml_confidence"),
                    "threat_score": triage.get("threat_score"),
                }, to_name="auditor")

                # Step 3: Alert escalation for high/critical
                if escalation_enabled and severity in escalation_severities:
                    request_escalation(client, incident, triage, enrichment)
                    alerts_escalated += 1

                if severity in {"high", "critical"}:
                    action = playbook.get(incident.get("type", ""))

                    client.send_message({
                        "type": "remediate",
                        "incident": incident,
                        "triage": triage,
                        "action": action,
                    }, to_name="remediation_executor")

                    # Also notify orchestrator for dashboard
                    client.send_message({
                        "type": "remediation_event",
                        "incident_id": incident_id,
                        "system": system,
                        "action": action.get("action") if action else "none",
                        "status": "pending",
                    }, to_name="orchestrator")
                else:
                    client.send_message({
                        "type": "remediation_event",
                        "incident_id": incident_id,
                        "status": "not_required",
                        "action": None
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
