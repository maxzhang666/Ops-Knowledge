"""Plan 39 M4 — 检索/治理过滤算法纯逻辑回归。

retrieval._filter_invisible 和 governance 各处的 chunks 过滤底层都是
"chunk.review_excluded=False AND document.is_archived=False" 的等价表达。
这里以纯函数模型锁定该不变量，避免后续重构时漏掉某个分支。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChunkRow:
    chunk_id: str
    document_id: str
    review_excluded: bool


@dataclass
class DocumentRow:
    id: str
    is_archived: bool


def filter_visible_chunks(
    chunks: list[ChunkRow], docs: list[DocumentRow],
) -> list[ChunkRow]:
    """retrieval._filter_invisible 的等价纯逻辑表示。"""
    archived = {d.id for d in docs if d.is_archived}
    return [
        c for c in chunks
        if not c.review_excluded and c.document_id not in archived
    ]


def test_pending_chunks_filtered_out():
    chunks = [
        ChunkRow("c1", "d1", review_excluded=False),
        ChunkRow("c2", "d1", review_excluded=True),   # pending
        ChunkRow("c3", "d2", review_excluded=False),
    ]
    docs = [DocumentRow("d1", False), DocumentRow("d2", False)]
    visible = filter_visible_chunks(chunks, docs)
    assert {c.chunk_id for c in visible} == {"c1", "c3"}


def test_archived_doc_chunks_filtered_out():
    chunks = [
        ChunkRow("c1", "d1", review_excluded=False),
        ChunkRow("c2", "d2", review_excluded=False),
    ]
    docs = [DocumentRow("d1", True), DocumentRow("d2", False)]   # d1 archived
    visible = filter_visible_chunks(chunks, docs)
    assert {c.chunk_id for c in visible} == {"c2"}


def test_both_filters_compose():
    """同时 archived + review_excluded → 仍然不可见（不会因双重排除翻出来）"""
    chunks = [
        ChunkRow("c1", "d1", review_excluded=True),   # pending
        ChunkRow("c2", "d2", review_excluded=False),
    ]
    docs = [DocumentRow("d1", True), DocumentRow("d2", False)]
    visible = filter_visible_chunks(chunks, docs)
    assert {c.chunk_id for c in visible} == {"c2"}


def test_legacy_kb_unaffected():
    """KB.review_required=False 时 chunks 全部 review_excluded=False（默认）→ 全部可见"""
    chunks = [ChunkRow(f"c{i}", "d1", review_excluded=False) for i in range(5)]
    docs = [DocumentRow("d1", False)]
    visible = filter_visible_chunks(chunks, docs)
    assert len(visible) == 5


# ── 候选审核员算法（纯集合操作）────────────────────────────────────


def candidate_reviewers(
    *,
    shared_dept_admins: set[str],
    owner_dept_admins: set[str],
    system_admins: set[str],
    creator_id: str,
) -> set[str]:
    """reviewers.get_candidate_reviewers 的等价纯逻辑表示。"""
    candidates = shared_dept_admins | owner_dept_admins | system_admins
    return candidates - {creator_id}


def test_creator_excluded_from_candidates():
    result = candidate_reviewers(
        shared_dept_admins={"alice"},
        owner_dept_admins={"alice", "bob"},
        system_admins={"root"},
        creator_id="alice",
    )
    assert "alice" not in result   # creator never reviews own
    assert {"bob", "root"} == result


def test_system_admin_always_candidate():
    """KB 未共享给任何部门 → 仅 system_admin 可审"""
    result = candidate_reviewers(
        shared_dept_admins=set(),
        owner_dept_admins=set(),
        system_admins={"root"},
        creator_id="alice",
    )
    assert result == {"root"}


def test_shared_dept_overrides_owner_dept():
    """shared 部门和 owner 部门的 admin 取并集，无差别"""
    result = candidate_reviewers(
        shared_dept_admins={"a", "b"},
        owner_dept_admins={"c"},
        system_admins={"root"},
        creator_id="x",
    )
    assert result == {"a", "b", "c", "root"}


# ── 通知去重逻辑 ─────────────────────────────────────────────────────


def should_notify_review_pending(
    *,
    last_pending_started_at: float | None,
    notif_created_ats: list[float],
) -> bool:
    """_notify_reviewers 去重逻辑：last_pending_started_at 之后已发过通知则跳过"""
    if last_pending_started_at is None:
        return True
    return not any(t > last_pending_started_at for t in notif_created_ats)


def test_dedup_first_submission_notifies():
    assert should_notify_review_pending(
        last_pending_started_at=100.0,
        notif_created_ats=[],
    ) is True


def test_dedup_same_pending_window_skipped():
    """pending 窗口内已发过 → 跳过"""
    assert should_notify_review_pending(
        last_pending_started_at=100.0,
        notif_created_ats=[101.0],
    ) is False


def test_dedup_resets_after_new_pending():
    """approved → 编辑 → pending（last_pending_started_at 推进）→ 又发一条"""
    assert should_notify_review_pending(
        last_pending_started_at=200.0,            # 新一轮 pending
        notif_created_ats=[101.0],                # 旧通知早于新窗口
    ) is True
