"""Central configuration. Safety-relevant limits live here so they are easy to audit."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REGULATIONS_DIR = DATA_DIR / "regulations"
RULES_DIR = DATA_DIR / "rules"
SAMPLES_DIR = DATA_DIR / "sample_plans"

RUNTIME_DIR = Path(os.environ.get("PROVENAI_RUNTIME_DIR", ROOT / ".runtime"))
CHROMA_DIR = RUNTIME_DIR / "chroma"
DATABASE = RUNTIME_DIR / "inspections.sqlite3"

# Below this extraction confidence the engine returns UNKNOWN.
MIN_CONFIDENCE = 0.80
# Below this retrieval relevance (cosine similarity) a rule's source counts as not found.
MIN_RELEVANCE = 0.35
# A rule's clause must appear among this many top search results.
RETRIEVAL_TOP_K = 3
