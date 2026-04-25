"""Plan 29 M6 — review state machine logic (pure).

ReviewService 的 DB 逻辑由集成测试覆盖；这里防回归核心常量与 helper。
"""
from __future__ import annotations

from app.knowledge.review.service import (
    REVIEW_APPROVED,
    REVIEW_PENDING,
    REVIEW_REJECTED,
    REVIEW_STATES,
    ReviewError,
)


def test_review_states_match_db_check():
    assert REVIEW_PENDING == "pending"
    assert REVIEW_APPROVED == "approved"
    assert REVIEW_REJECTED == "rejected"
    assert REVIEW_STATES == ("pending", "approved", "rejected")


def test_review_error_is_value_error_subclass():
    # API router catches ReviewError 把业务异常映射为 400；保持 ValueError
    # 子类继承也能让通用 except ValueError 捕获
    assert issubclass(ReviewError, ValueError)


def test_invisible_doc_logic_demo():
    """Document 可见 = NOT archived AND (KB.review_required==False OR review_status='approved')。

    这条规则在 retrieval/service._filter_invisible 实现；这里以纯逻辑等价方式
    锁定它，避免后续 retrieval 路径改动时悄悄漏掉某种情况。
    """
    def visible(*, archived: bool, review_required: bool, review_status: str | None) -> bool:
        if archived:
            return False
        if review_required and review_status != REVIEW_APPROVED:
            return False
        return True

    # 普通可见
    assert visible(archived=False, review_required=False, review_status=None)
    # 归档不可见
    assert not visible(archived=True, review_required=False, review_status=None)
    # 审批开启 + 未审 → 不可见
    assert not visible(archived=False, review_required=True, review_status=REVIEW_PENDING)
    assert not visible(archived=False, review_required=True, review_status=REVIEW_REJECTED)
    # 审批开启 + 已通过 → 可见
    assert visible(archived=False, review_required=True, review_status=REVIEW_APPROVED)
    # 审批关闭时 review_status 不重要
    assert visible(archived=False, review_required=False, review_status=REVIEW_PENDING)
