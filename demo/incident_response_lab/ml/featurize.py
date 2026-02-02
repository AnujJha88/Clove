"""Feature extraction for incident severity scoring.

Extracts numeric features from incident data for ML-based severity classification.
Follows patterns from the drug discovery pipeline for consistent feature engineering.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Feature names for model metadata
TIME_FEATURE_NAMES = ["hour_of_day", "day_of_week", "is_weekend"]
NETWORK_FEATURE_NAMES = [
    "ip_octet_1", "ip_octet_2", "ip_octet_3", "ip_octet_4",
    "port_category", "is_private_ip"
]
BEHAVIORAL_FEATURE_NAMES = ["velocity", "repeat_offender", "anomaly_count"]
INCIDENT_TYPE_FEATURE_NAMES = [
    "is_injection", "is_auth", "is_exfil", "is_scan", "is_dos"
]

ALL_FEATURE_NAMES = (
    TIME_FEATURE_NAMES +
    NETWORK_FEATURE_NAMES +
    BEHAVIORAL_FEATURE_NAMES +
    INCIDENT_TYPE_FEATURE_NAMES
)


def extract_time_features(incident: Dict[str, Any]) -> Optional[List[float]]:
    """Extract time-based features from incident timestamp.

    Returns:
        [hour_of_day (0-23), day_of_week (0-6), is_weekend (0/1)]
    """
    detected_at = incident.get("detected_at")
    if not detected_at:
        return None

    try:
        # Parse various timestamp formats
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
            try:
                dt = datetime.strptime(detected_at, fmt)
                break
            except ValueError:
                continue
        else:
            return None

        hour = float(dt.hour)
        day_of_week = float(dt.weekday())
        is_weekend = 1.0 if dt.weekday() >= 5 else 0.0

        return [hour / 23.0, day_of_week / 6.0, is_weekend]

    except (ValueError, TypeError):
        return None


def parse_ip_address(ip: Optional[str]) -> Optional[Tuple[int, int, int, int]]:
    """Parse IPv4 address into octets."""
    if not ip:
        return None

    pattern = r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$"
    match = re.match(pattern, ip)
    if not match:
        return None

    octets = tuple(int(g) for g in match.groups())
    if all(0 <= o <= 255 for o in octets):
        return octets  # type: ignore
    return None


def is_private_ip(octets: Tuple[int, int, int, int]) -> bool:
    """Check if IP octets represent a private/internal address."""
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


def categorize_port(port: Optional[int]) -> float:
    """Categorize port number into risk levels.

    Returns:
        0.0: No port / unknown
        0.2: Well-known privileged (0-1023)
        0.4: Registered (1024-49151)
        0.6: Dynamic/private (49152-65535)
        0.8: Common attack targets (SSH, RDP, etc.)
        1.0: Database ports
    """
    if port is None:
        return 0.0

    # Database ports - high risk
    if port in {3306, 5432, 27017, 6379, 1433, 1521}:
        return 1.0

    # Common attack targets
    if port in {22, 23, 3389, 445, 135, 139, 21, 25, 110, 143}:
        return 0.8

    # Dynamic/private range
    if 49152 <= port <= 65535:
        return 0.6

    # Registered ports
    if 1024 <= port <= 49151:
        return 0.4

    # Privileged ports
    if 0 <= port <= 1023:
        return 0.2

    return 0.0


def extract_network_features(incident: Dict[str, Any]) -> Optional[List[float]]:
    """Extract network-based features from incident.

    Returns:
        [ip_octet_1, ip_octet_2, ip_octet_3, ip_octet_4, port_category, is_private_ip]
        All normalized to 0-1 range.
    """
    source_ip = incident.get("source_ip")
    octets = parse_ip_address(source_ip)

    if octets:
        normalized_octets = [o / 255.0 for o in octets]
        private = 1.0 if is_private_ip(octets) else 0.0
    else:
        normalized_octets = [0.0, 0.0, 0.0, 0.0]
        private = 0.0

    # Extract port if available
    port = incident.get("port") or incident.get("dest_port")
    if isinstance(port, str):
        try:
            port = int(port)
        except ValueError:
            port = None
    port_cat = categorize_port(port)

    return normalized_octets + [port_cat, private]


def extract_behavioral_features(
    incident: Dict[str, Any],
    context: Dict[str, Any]
) -> Optional[List[float]]:
    """Extract behavioral features from incident and context.

    Context may include:
    - velocity: incidents per minute for this system
    - repeat_offender: whether this IP/user has been seen before
    - anomaly_count: total anomalies from this source

    Returns:
        [velocity_normalized, repeat_offender, anomaly_count_normalized]
    """
    # Velocity (incidents per minute), normalized with log scale
    velocity = context.get("velocity", 0)
    # Log scale normalization, cap at ~100 events/min
    velocity_norm = min(1.0, velocity / 100.0) if velocity > 0 else 0.0

    # Repeat offender flag
    repeat = 1.0 if context.get("repeat_offender", False) else 0.0

    # Anomaly count from same source
    anomaly_count = context.get("anomaly_count", 0)
    anomaly_norm = min(1.0, anomaly_count / 50.0) if anomaly_count > 0 else 0.0

    return [velocity_norm, repeat, anomaly_norm]


def extract_incident_type_features(incident: Dict[str, Any]) -> List[float]:
    """Extract incident type category features.

    Returns one-hot-ish encoding for attack categories:
        [is_injection, is_auth, is_exfil, is_scan, is_dos]
    """
    incident_type = (incident.get("type") or "").upper()

    # Injection attacks
    is_injection = 1.0 if any(
        kw in incident_type
        for kw in ["SQL", "INJECT", "XSS", "TRAVERSAL", "RCE", "COMMAND"]
    ) else 0.0

    # Authentication attacks
    is_auth = 1.0 if any(
        kw in incident_type
        for kw in ["BRUTE", "LOGIN", "AUTH", "PASSWORD", "PRIV", "ACCESS"]
    ) else 0.0

    # Data exfiltration
    is_exfil = 1.0 if any(
        kw in incident_type
        for kw in ["EXFIL", "LEAK", "C2", "BEACON", "DOWNLOAD"]
    ) else 0.0

    # Scanning/reconnaissance
    is_scan = 1.0 if any(
        kw in incident_type
        for kw in ["SCAN", "PROBE", "ENUM", "RECON"]
    ) else 0.0

    # Denial of service
    is_dos = 1.0 if any(
        kw in incident_type
        for kw in ["DDOS", "DOS", "FLOOD", "RATE", "EXHAUST"]
    ) else 0.0

    return [is_injection, is_auth, is_exfil, is_scan, is_dos]


def featurize_incident(
    incident: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Combine all feature extractors into a single feature vector.

    Args:
        incident: Incident dictionary with type, source_ip, detected_at, etc.
        context: Optional behavioral context (velocity, repeat_offender, etc.)

    Returns:
        {
            "features": List[float],  # Complete feature vector
            "valid": bool,            # Whether all extractors succeeded
            "n_features": int,        # Number of features
            "feature_names": List[str]
        }
    """
    if context is None:
        context = {}

    features: List[float] = []
    all_valid = True

    # Time features (3)
    time_feats = extract_time_features(incident)
    if time_feats is None:
        time_feats = [0.0] * len(TIME_FEATURE_NAMES)
        all_valid = False
    features.extend(time_feats)

    # Network features (6)
    net_feats = extract_network_features(incident)
    if net_feats is None:
        net_feats = [0.0] * len(NETWORK_FEATURE_NAMES)
        all_valid = False
    features.extend(net_feats)

    # Behavioral features (3)
    behav_feats = extract_behavioral_features(incident, context)
    if behav_feats is None:
        behav_feats = [0.0] * len(BEHAVIORAL_FEATURE_NAMES)
        all_valid = False
    features.extend(behav_feats)

    # Incident type features (5)
    type_feats = extract_incident_type_features(incident)
    features.extend(type_feats)

    return {
        "features": features,
        "valid": all_valid,
        "n_features": len(features),
        "feature_names": ALL_FEATURE_NAMES,
    }


def batch_featurize(
    incidents: List[Dict[str, Any]],
    contexts: Optional[List[Dict[str, Any]]] = None
) -> Tuple[List[List[float]], List[bool]]:
    """Featurize a batch of incidents.

    Args:
        incidents: List of incident dictionaries
        contexts: Optional list of context dictionaries (one per incident)

    Returns:
        (feature_matrix, valid_flags)
    """
    if contexts is None:
        contexts = [{}] * len(incidents)

    feature_matrix = []
    valid_flags = []

    for incident, ctx in zip(incidents, contexts):
        result = featurize_incident(incident, ctx)
        feature_matrix.append(result["features"])
        valid_flags.append(result["valid"])

    return feature_matrix, valid_flags
