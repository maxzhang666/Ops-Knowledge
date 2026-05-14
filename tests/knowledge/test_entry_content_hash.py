"""#5 — entry content_hash 行为单测。

验证 _content_hash 与 alembic 0060 backfill 的 sha256 输出一致，保证
迁移行能被 plugin update 路径正确比对（否则首次 update 一律视为 content
变化、触发不必要的 reembed）。
"""
from __future__ import annotations

import hashlib

from app.knowledge.sources.entry import _content_hash


def test_content_hash_matches_sha256_hex():
    """与 PG `encode(digest(content, 'sha256'), 'hex')` 输出严格一致。"""
    content = "Hello, 世界 🚀"
    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert _content_hash(content) == expected


def test_content_hash_is_deterministic():
    """同输入两次必得同 hash（无随机/盐）。"""
    s = "Reproducible content " * 100
    assert _content_hash(s) == _content_hash(s)


def test_content_hash_differs_on_single_char_change():
    """单字符改动必须改 hash —— 否则 short-circuit 会跳过该编辑。"""
    a = "Original content"
    b = "Original content."  # extra dot
    assert _content_hash(a) != _content_hash(b)


def test_content_hash_handles_empty_string():
    """空 content 也要给出 well-defined hash（DB 列允许 nullable，但写入路径不应抛）。"""
    h = _content_hash("")
    assert len(h) == 64
    # sha256("") well-known hex prefix
    assert h.startswith("e3b0c44298fc1c14")
