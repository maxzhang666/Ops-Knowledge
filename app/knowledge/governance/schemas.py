"""Governance schemas (Plan 32 M2).

Health score = weighted sum of 4 facets, each normalized to [0, 100]:
  - chunk quality (avg quality_composite × 100)
  - coverage (% of chunks with hit_count > 0 in last 30d)
  - freshness (% of documents NOT stale)
  - availability (% retrievals that returned > 0 chunks in last 7d)

Default weights 25/25/25/25; tunable per-system via SystemSettings.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


DEFAULT_WEIGHTS: dict[str, float] = {
    "chunk_quality": 0.2,
    "coverage": 0.2,
    "freshness": 0.2,
    "availability": 0.2,
    "answer_quality": 0.2,
}


class GovernanceWeights(BaseModel):
    chunk_quality: float = Field(0.2, ge=0, le=1)
    coverage: float = Field(0.2, ge=0, le=1)
    freshness: float = Field(0.2, ge=0, le=1)
    availability: float = Field(0.2, ge=0, le=1)
    answer_quality: float = Field(0.2, ge=0, le=1)  # Plan 25 Layer 4

    def normalized(self) -> dict[str, float]:
        """Re-scale to sum to 1 — ops editing weights shouldn't have to
        do the arithmetic themselves."""
        total = (
            self.chunk_quality + self.coverage + self.freshness
            + self.availability + self.answer_quality
        )
        if total <= 0:
            return dict(DEFAULT_WEIGHTS)
        return {
            "chunk_quality": self.chunk_quality / total,
            "coverage": self.coverage / total,
            "freshness": self.freshness / total,
            "availability": self.availability / total,
            "answer_quality": self.answer_quality / total,
        }


class FacetScore(BaseModel):
    score: float  # 0-100
    weight: float  # 0-1, normalized
    detail: dict  # facet-specific stats (chunk counts, cold counts, …)


class GovernanceAlert(BaseModel):
    """Actionable alert displayed as a dashboard card. ``action_href`` is
    a relative URL the frontend can jump to."""
    severity: Literal["info", "warning", "critical"]
    kind: Literal[
        "stale_docs", "low_quality_chunks", "cold_chunks",
        "knowledge_gap", "redundancy",
    ]
    title: str
    count: int
    preview: list[dict]   # top N concrete items for quick scan
    action_href: str | None = None


class GovernanceHealthResponse(BaseModel):
    kb_id: uuid.UUID
    health_score: float   # 0-100 weighted composite
    facets: dict[str, FacetScore]
    alerts: list[GovernanceAlert]
    trend: dict   # { "chunk_quality": [{"t": iso, "v": 72}, ...], ... }  (7d)
    generated_at: datetime


class GovernanceOverviewItem(BaseModel):
    kb_id: uuid.UUID
    kb_name: str
    health_score: float
    alerts_critical: int
    alerts_warning: int


class GovernanceOverview(BaseModel):
    kbs: list[GovernanceOverviewItem]
    avg_health_score: float
    generated_at: datetime


class KBGovernanceConfig(BaseModel):
    """Writable KB-level lifecycle knobs (Plan 32 M3 consumer)."""
    expiration_threshold_days: int = Field(90, ge=1, le=3650)
    auto_archive_idle_days: int = Field(30, ge=1, le=3650)
