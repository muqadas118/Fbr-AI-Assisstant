"""
Self-Learning / Personalization Backend
=======================================

Behavioural personalization module for the FBR assistant.

This is **behavioural personalization, NOT model training**. Nothing in
this package reads, writes, or changes any model weights. It only records
one user's own derived signals, aggregates them into a per-user profile,
and reshapes the recommendations that single user sees.

Public contract (kept stable for downstream consumers):
    get_learning_store() -> LearningStore     # process-wide singleton
    LearningStore, UserProfile, Recommendation, Signal

Privacy by design:
    * Raw query text is stored only when env `FBR_LEARNING_STORE_RAW_QUERIES=1`
      (default OFF); derived signals are stored otherwise.
    * Retention cap via `FBR_LEARNING_RETENTION_DAYS` (default 90) and a hard
      500-interaction per-user row cap.
    * Every store method degrades safely (empty/None) and never raises into
      the request path when the store is unavailable or personalization is off.
"""

from app.learning.profile import (
    Signal,
    UserProfile,
    build_profile,
    extract_signals,
)
from app.learning.recommender import (
    Recommendation,
    build_recommendations,
)
from app.learning.store import LearningStore, get_learning_store

__all__ = [
    "get_learning_store",
    "LearningStore",
    "UserProfile",
    "build_profile",
    "extract_signals",
    "Recommendation",
    "build_recommendations",
    "Signal",
]
