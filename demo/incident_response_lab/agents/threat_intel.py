"""Agent: threat_intel - IP reputation lookup via external APIs.

Enriches incidents with threat intelligence data from:
- AbuseIPDB: Abuse confidence scores
- VirusTotal: Malicious detection counts

Uses Clove SDK http() for API calls and distributed state for caching.
"""
from __future__ import annotations

import json
import os
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils import ensure_sdk_on_path, wait_for_message, log, is_valid_ip, is_internal_ip

ensure_sdk_on_path()
from clove_sdk import CloveClient  # noqa: E402

AGENT_NAME = "threat_intel"


@dataclass
class IPReputation:
    """IP reputation result from threat intel providers."""
    ip: str
    score: int  # 0-100, higher = more malicious
    is_malicious: bool
    provider: str
    abuse_confidence: Optional[int] = None
    total_reports: Optional[int] = None
    last_reported: Optional[str] = None
    country: Optional[str] = None
    isp: Optional[str] = None
    categories: Optional[list] = None
    raw_response: Optional[Dict] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ip": self.ip,
            "score": self.score,
            "is_malicious": self.is_malicious,
            "provider": self.provider,
            "abuse_confidence": self.abuse_confidence,
            "total_reports": self.total_reports,
            "last_reported": self.last_reported,
            "country": self.country,
            "isp": self.isp,
            "categories": self.categories,
        }


class ThreatIntelProvider(ABC):
    """Abstract base class for threat intel providers."""

    @abstractmethod
    def lookup_ip(self, ip: str, client: CloveClient) -> Optional[IPReputation]:
        """Look up IP reputation."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass


class AbuseIPDBProvider(ThreatIntelProvider):
    """AbuseIPDB threat intelligence provider."""

    def __init__(self, api_key: str, max_age_days: int = 90):
        self.api_key = api_key
        self.max_age_days = max_age_days

    @property
    def name(self) -> str:
        return "abuseipdb"

    def lookup_ip(self, ip: str, client: CloveClient) -> Optional[IPReputation]:
        """Query AbuseIPDB for IP reputation."""
        if not self.api_key:
            return None

        try:
            result = client.http(
                url=f"https://api.abuseipdb.com/api/v2/check",
                method="GET",
                headers={
                    "Key": self.api_key,
                    "Accept": "application/json",
                },
                params={
                    "ipAddress": ip,
                    "maxAgeInDays": str(self.max_age_days),
                },
            )

            if not result.get("success"):
                log(AGENT_NAME, "WARN", f"AbuseIPDB request failed: {result.get('error')}")
                return None

            body = result.get("body", "{}")
            data = json.loads(body) if isinstance(body, str) else body
            ip_data = data.get("data", {})

            abuse_score = ip_data.get("abuseConfidenceScore", 0)

            return IPReputation(
                ip=ip,
                score=abuse_score,
                is_malicious=abuse_score >= 50,
                provider=self.name,
                abuse_confidence=abuse_score,
                total_reports=ip_data.get("totalReports", 0),
                last_reported=ip_data.get("lastReportedAt"),
                country=ip_data.get("countryCode"),
                isp=ip_data.get("isp"),
                raw_response=ip_data,
            )

        except Exception as e:
            log(AGENT_NAME, "ERROR", f"AbuseIPDB lookup failed: {e}")
            return None


class VirusTotalProvider(ThreatIntelProvider):
    """VirusTotal threat intelligence provider."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    @property
    def name(self) -> str:
        return "virustotal"

    def lookup_ip(self, ip: str, client: CloveClient) -> Optional[IPReputation]:
        """Query VirusTotal for IP reputation."""
        if not self.api_key:
            return None

        try:
            result = client.http(
                url=f"https://www.virustotal.com/api/v3/ip_addresses/{ip}",
                method="GET",
                headers={
                    "x-apikey": self.api_key,
                    "Accept": "application/json",
                },
            )

            if not result.get("success"):
                log(AGENT_NAME, "WARN", f"VirusTotal request failed: {result.get('error')}")
                return None

            body = result.get("body", "{}")
            data = json.loads(body) if isinstance(body, str) else body
            attrs = data.get("data", {}).get("attributes", {})

            # Calculate score from last_analysis_stats
            stats = attrs.get("last_analysis_stats", {})
            malicious = stats.get("malicious", 0)
            suspicious = stats.get("suspicious", 0)
            total = sum(stats.values()) if stats else 1

            score = int(((malicious * 2 + suspicious) / max(total * 2, 1)) * 100)

            return IPReputation(
                ip=ip,
                score=score,
                is_malicious=malicious > 0,
                provider=self.name,
                total_reports=malicious + suspicious,
                country=attrs.get("country"),
                categories=list(attrs.get("categories", {}).values()) if attrs.get("categories") else None,
                raw_response=attrs,
            )

        except Exception as e:
            log(AGENT_NAME, "ERROR", f"VirusTotal lookup failed: {e}")
            return None


