"""Agent: alert_escalator - webhook notifications for critical alerts.

Sends alerts to external services:
- Slack (Block Kit format)
- Discord (Embed format)
- PagerDuty (Events API v2)
- Generic webhooks (JSON payload)

Uses Clove SDK http() for webhook delivery.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils import ensure_sdk_on_path, wait_for_message, log

ensure_sdk_on_path()
from clove_sdk import CloveClient  # noqa: E402

AGENT_NAME = "alert_escalator"


@dataclass
class WebhookConfig:
    """Configuration for a webhook destination."""
    name: str
    type: str  # slack, discord, pagerduty, generic
    url: str
    severity_filter: List[str] = field(default_factory=lambda: ["critical", "high"])
    routing_key: Optional[str] = None  # For PagerDuty
    enabled: bool = True


class WebhookFormatter:
    """Format alerts for different webhook destinations."""

    @staticmethod
    def format_slack(incident: Dict, triage: Dict, enrichment: Optional[Dict] = None) -> Dict:
        """Format alert as Slack Block Kit message."""
        severity = triage.get("severity", incident.get("severity", "unknown"))
        severity_emoji = {
            "critical": ":rotating_light:",
            "high": ":warning:",
            "medium": ":large_yellow_circle:",
            "low": ":information_source:",
        }.get(severity, ":grey_question:")

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{severity_emoji} Security Alert: {incident.get('type', 'Unknown')}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Severity:*\n{severity.upper()}"},
                    {"type": "mrkdwn", "text": f"*Priority:*\n{triage.get('priority', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*System:*\n{incident.get('system', 'unknown')}"},
                    {"type": "mrkdwn", "text": f"*Source IP:*\n{incident.get('source_ip', 'N/A')}"},
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Details:*\n```{incident.get('line', incident.get('title', 'No details'))}```"
                }
            },
        ]

        # Add threat intel if available
        if enrichment and enrichment.get("enriched"):
            rep = enrichment.get("reputation", {})
            threat_text = f"*Threat Score:* {rep.get('score', 'N/A')}/100"
            if rep.get("is_malicious"):
                threat_text += " :skull:"
            if rep.get("country"):
                threat_text += f" | *Country:* {rep.get('country')}"

            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": threat_text}]
            })

        # Add ML confidence if available
        if triage.get("ml_confidence"):
            blocks.append({
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": f":robot_face: ML Confidence: {triage['ml_confidence']:.0%}"
                }]
            })

        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": f"Incident ID: `{incident.get('id', 'unknown')}` | Detected: {incident.get('detected_at', 'N/A')}"
            }]
        })

        return {"blocks": blocks}

    @staticmethod
    def format_discord(incident: Dict, triage: Dict, enrichment: Optional[Dict] = None) -> Dict:
        """Format alert as Discord embed."""
        severity = triage.get("severity", incident.get("severity", "unknown"))
        color = {
            "critical": 0xFF0000,  # Red
            "high": 0xFF6600,      # Orange
            "medium": 0xFFCC00,    # Yellow
            "low": 0x00CCFF,       # Cyan
        }.get(severity, 0x808080)

        fields = [
            {"name": "Severity", "value": severity.upper(), "inline": True},
            {"name": "Priority", "value": triage.get("priority", "N/A"), "inline": True},
            {"name": "System", "value": incident.get("system", "unknown"), "inline": True},
            {"name": "Source IP", "value": incident.get("source_ip", "N/A"), "inline": True},
        ]

        if enrichment and enrichment.get("enriched"):
            rep = enrichment.get("reputation", {})
            threat_value = f"{rep.get('score', 'N/A')}/100"
            if rep.get("is_malicious"):
                threat_value += " ⚠️ MALICIOUS"
            fields.append({"name": "Threat Score", "value": threat_value, "inline": True})

        if triage.get("ml_confidence"):
            fields.append({
                "name": "ML Confidence",
                "value": f"{triage['ml_confidence']:.0%}",
                "inline": True
            })

        embed = {
            "title": f"🚨 {incident.get('type', 'Security Alert')}",
            "description": incident.get("line", incident.get("title", "No details")),
            "color": color,
            "fields": fields,
            "footer": {"text": f"Incident: {incident.get('id', 'unknown')}"},
            "timestamp": incident.get("detected_at", "").replace(" ", "T") + "Z" if incident.get("detected_at") else None,
        }

        return {"embeds": [embed]}

    @staticmethod
    def format_pagerduty(
        incident: Dict,
        triage: Dict,
        routing_key: str,
        enrichment: Optional[Dict] = None
    ) -> Dict:
        """Format alert for PagerDuty Events API v2."""
        severity = triage.get("severity", incident.get("severity", "unknown"))
        pd_severity = {
            "critical": "critical",
            "high": "error",
            "medium": "warning",
            "low": "info",
        }.get(severity, "warning")

        custom_details = {
            "incident_id": incident.get("id"),
            "system": incident.get("system"),
            "source_ip": incident.get("source_ip"),
            "priority": triage.get("priority"),
            "velocity": triage.get("velocity"),
            "log_line": incident.get("line"),
        }

        if enrichment and enrichment.get("enriched"):
            rep = enrichment.get("reputation", {})
            custom_details["threat_score"] = rep.get("score")
            custom_details["is_malicious"] = rep.get("is_malicious")

        if triage.get("ml_confidence"):
            custom_details["ml_confidence"] = triage["ml_confidence"]

        return {
            "routing_key": routing_key,
            "event_action": "trigger",
            "dedup_key": incident.get("id", f"alert_{time.time()}"),
            "payload": {
                "summary": f"{incident.get('type', 'Security Alert')} on {incident.get('system', 'unknown')}",
                "severity": pd_severity,
                "source": "clove-soc",
                "component": incident.get("system"),
                "custom_details": custom_details,
            },
        }

    @staticmethod
    def format_generic(incident: Dict, triage: Dict, enrichment: Optional[Dict] = None) -> Dict:
        """Format alert as generic JSON payload."""
        payload = {
            "alert_type": "security_incident",
            "incident": incident,
            "triage": triage,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if enrichment:
            payload["enrichment"] = enrichment
        return payload


class RateLimiter:
    """Simple rate limiter for webhook calls."""

    def __init__(self, max_per_minute: int = 10):
        self.max_per_minute = max_per_minute
        self.calls: Dict[str, List[float]] = defaultdict(list)

    def can_send(self, destination: str) -> bool:
        """Check if we can send to this destination."""
        now = time.time()
        cutoff = now - 60

        # Clean old entries
        self.calls[destination] = [t for t in self.calls[destination] if t > cutoff]

        return len(self.calls[destination]) < self.max_per_minute

    def record(self, destination: str) -> None:
        """Record a call to a destination."""
        self.calls[destination].append(time.time())


class AlertEscalator:
    """Main alert escalation agent."""

    def __init__(self, client: CloveClient, config: Dict[str, Any]):
        self.client = client
        self.config = config
        self.webhooks: List[WebhookConfig] = []

        rate_limit_config = config.get("rate_limit", {})
        self.rate_limiter = RateLimiter(rate_limit_config.get("max_per_minute", 10))

        # Parse webhook configurations
        for wh in config.get("webhooks", []):
            url = wh.get("url", "")
            # Support environment variables
            if url.startswith("${") and url.endswith("}"):
                env_var = url[2:-1]
                url = os.environ.get(env_var, "")

            routing_key = wh.get("routing_key", "")
            if routing_key.startswith("${") and routing_key.endswith("}"):
                env_var = routing_key[2:-1]
                routing_key = os.environ.get(env_var, "")

            if url:
                self.webhooks.append(WebhookConfig(
                    name=wh.get("name", "unnamed"),
                    type=wh.get("type", "generic"),
                    url=url,
                    severity_filter=wh.get("severity_filter", ["critical", "high"]),
                    routing_key=routing_key or None,
                    enabled=wh.get("enabled", True),
                ))

        self.alerts_sent = 0
        self.alerts_failed = 0
        self.alerts_rate_limited = 0

    def should_escalate(self, webhook: WebhookConfig, severity: str) -> bool:
        """Check if alert should be sent to this webhook."""
        if not webhook.enabled:
            return False
        return severity.lower() in [s.lower() for s in webhook.severity_filter]

    def send_alert(
        self,
        incident: Dict,
        triage: Dict,
        enrichment: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Send alert to all applicable webhooks.

        Returns:
            Summary of send results
        """
        severity = triage.get("severity", incident.get("severity", "unknown"))
        results = []

        for webhook in self.webhooks:
            if not self.should_escalate(webhook, severity):
                continue

            # Check rate limit
            if not self.rate_limiter.can_send(webhook.name):
                self.alerts_rate_limited += 1
                results.append({
                    "webhook": webhook.name,
                    "status": "rate_limited",
                })
                continue

            # Format payload
            if webhook.type == "slack":
                payload = WebhookFormatter.format_slack(incident, triage, enrichment)
            elif webhook.type == "discord":
                payload = WebhookFormatter.format_discord(incident, triage, enrichment)
            elif webhook.type == "pagerduty":
                if not webhook.routing_key:
                    results.append({
                        "webhook": webhook.name,
                        "status": "error",
                        "error": "missing routing_key",
                    })
                    continue
                payload = WebhookFormatter.format_pagerduty(
                    incident, triage, webhook.routing_key, enrichment
                )
            else:
                payload = WebhookFormatter.format_generic(incident, triage, enrichment)

            # Send webhook
            try:
                result = self.client.http(
                    url=webhook.url,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                    body=json.dumps(payload),
                )

                self.rate_limiter.record(webhook.name)

                if result.get("success"):
                    self.alerts_sent += 1
                    results.append({
                        "webhook": webhook.name,
                        "status": "sent",
                        "status_code": result.get("status_code"),
                    })
                else:
                    self.alerts_failed += 1
                    results.append({
                        "webhook": webhook.name,
                        "status": "failed",
                        "error": result.get("error"),
                    })

            except Exception as e:
                self.alerts_failed += 1
                results.append({
                    "webhook": webhook.name,
                    "status": "error",
                    "error": str(e),
                })

        return {
            "incident_id": incident.get("id"),
            "severity": severity,
            "webhooks_attempted": len(results),
            "results": results,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get escalation statistics."""
        return {
            "alerts_sent": self.alerts_sent,
            "alerts_failed": self.alerts_failed,
            "alerts_rate_limited": self.alerts_rate_limited,
            "webhooks_configured": len(self.webhooks),
            "webhook_names": [w.name for w in self.webhooks],
        }


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
        mode = init.get("mode", "continuous")
        config = init.get("config", {})

        escalation_config = config.get("alert_escalation", {})
        enabled = escalation_config.get("enabled", True)

        service_config = config.get("service", {})
        heartbeat_interval = service_config.get("heartbeat_interval_seconds", 5)

        escalator = AlertEscalator(client, escalation_config)

        log(AGENT_NAME, "INFO", f"Initialized with {len(escalator.webhooks)} webhooks")

        # Send init acknowledgment
        client.send_message({"type": "init_ack", "agent": AGENT_NAME}, to_name="orchestrator")

        last_heartbeat = time.time()

        while True:
            current_time = time.time()

            # Send heartbeat
            if mode == "continuous" and current_time - last_heartbeat >= heartbeat_interval:
                stats = escalator.get_stats()
                client.send_message({
                    "type": "heartbeat",
                    "agent": AGENT_NAME,
                    **stats,
                }, to_name="orchestrator")
                last_heartbeat = current_time

            # Check for messages
            try:
                message = wait_for_message(client, timeout_s=0.5)
                msg_type = message.get("type")

                if msg_type == "escalate_alert":
                    incident = message.get("incident", {})
                    triage = message.get("triage", {})
                    enrichment = message.get("enrichment")
                    reply_to = message.get("reply_to", "auditor")

                    if enabled:
                        result = escalator.send_alert(incident, triage, enrichment)
                    else:
                        result = {
                            "incident_id": incident.get("id"),
                            "status": "disabled",
                            "webhooks_attempted": 0,
                            "results": [],
                        }

                    client.send_message({
                        "type": "escalation_result",
                        **result,
                    }, to_name=reply_to)

                    # Also notify orchestrator
                    client.send_message({
                        "type": "escalation_event",
                        "incident_id": incident.get("id"),
                        "severity": triage.get("severity"),
                        "webhooks_sent": sum(1 for r in result.get("results", []) if r.get("status") == "sent"),
                    }, to_name="orchestrator")

                elif msg_type == "test_webhook":
                    # Test webhook connectivity
                    webhook_name = message.get("webhook_name")
                    reply_to = message.get("reply_to", "orchestrator")

                    test_incident = {
                        "id": "test_001",
                        "type": "TEST_ALERT",
                        "severity": "high",
                        "system": "test",
                        "source_ip": "192.168.1.1",
                        "line": "This is a test alert from CLOVE SOC",
                        "detected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    test_triage = {"severity": "high", "priority": "P2"}

                    result = escalator.send_alert(test_incident, test_triage)
                    client.send_message({
                        "type": "test_webhook_result",
                        **result,
                    }, to_name=reply_to)

                elif msg_type == "get_stats":
                    reply_to = message.get("reply_to", "orchestrator")
                    client.send_message({
                        "type": "escalation_stats",
                        **escalator.get_stats(),
                    }, to_name=reply_to)

                elif msg_type == "shutdown":
                    log(AGENT_NAME, "INFO", "Received shutdown")
                    break

            except TimeoutError:
                pass

            time.sleep(0.05)

    except TimeoutError as e:
        log(AGENT_NAME, "ERROR", f"Fatal timeout: {e}")
        return 1
    finally:
        client.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
