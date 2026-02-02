#!/usr/bin/env python3
"""Train severity classification model for incident triage.

Offline training script that follows patterns from the drug discovery pipeline.
Trains a model to predict incident severity based on extracted features.

Usage:
    python train_severity_model.py --data data/sample_incidents.json --output models/
    python train_severity_model.py --generate-sample --output models/
"""
from __future__ import annotations

import argparse
import json
import pickle
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))
from featurize import (
    ALL_FEATURE_NAMES,
    batch_featurize,
    featurize_incident,
)

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.metrics import classification_report, confusion_matrix
    import numpy as np
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    np = None  # type: ignore

# Severity labels in order of increasing severity
SEVERITY_LABELS = ["low", "medium", "high", "critical"]
SEVERITY_TO_IDX = {label: idx for idx, label in enumerate(SEVERITY_LABELS)}


def generate_sample_incidents(n_samples: int = 500) -> List[Dict[str, Any]]:
    """Generate synthetic training data for model development.

    Creates a balanced dataset with realistic incident patterns.
    """
    random.seed(42)
    incidents = []

    attack_types = {
        "critical": [
            ("SQL_INJECTION", "SQL Injection attempt"),
            ("C2_BEACON", "C2 beacon detected"),
            ("DATA_EXFIL", "Data exfiltration"),
            ("PRIV_ESC", "Privilege escalation"),
            ("BRUTE_FORCE", "Brute force attack"),
        ],
        "high": [
            ("PORT_SCAN", "Port scan detected"),
            ("XSS_ATTEMPT", "XSS attempt"),
            ("PATH_TRAVERSAL", "Path traversal"),
            ("UNAUTH_ACCESS", "Unauthorized access"),
        ],
        "medium": [
            ("FAILED_LOGIN", "Failed login"),
            ("RATE_LIMIT", "Rate limit exceeded"),
            ("HTTP_ERROR", "HTTP 5xx error"),
            ("SLOW_QUERY", "Slow database query"),
        ],
        "low": [
            ("CONN_TIMEOUT", "Connection timeout"),
            ("WARNING", "Generic warning"),
            ("INFO", "Informational"),
        ],
    }

    samples_per_class = n_samples // len(SEVERITY_LABELS)

    for severity in SEVERITY_LABELS:
        types = attack_types[severity]
        for _ in range(samples_per_class):
            attack_type, title = random.choice(types)

            # Generate realistic features
            hour = random.randint(0, 23)
            # More attacks during off-hours for high/critical
            if severity in ("high", "critical"):
                hour = random.choice([2, 3, 4, 5, 22, 23] + [random.randint(0, 23)])
            day = random.randint(0, 6)

            # Generate IP - external IPs more likely for attacks
            if severity in ("high", "critical") and random.random() > 0.3:
                # External IP
                ip = f"{random.randint(1, 223)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"
            else:
                # Internal IP
                ip = f"192.168.{random.randint(1, 254)}.{random.randint(1, 254)}"

            # Velocity - higher for attacks
            velocity = 0
            if severity == "critical":
                velocity = random.randint(20, 100)
            elif severity == "high":
                velocity = random.randint(10, 50)
            elif severity == "medium":
                velocity = random.randint(1, 20)

            incident = {
                "id": f"sample_{len(incidents):04d}",
                "type": attack_type,
                "title": title,
                "severity": severity,
                "source_ip": ip,
                "detected_at": f"2024-01-{random.randint(1, 28):02d} {hour:02d}:{random.randint(0, 59):02d}:00",
                "port": random.choice([22, 80, 443, 3306, 8080, None]),
                "system": random.choice(["web", "auth", "database", "network"]),
            }
            incidents.append((incident, {"velocity": velocity}))

    return incidents


def prepare_training_data(
    labeled_data: List[Tuple[Dict[str, Any], Dict[str, Any]]]
) -> Tuple[List[List[float]], List[int]]:
    """Prepare training data from labeled incidents.

    Args:
        labeled_data: List of (incident, context) tuples with 'severity' in incident

    Returns:
        (X feature matrix, y labels as indices)
    """
    incidents = [item[0] for item in labeled_data]
    contexts = [item[1] for item in labeled_data]

    X, _ = batch_featurize(incidents, contexts)
    y = [SEVERITY_TO_IDX[inc["severity"]] for inc in incidents]

    return X, y


def train_random_forest(
    X: List[List[float]],
    y: List[int],
    config: Optional[Dict[str, Any]] = None
) -> Any:
    """Train a Random Forest classifier.

    Args:
        X: Feature matrix
        y: Labels
        config: Optional model configuration

    Returns:
        Trained sklearn model
    """
    if not SKLEARN_AVAILABLE:
        raise ImportError("scikit-learn required for training. Install with: pip install scikit-learn")

    config = config or {}

    model = RandomForestClassifier(
        n_estimators=config.get("n_estimators", 100),
        max_depth=config.get("max_depth", 10),
        min_samples_split=config.get("min_samples_split", 5),
        min_samples_leaf=config.get("min_samples_leaf", 2),
        random_state=config.get("random_state", 42),
        n_jobs=-1,
        class_weight="balanced",
    )

    X_arr = np.array(X)
    y_arr = np.array(y)

    model.fit(X_arr, y_arr)

    return model


TRAINERS = {
    "random_forest": train_random_forest,
}


