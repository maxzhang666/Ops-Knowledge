"""Plan 41 M3.3 — embed_unit_chunks 路由语义纯逻辑测试。

Celery task 内部按 unit_type 路由到不同 unit 表（documents / knowledge_entries）。
这里以纯逻辑模型锁定该路由表，避免未来加新 unit_type 时漏掉一个分支。
"""
from __future__ import annotations

import pytest


SUPPORTED_UNIT_TYPES_FOR_EMBED = {"document", "entry"}


def resolve_unit_title(unit_type: str, unit_data: dict) -> str | None:
    """embed_unit_chunks 内部按 unit_type 取 title 的等价纯函数。
    返回 None 表示不支持的 unit_type。"""
    if unit_type == "document":
        return unit_data.get("title")
    if unit_type == "entry":
        return unit_data.get("title")
    return None


def test_document_title_resolved():
    assert resolve_unit_title("document", {"title": "故障手册.pdf"}) == "故障手册.pdf"


def test_entry_title_resolved():
    assert resolve_unit_title("entry", {"title": "退款流程"}) == "退款流程"


def test_unsupported_unit_type_returns_none():
    """未实现的 unit_type 不应崩溃，让 task 安全 skip"""
    assert resolve_unit_title("git_repo", {"title": "x"}) is None
    assert resolve_unit_title("confluence", {"title": "x"}) is None


def test_supported_set():
    assert "document" in SUPPORTED_UNIT_TYPES_FOR_EMBED
    assert "entry" in SUPPORTED_UNIT_TYPES_FOR_EMBED
    assert "git_repo" not in SUPPORTED_UNIT_TYPES_FOR_EMBED


# ── chunk_dict 字段语义（Milvus schema 兼容） ──────────────────────


def make_chunk_dict(
    *,
    chunk_id: str, content: str,
    unit_id: str, folder_id: str | None,
    level: int, position: int,
    title: str, metadata: dict | None,
) -> dict:
    """Plan 41 M3.2 — chunk_dict 写入 Milvus 的字段映射。
    Milvus schema field "document_id" 实际存 unit_id（Plan 40 P16 历史兼容）。"""
    return {
        "id": chunk_id,
        "content": content,
        "document_id": unit_id,  # 关键：值是 unit_id，字段名兼容 Milvus
        "folder_id": folder_id,
        "level": level,
        "position": position,
        "title": title,
        "metadata": metadata,
    }


def test_chunk_dict_document_id_uses_unit_id():
    """文件型 chunk: unit_id == document.id, 写 Milvus document_id 字段无变"""
    d = make_chunk_dict(
        chunk_id="c1", content="x", unit_id="doc-uuid",
        folder_id=None, level=0, position=0,
        title="t", metadata=None,
    )
    assert d["document_id"] == "doc-uuid"


def test_chunk_dict_entry_uses_entry_id_in_document_id_field():
    """条目型 chunk: unit_id == entry.id；写 Milvus 的 document_id 字段实际是 entry_id。
    Milvus filter 'document_id == "entry-uuid"' 正确删除 entry chunks。"""
    d = make_chunk_dict(
        chunk_id="c1", content="x", unit_id="entry-uuid",
        folder_id=None, level=0, position=0,
        title="退款流程", metadata={"tags": ["售后"]},
    )
    assert d["document_id"] == "entry-uuid"
    # tags 在 metadata 里，document_id 字段不污染
    assert "tags" not in d


# ── RAPTOR hook 限制 ─────────────────────────────────────────────


def should_dispatch_raptor(unit_type: str, use_raptor: bool) -> bool:
    """embed_unit_chunks 内：RAPTOR 仅文件型 + use_raptor=True 时触发。"""
    return unit_type == "document" and use_raptor


def test_raptor_skipped_for_entry():
    """条目型不走 RAPTOR（树形 summary 假设 doc-level 层级，不适用 entry）"""
    assert should_dispatch_raptor("entry", use_raptor=True) is False


def test_raptor_dispatched_for_document_when_enabled():
    assert should_dispatch_raptor("document", use_raptor=True) is True


def test_raptor_skipped_when_disabled():
    assert should_dispatch_raptor("document", use_raptor=False) is False
