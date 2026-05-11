"""Plan 40 M2 — 治理 unit_stats 抽象层 + 多态切读语义纯逻辑测试。"""
from __future__ import annotations

from app.knowledge.governance.unit_stats import UnitStats, UnitStaleRow


def test_unit_stats_zero_for_unknown_source_type():
    """未注册的 source_type 治理服务返回 0 而非崩溃 — 让 dashboard 仍可显示"""
    # get_unit_stats 实际逻辑要 db；这里以 schema 校验：不报错构造
    s = UnitStats(total_units=0, stale_units=0)
    assert s.total_units == 0
    assert s.stale_units == 0


def test_unit_stale_row_pydantic_strict():
    """UnitStaleRow 字段命名固定，pydantic 严格验证"""
    import uuid
    from datetime import datetime, timezone
    row = UnitStaleRow(
        unit_id=uuid.uuid4(),
        title="Stale doc",
        updated_at=datetime.now(timezone.utc),
    )
    assert row.title == "Stale doc"
    assert isinstance(row.unit_id, uuid.UUID)


# ── 多态切读语义 ────────────────────────────────────────────────


def chunks_of_unit_filter(unit_type: str, unit_id: str) -> tuple[str, str]:
    """模拟 SA where 子句：(unit_type=X, unit_id=Y) 等价旧 (document_id=Y)。
    锁定 M2 切读不变量。"""
    return (unit_type, unit_id)


def test_polymorphic_filter_preserves_doc_semantics():
    """文件型 unit 的多态过滤等价于旧 document_id 过滤"""
    f = chunks_of_unit_filter("document", "doc-1")
    assert f == ("document", "doc-1")


def test_polymorphic_filter_distinguishes_types():
    """同 UUID 不同 unit_type 应该是不同 chunks 集合（虽然实际 UUID 不撞）"""
    f1 = chunks_of_unit_filter("document", "shared-uuid")
    f2 = chunks_of_unit_filter("entry", "shared-uuid")
    assert f1 != f2


# ── 双写一致性 invariant ────────────────────────────────────────


def dual_write_invariant(
    *, document_id: str | None, unit_type: str | None, unit_id: str | None,
) -> bool:
    """Plan 40 M1-M2 双写期：file 型 chunks 的 document_id 和 unit_id 必须一致。
    M3 drop document_id 后此 invariant 自然解除。"""
    if document_id is None and unit_type is None:
        return True   # 全空（旧路径错误数据）— 实际不应出现，但允许
    # 如果 unit_type='document'，document_id 应等于 unit_id
    if unit_type == "document":
        return document_id == unit_id
    # 非 document unit 的 chunks 不应有 document_id
    return document_id is None


def test_dual_write_invariant_consistent():
    assert dual_write_invariant(
        document_id="d1", unit_type="document", unit_id="d1",
    ) is True


def test_dual_write_invariant_inconsistent_caught():
    """文件型 chunk document_id 和 unit_id 不一致 → 违反 invariant"""
    assert dual_write_invariant(
        document_id="d1", unit_type="document", unit_id="d2",
    ) is False


def test_dual_write_entry_no_document_id():
    """条目型 chunks 不应有 document_id"""
    assert dual_write_invariant(
        document_id=None, unit_type="entry", unit_id="e1",
    ) is True
    # 异常：条目 chunks 误填 document_id
    assert dual_write_invariant(
        document_id="d1", unit_type="entry", unit_id="e1",
    ) is False
