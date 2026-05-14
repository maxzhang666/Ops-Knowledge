"""Celery 失败任务捕获 — 三类失败统一写入 task_failures 表。

监听 signal：
- task_failure: task 抛异常 / SoftTimeLimitExceeded（按异常类型分 state）
- task_unknown: worker 未注册 task name（celery 默认 discard，本表是唯一痕迹）

handler 用独立 sync session（不污染 task 自己的 session）；写入失败用
try/except 全包并 structlog ERROR，不二次重试避免无限循环。

模块需要被 worker 进程 import 一次以触发 signal connect；通过 celery.py
顶部 import + include=[] 双保险注册。
"""
from __future__ import annotations

import base64
import json
import uuid

import structlog
from celery.signals import task_failure, task_unknown
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.system.models import TaskFailure

logger = structlog.get_logger(__name__)

SYNC_DB_URL = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(SYNC_DB_URL, pool_pre_ping=True)
    return _engine


def _json_safe(obj):
    """JSON-encode 兼容 UUID/datetime/Decimal 等非原生类型 → 序列化后再
    反序列化为纯原生结构，便于 JSONB 写入。

    宽口径 catch：default=str 可能触发对象自身的 __str__/__repr__ 抛任意异常，
    handler 不应因此中断；记录失败时丢失 args/kwargs 比丢整条 failure 记录好。"""
    try:
        return json.loads(json.dumps(obj, default=str))
    except Exception:
        return None


def _coerce_uuid(v):
    try:
        return uuid.UUID(str(v))
    except (ValueError, TypeError, AttributeError):
        return None


def _extract_kb_id(args, kwargs):
    """启发式从 task 参数提取 kb_id：多数 unit 类 task 第一参数或 kwarg['kb_id']。"""
    try:
        if isinstance(kwargs, dict):
            v = kwargs.get("kb_id")
            if v:
                u = _coerce_uuid(v)
                if u:
                    return u
        if isinstance(args, (list, tuple)) and len(args) >= 1:
            u = _coerce_uuid(args[0])
            if u:
                return u
    except Exception:
        pass
    return None


def _write_failure(**fields):
    """独立 session 写表；任何异常都吞掉 + structlog ERROR（不二次重试）。"""
    try:
        with Session(_get_engine()) as session:
            tf = TaskFailure(**fields)
            session.add(tf)
            session.commit()
    except Exception:
        logger.error(
            "task_failure_record_write_failed", exc_info=True,
            task_name=fields.get("task_name"), state=fields.get("state"),
        )


@task_failure.connect
def _on_task_failure(sender=None, task_id=None, exception=None, args=None,
                     kwargs=None, traceback=None, einfo=None, **_kw):
    """task 抛异常 retries 用尽 / SoftTimeLimitExceeded / 单次 fatal 都走这里。"""
    from celery.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded

    if isinstance(exception, (SoftTimeLimitExceeded, TimeLimitExceeded)):
        state = "TIMEOUT"
    else:
        state = "FAILURE"

    task_name = getattr(sender, "name", None) or "unknown"
    retries = 0
    try:
        if sender is not None:
            retries = int(getattr(sender.request, "retries", 0) or 0)
    except Exception:
        pass

    _write_failure(
        task_id=str(task_id) if task_id else None,
        task_name=task_name,
        args_json=_json_safe(list(args)) if args else None,
        kwargs_json=_json_safe(kwargs) if kwargs else None,
        state=state,
        exception=f"{type(exception).__name__}: {exception}" if exception else None,
        traceback=str(einfo) if einfo else (str(traceback) if traceback else None),
        retries=retries,
        kb_id=_extract_kb_id(args, kwargs),
    )


@task_unknown.connect
def _on_task_unknown(sender=None, message=None, exc=None, name=None,
                     id=None, **_kw):
    """worker 未注册该 task；celery 默认 discard 后无任何痕迹，本表唯一兜底。

    message.body 是 celery protocol v2 的 raw JSON: `[args, kwargs, embed]`。
    JSON 解析失败时存 base64 原始字节供调试。"""
    args_json = None
    kwargs_json = None
    raw_b64 = None
    try:
        body = message.body if message is not None else None
        if isinstance(body, bytes):
            try:
                parsed = json.loads(body.decode("utf-8"))
                if isinstance(parsed, list) and len(parsed) >= 2:
                    args_json = _json_safe(parsed[0])
                    kwargs_json = _json_safe(parsed[1])
            except (UnicodeDecodeError, ValueError):
                raw_b64 = base64.b64encode(body).decode("ascii")
    except Exception:
        pass

    final_args = (
        args_json if args_json is not None
        else ({"_raw_b64": raw_b64} if raw_b64 else None)
    )
    _write_failure(
        task_id=str(id) if id else None,
        task_name=name or "unknown",
        args_json=final_args,
        kwargs_json=kwargs_json,
        state="UNREGISTERED",
        exception=(
            f"{type(exc).__name__}: {exc}" if exc
            else "task not registered in this worker"
        ),
        traceback=None,
        retries=0,
        kb_id=_extract_kb_id(
            args_json if isinstance(args_json, list) else [],
            kwargs_json if isinstance(kwargs_json, dict) else {},
        ),
    )
