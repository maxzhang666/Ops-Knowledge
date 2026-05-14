"""Task failure tracking 纯逻辑单测：mock signal payload / mock celery send_task。

集成测试（真实 worker → 真实 DB）见 spec 19 §16 手测清单。
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.system import celery_failures


def test_json_safe_handles_uuid_datetime():
    """UUID / datetime / Decimal 等非原生类型走 default=str 兜底。"""
    import uuid
    from datetime import datetime
    from decimal import Decimal

    obj = {
        "kb_id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "when": datetime(2026, 5, 13, 9, 20, 10),
        "amount": Decimal("1.5"),
        "nested": [uuid.UUID("00000000-0000-0000-0000-000000000002")],
    }
    result = celery_failures._json_safe(obj)
    assert isinstance(result, dict)
    assert result["kb_id"] == "00000000-0000-0000-0000-000000000001"
    assert result["amount"] == "1.5"
    assert isinstance(result["nested"], list)


def test_json_safe_returns_none_on_unserializable():
    """完全不可序列化（自定义对象无 __str__？）走 fallback。"""
    class _Weird:
        def __repr__(self):
            raise RuntimeError("kapow")

    # default=str 实际上会调用 str(obj)，触发 __repr__ → 异常 → json.dumps 报错
    result = celery_failures._json_safe({"x": _Weird()})
    assert result is None


def test_coerce_uuid_accepts_string_and_obj():
    import uuid
    u = uuid.uuid4()
    assert celery_failures._coerce_uuid(u) == u
    assert celery_failures._coerce_uuid(str(u)) == u
    assert celery_failures._coerce_uuid("not-a-uuid") is None
    assert celery_failures._coerce_uuid(None) is None


def test_extract_kb_id_from_kwargs():
    import uuid
    kb = uuid.uuid4()
    assert celery_failures._extract_kb_id([], {"kb_id": str(kb)}) == kb


def test_extract_kb_id_from_first_arg():
    import uuid
    kb = uuid.uuid4()
    assert celery_failures._extract_kb_id([str(kb), "other"], {}) == kb


def test_extract_kb_id_returns_none_when_none_match():
    assert celery_failures._extract_kb_id(["not-a-uuid"], {"foo": "bar"}) is None
    assert celery_failures._extract_kb_id([], {}) is None


def test_on_task_unknown_parses_celery_body(monkeypatch):
    """worker 收到 unregistered task 时，message.body 是 JSON 编码的
    `[args, kwargs, embed]` —— signal handler 解析后写表。"""
    captured: dict = {}

    def _capture(**fields):
        captured.update(fields)

    monkeypatch.setattr(celery_failures, "_write_failure", _capture)

    fake_message = MagicMock()
    fake_message.body = json.dumps([
        ["45feb627-e7ba-464d-a5ce-361765a9c7c8"],
        {},
        {"callbacks": None},
    ]).encode("utf-8")

    celery_failures._on_task_unknown(
        sender=None, message=fake_message, exc=KeyError("foo"),
        name="app.knowledge.milvus.governance_tasks.scan_orphan_vectors",
        id="13fd3093-8eb6-41fd-92f7-2393af4d4992",
    )

    assert captured["state"] == "UNREGISTERED"
    assert captured["task_name"] == "app.knowledge.milvus.governance_tasks.scan_orphan_vectors"
    assert captured["task_id"] == "13fd3093-8eb6-41fd-92f7-2393af4d4992"
    assert captured["args_json"] == ["45feb627-e7ba-464d-a5ce-361765a9c7c8"]
    assert captured["kwargs_json"] == {}
    # kb_id 从 first arg 启发式提取
    assert str(captured["kb_id"]) == "45feb627-e7ba-464d-a5ce-361765a9c7c8"


def test_on_task_unknown_falls_back_to_base64(monkeypatch):
    """body 不是有效 JSON 时存 base64 供调试。"""
    captured: dict = {}
    monkeypatch.setattr(celery_failures, "_write_failure", lambda **f: captured.update(f))

    fake_message = MagicMock()
    fake_message.body = b"\x80\x81\x82 not json"

    celery_failures._on_task_unknown(
        sender=None, message=fake_message, exc=KeyError("x"),
        name="some.task", id="abc",
    )
    assert captured["state"] == "UNREGISTERED"
    assert isinstance(captured["args_json"], dict)
    assert "_raw_b64" in captured["args_json"]


def test_on_task_failure_classifies_timeout(monkeypatch):
    """SoftTimeLimitExceeded → state=TIMEOUT；其他异常 → FAILURE。"""
    from celery.exceptions import SoftTimeLimitExceeded

    captured: dict = {}
    monkeypatch.setattr(celery_failures, "_write_failure", lambda **f: captured.update(f))

    fake_sender = MagicMock()
    fake_sender.name = "app.x.y.foo"
    fake_sender.request.retries = 2

    celery_failures._on_task_failure(
        sender=fake_sender,
        task_id="t1",
        exception=SoftTimeLimitExceeded("time up"),
        args=("kb-uuid", "other"),
        kwargs={"flag": True},
        einfo="traceback string here",
    )
    assert captured["state"] == "TIMEOUT"
    assert captured["retries"] == 2
    assert "SoftTimeLimitExceeded" in captured["exception"]


def test_on_task_failure_state_failure(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(celery_failures, "_write_failure", lambda **f: captured.update(f))

    fake_sender = MagicMock()
    fake_sender.name = "app.x.foo"
    fake_sender.request.retries = 0

    celery_failures._on_task_failure(
        sender=fake_sender, task_id="t2",
        exception=ValueError("boom"), args=(), kwargs={}, einfo="trace",
    )
    assert captured["state"] == "FAILURE"
    assert "ValueError: boom" in captured["exception"]


def test_write_failure_silent_on_db_error(monkeypatch):
    """DB 写入抛异常时 handler 不应再抛出，避免无限循环。"""
    class _BrokenSession:
        def __enter__(self): raise ConnectionError("db down")
        def __exit__(self, *a): return False

    monkeypatch.setattr(celery_failures, "Session", lambda _: _BrokenSession())
    monkeypatch.setattr(celery_failures, "_get_engine", lambda: None)

    # Should not raise
    celery_failures._write_failure(task_name="x", state="FAILURE")


def test_task_failure_router_imports():
    """Smoke test：router 文件能 import，endpoint 已注册。"""
    from app.system.task_failures_router import router
    paths = [r.path for r in router.routes]
    assert "/system/celery/failures" in paths
    assert "/system/celery/failures/pending/count" in paths
    assert "/system/celery/failures/{failure_id}/retry" in paths
    assert "/system/celery/failures/{failure_id}/resolve" in paths


def test_cleanup_task_registered():
    """beat schedule 入口 + task 注册。"""
    from app.core.celery import celery_app
    celery_app.loader.import_default_modules()
    celery_app.finalize()
    assert "app.system.tasks.task_failure_cleanup" in celery_app.tasks
    assert "task-failure-cleanup" in celery_app.conf.beat_schedule