def evaluate_model(
    model: Any,
    X_test: List[List[float]],
    y_test: List[int]
) -> Dict[str, Any]:
    """Evaluate model on test set."""
    if not SKLEARN_AVAILABLE:
        return {"error": "scikit-learn not available"}

    X_arr = np.array(X_test)
    y_arr = np.array(y_test)

    y_pred = model.predict(X_arr)
    y_proba = model.predict_proba(X_arr)

    report = classification_report(
        y_arr, y_pred,
        target_names=SEVERITY_LABELS,
        output_dict=True
    )

    # Feature importances
    importances = dict(zip(ALL_FEATURE_NAMES, model.feature_importances_))

    return {
        "classification_report": report,
        "accuracy": float(report["accuracy"]),
        "feature_importances": importances,
        "confusion_matrix": confusion_matrix(y_arr, y_pred).tolist(),
    }


def train_severity_model(
    training_data: List[Tuple[Dict[str, Any], Dict[str, Any]]],
    output_dir: Path,
    model_type: str = "random_forest",
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Train and save severity classification model.

    Args:
        training_data: List of (incident, context) tuples
        output_dir: Directory to save model and metadata
        model_type: Type of model to train
        config: Model configuration

    Returns:
        Training results including metrics
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Preparing training data from {len(training_data)} samples...")
    X, y = prepare_training_data(training_data)

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=0.2,
        random_state=42,
        stratify=y
    )

    print(f"Training {model_type} model...")
    print(f"  Train samples: {len(X_train)}")
    print(f"  Test samples: {len(X_test)}")
    print(f"  Features: {len(ALL_FEATURE_NAMES)}")

    trainer = TRAINERS.get(model_type)
    if not trainer:
        raise ValueError(f"Unknown model type: {model_type}. Available: {list(TRAINERS.keys())}")

    model = trainer(X_train, y_train, config)

    # Cross-validation
    print("Running cross-validation...")
    cv_scores = cross_val_score(model, np.array(X), np.array(y), cv=5)
    print(f"  CV accuracy: {cv_scores.mean():.3f} (+/- {cv_scores.std() * 2:.3f})")

    # Evaluate on test set
    print("Evaluating on test set...")
    metrics = evaluate_model(model, X_test, y_test)

    print(f"\nTest accuracy: {metrics['accuracy']:.3f}")
    print("\nClassification Report:")
    for label in SEVERITY_LABELS:
        r = metrics["classification_report"][label]
        print(f"  {label:10s}: precision={r['precision']:.2f} recall={r['recall']:.2f} f1={r['f1-score']:.2f}")

    print("\nTop 5 feature importances:")
    sorted_imp = sorted(
        metrics["feature_importances"].items(),
        key=lambda x: x[1],
        reverse=True
    )
    for name, imp in sorted_imp[:5]:
        print(f"  {name}: {imp:.3f}")

    # Save model
    model_path = output_dir / "severity_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
    print(f"\nModel saved to: {model_path}")

    # Save metadata
    metadata = {
        "model_type": model_type,
        "feature_names": ALL_FEATURE_NAMES,
        "severity_labels": SEVERITY_LABELS,
        "n_features": len(ALL_FEATURE_NAMES),
        "n_training_samples": len(X_train),
        "cv_accuracy_mean": float(cv_scores.mean()),
        "cv_accuracy_std": float(cv_scores.std()),
        "test_accuracy": metrics["accuracy"],
        "feature_importances": metrics["feature_importances"],
    }

    metadata_path = output_dir / "severity_model.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Metadata saved to: {metadata_path}")

    return {
        "model_path": str(model_path),
        "metadata_path": str(metadata_path),
        "metrics": metrics,
        "cv_scores": cv_scores.tolist(),
    }


def load_training_data(data_path: Path) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Load training data from JSON file.

    Expected format:
    [
        {"incident": {..., "severity": "high"}, "context": {...}},
        ...
    ]
    """
    with open(data_path) as f:
        data = json.load(f)

    result = []
    for item in data:
        if isinstance(item, dict):
            if "incident" in item:
                incident = item["incident"]
                context = item.get("context", {})
            else:
                # Assume item is the incident itself
                incident = item
                context = {}
            result.append((incident, context))

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train severity classification model"
    )
    parser.add_argument(
        "--data",
        type=Path,
        help="Path to training data JSON file"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models"),
        help="Output directory for model and metadata"
    )
    parser.add_argument(
        "--model-type",
        choices=list(TRAINERS.keys()),
        default="random_forest",
        help="Type of model to train"
    )
    parser.add_argument(
        "--generate-sample",
        action="store_true",
        help="Generate and use sample training data"
    )
    parser.add_argument(
        "--n-samples",
        type=int,
        default=500,
        help="Number of samples to generate (with --generate-sample)"
    )

    args = parser.parse_args()

    if not SKLEARN_AVAILABLE:
        print("ERROR: scikit-learn is required for training")
        print("Install with: pip install scikit-learn")
        return 1

    if args.generate_sample:
        print(f"Generating {args.n_samples} sample incidents...")
        training_data = generate_sample_incidents(args.n_samples)
    elif args.data:
        print(f"Loading training data from {args.data}...")
        training_data = load_training_data(args.data)
    else:
        print("ERROR: Either --data or --generate-sample required")
        parser.print_help()
        return 1

    if not training_data:
        print("ERROR: No training data available")
        return 1

    result = train_severity_model(
        training_data,
        args.output,
        model_type=args.model_type
    )

    print(f"\nTraining complete!")
    print(f"  Model: {result['model_path']}")
    print(f"  Metadata: {result['metadata_path']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
