"""Dynamic score formula (Plan 32 M1.6).

Isolated from the Celery task so it's testable without a DB. Composes
three signals per chunk:

  adoption_rate = adopted / max(hit, 1)
  feedback_score = (pos - neg) / (pos + neg)   # maps to [-1, 1], 0 if no feedback
  usage_reliability = 1 − 1 / (1 + hit / 20)    # S-curve approaching 1 past 20 hits

  dynamic_raw = 0.5 * adoption_rate + 0.3 * ((feedback_score + 1) / 2) + 0.2 * (hit / (hit + 5))

Weights tuned so a chunk with ~20 hits, ~60% adoption, neutral feedback
lands around 0.55 — a realistic "works but not great" baseline.

Composite = static * w_s + dynamic * w_d, w_s sliding 1 → 0.4 as hit
grows past 20 (w_s = clamp(1 − 0.6 * min(hit, 60) / 60, 0.4, 1.0)).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChunkStats:
    hit: int
    adopted: int
    feedback_positive: int
    feedback_negative: int


def compute_dynamic(stats: ChunkStats) -> float:
    """Returns dynamic score in [0, 1]. No-usage chunks return 0 (not None)
    — caller decides whether to use composite vs static alone via weight."""
    hit = max(stats.hit, 0)
    adopted = max(stats.adopted, 0)
    pos = max(stats.feedback_positive, 0)
    neg = max(stats.feedback_negative, 0)

    if hit == 0:
        return 0.0

    adoption_rate = min(adopted / hit, 1.0)
    total_fb = pos + neg
    if total_fb > 0:
        feedback_score = (pos - neg) / total_fb  # in [-1, 1]
        feedback_component = (feedback_score + 1) / 2  # in [0, 1]
    else:
        feedback_component = 0.5  # neutral — don't penalize for no feedback
    hit_component = hit / (hit + 5.0)  # 0 @ 0 hits, 0.67 @ 10, 0.95 @ 100

    return (
        0.5 * adoption_rate
        + 0.3 * feedback_component
        + 0.2 * hit_component
    )


def compute_composite(
    static_score: float | None, dynamic_score: float, hit: int,
) -> float:
    """Blend static + dynamic. w_s decays 1 → 0.4 as hit grows past 20."""
    if static_score is None:
        # No static score available — rely on dynamic
        return dynamic_score
    progress = min(max(hit, 0), 60) / 60.0
    w_s = max(1.0 - 0.6 * progress, 0.4)
    w_d = 1.0 - w_s
    return w_s * static_score + w_d * dynamic_score
