"""Runtime severity scoring for incidents.

Loads a trained model and provides real-time severity predictions.
Used by the anomaly_triager agent when ML scoring is enabled.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional

from .featurize import featurize_incident

# Severity labels in order of increasing severity
SEVERITY_LABELS = ["low", "medium", "high", "critical"]


class SeverityScorer:
    """Runtime severity scorer using trained ML model."""

    def __init__(self, model_path: Path, metadata_path: Optional[Path] = None):
        """Load trained model and metadata.

        Args:
            model_path: Path to pickled model file
            metadata_path: Optional path to JSON metadata (auto-detected if not provided)
        """
        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        with open(model_path, "rb") as f:
            self.model = pickle.load(f)

        # Load metadata
        if metadata_path is None:
            metadata_path = model_path.with_suffix(".json")

        self.metadata: Dict[str, Any] = {}
        if metadata_path.exists():
            with open(metadata_path) as f:
                self.metadata = json.load(f)

        self.severity_labels = self.metadata.get("severity_labels", SEVERITY_LABELS)
        self.feature_names = self.metadata.get("feature_names", [])

    def score(
        self,
        incident: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Score an incident and predict severity.

        Args:
            incident: Incident dictionary with type, source_ip, etc.
            context: Optional behavioral context (velocity, etc.)

        Returns:
            {
                "severity": str,        # Predicted severity label
                "confidence": float,    # Confidence score (0-1)
                "probabilities": Dict,  # Per-class probabilities
                "ml_scored": True,      # Flag indicating ML was used
                "features_valid": bool  # Whether all features extracted
            }
        """
        if context is None:
            context = {}

        # Extract features
        feat_result = featurize_incident(incident, context)
        features = feat_result["features"]

        # Get prediction
        try:
            proba = self.model.predict_proba([features])[0]
            severity_idx = proba.argmax()
            severity = self.severity_labels[severity_idx]
            confidence = float(proba[severity_idx])

            probabilities = {
                label: float(p)
                for label, p in zip(self.severity_labels, proba)
            }

            return {
                "severity": severity,
                "confidence": confidence,
                "probabilities": probabilities,
                "ml_scored": True,
                "features_valid": feat_result["valid"],
            }

        except Exception as e:
            # Fallback on error
            return {
                "severity": incident.get("severity", "medium"),
                "confidence": 0.0,
                "probabilities": {},
                "ml_scored": False,
                "error": str(e),
                "features_valid": feat_result["valid"],
            }

    def batch_score(
        self,
        incidents: List[Dict[str, Any]],
        contexts: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """Score multiple incidents at once.

        Args:
            incidents: List of incident dictionaries
            contexts: Optional list of context dictionaries

        Returns:
            List of score results
        """
        if contexts is None:
            contexts = [{}] * len(incidents)

        return [
            self.score(inc, ctx)
            for inc, ctx in zip(incidents, contexts)
        ]

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about the loaded model."""
        return {
            "model_type": self.metadata.get("model_type", "unknown"),
            "n_features": self.metadata.get("n_features", len(self.feature_names)),
            "severity_labels": self.severity_labels,
            "training_accuracy": self.metadata.get("test_accuracy"),
            "feature_names": self.feature_names,
        }


class RuleBasedScorer:
    """Fallback rule-based scorer when ML model unavailable."""

    def __init__(self, rules: Optional[Dict[str, Dict[str, Any]]] = None):
        """Initialize with optional severity rules.

        Args:
            rules: Mapping of incident type to {severity: str, ...}
        """
        self.rules = rules or {}

    def score(
        self,
        incident: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Score using rule-based logic."""
        incident_type = incident.get("type", "")
        rule = self.rules.get(incident_type, {})

        severity = rule.get("severity") or incident.get("severity", "medium")

        return {
            "severity": severity,
            "confidence": 1.0,  # Rules are deterministic
            "probabilities": {severity: 1.0},
            "ml_scored": False,
            "rule_based": True,
        }


def create_scorer(
    model_path: Optional[Path] = None,
    rules: Optional[Dict[str, Dict[str, Any]]] = None,
    fallback_to_rules: bool = True
) -> SeverityScorer | RuleBasedScorer:
    """Factory function to create appropriate scorer.

    Args:
        model_path: Path to ML model (optional)
        rules: Rule definitions for fallback
        fallback_to_rules: Whether to use rules if ML unavailable

    Returns:
        SeverityScorer if model available, else RuleBasedScorer
    """
    if model_path and Path(model_path).exists():
        try:
            return SeverityScorer(Path(model_path))
        except Exception:
            if fallback_to_rules:
                return RuleBasedScorer(rules)
            raise

    if fallback_to_rules:
        return RuleBasedScorer(rules)

    raise FileNotFoundError(f"Model not found and fallback disabled: {model_path}")
