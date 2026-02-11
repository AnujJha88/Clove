"""
Research World Configuration

Configure API keys, models, and research parameters.
"""

import os
from pathlib import Path

# =============================================================================
# PATHS
# =============================================================================
BASE_DIR = Path(__file__).parent

# Load .env file if it exists
env_file = BASE_DIR / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())
DATA_DIR = BASE_DIR / "data"
PDF_DIR = DATA_DIR / "pdfs"
PROCESSED_DIR = DATA_DIR / "processed"
CHECKPOINT_DIR = BASE_DIR / "checkpoints"
REPORTS_DIR = BASE_DIR / "reports"
LOGS_DIR = BASE_DIR / "logs"

# Create directories
for d in [PDF_DIR, PROCESSED_DIR, CHECKPOINT_DIR, REPORTS_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# =============================================================================
# API KEYS - Add your 10 keys here
# =============================================================================
API_KEYS = [
    os.environ.get("GOOGLE_API_KEY_1", ""),
    os.environ.get("GOOGLE_API_KEY_2", ""),
    os.environ.get("GOOGLE_API_KEY_3", ""),
    os.environ.get("GOOGLE_API_KEY_4", ""),
    os.environ.get("GOOGLE_API_KEY_5", ""),
    os.environ.get("GOOGLE_API_KEY_6", ""),
    os.environ.get("GOOGLE_API_KEY_7", ""),
    os.environ.get("GOOGLE_API_KEY_8", ""),
    os.environ.get("GOOGLE_API_KEY_9", ""),
    os.environ.get("GOOGLE_API_KEY_10", ""),
]

# Filter out empty keys
API_KEYS = [k for k in API_KEYS if k]

# Fallback to single key if pool not configured
if not API_KEYS:
    single_key = os.environ.get("GOOGLE_API_KEY", "")
    if single_key:
        API_KEYS = [single_key]

# =============================================================================
# MODEL CONFIGURATION
# =============================================================================
MODEL_NAME = "gemini-2.0-flash"  # Fast model for research
MODEL_NAME_DEEP = "gemini-1.5-pro"  # Deep model for synthesis

# =============================================================================
# RESEARCH PARAMETERS
# =============================================================================
MAX_RESEARCH_HOURS = 4  # Maximum research duration
MAX_AGENTS = 5  # Number of parallel research agents
CHECKPOINT_INTERVAL_MINUTES = 5  # Save progress every N minutes

# Rate limiting per key
REQUESTS_PER_MINUTE_PER_KEY = 15  # Conservative to avoid 429
COOLDOWN_SECONDS = 4  # Seconds between requests per key

# =============================================================================
# AGENT CONFIGURATION
# =============================================================================
AGENT_ROLES = {
    "literature_reviewer": "Reviews scientific literature and extracts key findings",
    "data_analyst": "Analyzes data, statistics, and quantitative results",
    "methodology_expert": "Evaluates research methods and experimental design",
    "synthesizer": "Combines findings from multiple sources into coherent insights",
    "critic": "Identifies gaps, limitations, and counter-arguments",
}
