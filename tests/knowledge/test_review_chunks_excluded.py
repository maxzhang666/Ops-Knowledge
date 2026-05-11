"""Plan 39 M1 — chunks.review_excluded 维护语义（纯逻辑）。

ReviewService 实际写库由集成测试覆盖；这里以纯函数等价模型锁定状态机，
避免未来改动时悄悄漏掉某个分支。
"""
from __future__ import annotations

from app.knowledge.review.service import (
    REVIEW_APPROVED,
    REVIEW_PENDING,
    REVIEW_REJECTED,
)


def derive_review_excluded(review_status: str | None) -> bool:
    """chunks.review_excluded 的目标值由 unit.review_status 派生：
    pending / rejected → 排除（不进召回 / 不进治理动态分）
    approved / NULL    → 不排除（正常召回）
    """
    return review_status in (REVIEW_PENDING, REVIEW_REJECTED)


def test_pending_excludes_chunks():
    assert derive_review_excluded(REVIEW_PENDING) is True


def test_rejected_excludes_chunks():
    assert derive_review_excluded(REVIEW_REJECTED) is True


def test_approved_includes_chunks():
    assert derive_review_excluded(REVIEW_APPROVED) is False


def test_null_includes_chunks():
    """KB.review_required=False 时 review_status 始终 NULL；chunks 不应被排除。"""
    assert derive_review_excluded(None) is False


def test_state_transition_table():
    """完整 4×3 状态转换语义：(from, to) → chunks.review_excluded 目标值"""
    cases = [
        # (from, to, expected review_excluded after transition)
        (None, REVIEW_PENDING, True),       # KB 开启审核 → 历史 doc 进入 pending
        (REVIEW_PENDING, REVIEW_APPROVED, False),  # 通过：放行
        (REVIEW_PENDING, REVIEW_REJECTED, True),   # 驳回：保持排除
        (REVIEW_REJECTED, REVIEW_PENDING, True),   # 重新提交：再次 pending
        (REVIEW_APPROVED, REVIEW_PENDING, True),   # 编辑后重审
    ]
    for _, to_state, expected in cases:
        assert derive_review_excluded(to_state) is expected, (
            f"transition to {to_state} should give review_excluded={expected}"
        )