class MockProvider(ThreatIntelProvider):
    """Mock provider for testing without API keys."""

    # Known malicious IP patterns for demo
    MALICIOUS_PATTERNS = [
        "185.220.101",  # Tor exits
        "45.155.205",   # Suspicious hosting
        "194.26.192",   # VPN/proxy
        "89.248.167",   # Scanner networks
        "141.98.10",    # Bulletproof hosting
    ]

    @property
    def name(self) -> str:
        return "mock"

    def lookup_ip(self, ip: str, client: CloveClient) -> Optional[IPReputation]:
        """Generate mock reputation data."""
        # Check against known patterns
        is_suspicious = any(ip.startswith(p) for p in self.MALICIOUS_PATTERNS)

        if is_suspicious:
            score = 75 + (hash(ip) % 25)  # 75-100
        elif is_internal_ip(ip):
            score = 0
        else:
            score = hash(ip) % 30  # 0-30 for random IPs

        return IPReputation(
            ip=ip,
            score=score,
            is_malicious=score >= 50,
            provider=self.name,
            abuse_confidence=score,
            total_reports=score // 10 if score > 0 else 0,
            country="XX",
        )


class ThreatIntelAgent:
    """Main threat intelligence agent."""

    def __init__(self, client: CloveClient, config: Dict[str, Any]):
        self.client = client
        self.config = config
        self.cache_ttl = config.get("cache_ttl_seconds", 3600)
        self.providers: list[ThreatIntelProvider] = []

        # Initialize providers
        providers_config = config.get("providers", {})

        # AbuseIPDB
        abuseipdb_config = providers_config.get("abuseipdb", {})
        if abuseipdb_config.get("enabled", False):
            api_key = abuseipdb_config.get("api_key", "")
            # Support environment variable
            if api_key.startswith("${") and api_key.endswith("}"):
                env_var = api_key[2:-1]
                api_key = os.environ.get(env_var, "")
            if api_key:
                self.providers.append(AbuseIPDBProvider(api_key))

        # VirusTotal
        vt_config = providers_config.get("virustotal", {})
        if vt_config.get("enabled", False):
            api_key = vt_config.get("api_key", "")
            if api_key.startswith("${") and api_key.endswith("}"):
                env_var = api_key[2:-1]
                api_key = os.environ.get(env_var, "")
            if api_key:
                self.providers.append(VirusTotalProvider(api_key))

        # Mock provider for testing
        if providers_config.get("mock", {}).get("enabled", False) or not self.providers:
            self.providers.append(MockProvider())

        self.lookups_total = 0
        self.cache_hits = 0
        self.malicious_found = 0

    def get_cached(self, ip: str) -> Optional[Dict[str, Any]]:
        """Check distributed cache for IP reputation."""
        result = self.client.fetch(f"threat_intel:{ip}")
        if result.get("success") and result.get("value"):
            self.cache_hits += 1
            return result["value"]
        return None

    def cache_result(self, ip: str, reputation: Dict[str, Any]) -> None:
        """Store IP reputation in distributed cache."""
        self.client.store(
            f"threat_intel:{ip}",
            reputation,
            scope="global",
            ttl=self.cache_ttl
        )

    def enrich_incident(self, incident: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich an incident with threat intelligence.

        Args:
            incident: Incident dictionary with source_ip

        Returns:
            Enrichment result with reputation data
        """
        ip = incident.get("source_ip")

        if not ip or not is_valid_ip(ip):
            return {
                "enriched": False,
                "reason": "no_valid_ip",
            }

        # Skip internal IPs
        if is_internal_ip(ip):
            return {
                "enriched": True,
                "ip": ip,
                "reputation": {
                    "score": 0,
                    "is_malicious": False,
                    "is_internal": True,
                },
            }

        self.lookups_total += 1

        # Check cache first
        cached = self.get_cached(ip)
        if cached:
            return {
                "enriched": True,
                "ip": ip,
                "reputation": cached,
                "cached": True,
            }

        # Query providers
        for provider in self.providers:
            reputation = provider.lookup_ip(ip, self.client)
            if reputation:
                rep_dict = reputation.to_dict()
                self.cache_result(ip, rep_dict)

                if reputation.is_malicious:
                    self.malicious_found += 1

                return {
                    "enriched": True,
                    "ip": ip,
                    "reputation": rep_dict,
                    "cached": False,
                }

        return {
            "enriched": False,
            "ip": ip,
            "reason": "lookup_failed",
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics."""
        return {
            "lookups_total": self.lookups_total,
            "cache_hits": self.cache_hits,
            "cache_hit_rate": self.cache_hits / max(self.lookups_total, 1),
            "malicious_found": self.malicious_found,
            "providers": [p.name for p in self.providers],
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

        threat_intel_config = config.get("threat_intel", {})
        enabled = threat_intel_config.get("enabled", True)

        service_config = config.get("service", {})
        heartbeat_interval = service_config.get("heartbeat_interval_seconds", 5)

        agent = ThreatIntelAgent(client, threat_intel_config)

        log(AGENT_NAME, "INFO", f"Initialized with providers: {[p.name for p in agent.providers]}")

        # Send init acknowledgment
        client.send_message({"type": "init_ack", "agent": AGENT_NAME}, to_name="orchestrator")

        last_heartbeat = time.time()

        while True:
            current_time = time.time()

            # Send heartbeat
            if mode == "continuous" and current_time - last_heartbeat >= heartbeat_interval:
                stats = agent.get_stats()
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

                if msg_type == "enrich_incident":
                    incident = message.get("incident", {})
                    reply_to = message.get("reply_to", "anomaly_triager")
                    request_id = message.get("request_id")

                    if enabled:
                        result = agent.enrich_incident(incident)
                    else:
                        result = {"enriched": False, "reason": "disabled"}

                    client.send_message({
                        "type": "enrichment_result",
                        "request_id": request_id,
                        "incident_id": incident.get("id"),
                        **result,
                    }, to_name=reply_to)

                elif msg_type == "lookup_ip":
                    # Direct IP lookup
                    ip = message.get("ip")
                    reply_to = message.get("reply_to", "orchestrator")

                    if enabled and ip:
                        result = agent.enrich_incident({"source_ip": ip})
                    else:
                        result = {"enriched": False, "reason": "disabled_or_no_ip"}

                    client.send_message({
                        "type": "ip_lookup_result",
                        "ip": ip,
                        **result,
                    }, to_name=reply_to)

                elif msg_type == "get_stats":
                    reply_to = message.get("reply_to", "orchestrator")
                    client.send_message({
                        "type": "threat_intel_stats",
                        **agent.get_stats(),
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
