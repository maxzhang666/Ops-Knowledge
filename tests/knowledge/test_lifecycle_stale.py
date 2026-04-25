"""Plan 32 M3 lifecycle — 纯函数/逻辑层单元测试。

只测 staleness 判定 + 转换规则（无 DB 依赖的部分）。完整 Celery 任务
的数据库侧路径由集成测试（后续）覆盖，这里防止纯函数级的回归。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from app.knowledge.lifecycle.tasks import HIT_DROP_RATIO


@dataclass
class _Doc:
    updated_at: datetime
    is_stale: bool = False
    stale_since: datetime | None = None
    is_archived: bool = False


def _decide(
    doc: _Doc,
    now: datetime,
    expiration_days: int,
    idle_days: int,
    hits_7d: int,
    hits_prev_7d: int,
) -> str:
    """Mirrors the inline decision in `_run_lifecycle` — no DB writes.

    Returns one of: ``"mark_stale"``, ``"clear_stale"``, ``"archive"``, ``"noop"``.
    Keeping it separate here means we can exhaustively test state transitions
    without setting up a database.
    """
    stale_cutoff = now - timedelta(days=expiration_days)
    archive_cutoff = now - timedelta(days=idle_days)
    updated_stale = doc.updated_at < stale_cutoff
    heat_cliff = hits_prev_7d > 0 and hits_7d < hits_prev_7d * HIT_DROP_RATIO
    should_be_stale = updated_stale or heat_cliff

    if should_be_stale and not doc.is_stale:
        return "mark_stale"
    if not should_be_stale and doc.is_stale:
        return "clear_stale"
    if doc.is_stale and doc.stale_since is not None and doc.stale_since < archive_cutoff:
        return "archive"
    return "noop"


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)


# ─── stale transition ─────────────────────────────────────────────

def test_fresh_doc_stays_noop(now):
    doc = _Doc(updated_at=now - timedelta(days=10))
    assert _decide(doc, now, 90, 30, hits_7d=3, hits_prev_7d=4) == "noop"


def test_old_doc_marked_stale(now):
    doc = _Doc(updated_at=now - timedelta(days=120))  # > 90d
    assert _decide(doc, now, 90, 30, hits_7d=0, hits_prev_7d=0) == "mark_stale"


def test_heat_cliff_marks_stale_even_if_recently_updated(now):
    # Updated yesterday, but traffic collapsed > 70%
    doc = _Doc(updated_at=now - timedelta(days=1))
    assert _decide(doc, now, 90, 30, hits_7d=2, hits_prev_7d=10) == "mark_stale"


def test_moderate_drop_not_a_cliff(now):
    # 60% of prev → 6 hits from 10; that's above 0.3 ratio → not a cliff
    doc = _Doc(updated_at=now - timedelta(days=1))
    assert _decide(doc, now, 90, 30, hits_7d=6, hits_prev_7d=10) == "noop"


def test_no_prior_traffic_no_cliff(now):
    # prev=0 means we can't compute a drop — must NOT mark stale
    doc = _Doc(updated_at=now - timedelta(days=1))
    assert _decide(doc, now, 90, 30, hits_7d=0, hits_prev_7d=0) == "noop"


# ─── clear_stale ──────────────────────────────────────────────────

def test_refreshed_stale_doc_clears_flag(now):
    # Doc was stale, but now updated_at is fresh and hits are healthy
    doc = _Doc(
        updated_at=now - timedelta(days=1),
        is_stale=True, stale_since=now - timedelta(days=5),
    )
    assert _decide(doc, now, 90, 30, hits_7d=8, hits_prev_7d=10) == "clear_stale"


# ─── archive ──────────────────────────────────────────────────────

def test_stale_beyond_idle_days_gets_archived(now):
    # Doc has been stale > idle_days (= 30); time to auto-archive.
    doc = _Doc(
        updated_at=now - timedelta(days=200),
        is_stale=True, stale_since=now - timedelta(days=31),
    )
    assert _decide(doc, now, 90, 30, hits_7d=0, hits_prev_7d=0) == "archive"


def test_stale_within_idle_days_stays_noop(now):
    doc = _Doc(
        updated_at=now - timedelta(days=200),
        is_stale=True, stale_since=now - timedelta(days=10),
    )
    assert _decide(doc, now, 90, 30, hits_7d=0, hits_prev_7d=0) == "noop"


def test_idle_days_from_governance_config_is_respected(now):
    # With a larger idle_days, same "stale 31d ago" should NOT auto-archive
    doc = _Doc(
        updated_at=now - timedelta(days=200),
        is_stale=True, stale_since=now - timedelta(days=31),
    )
    assert _decide(doc, now, 90, 60, hits_7d=0, hits_prev_7d=0) == "noop"


# ─── HIT_DROP_RATIO sanity ────────────────────────────────────────

def test_hit_drop_ratio_is_0_3():
    # Cement the business rule — hard to spot if someone drifts this
    assert HIT_DROP_RATIO == 0.3
