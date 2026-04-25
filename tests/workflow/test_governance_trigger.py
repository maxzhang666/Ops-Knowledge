"""Plan 27 M6 — governance_trigger 匹配逻辑纯函数测试。"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.workflow.governance_trigger import TRIGGER_TYPE, _matches


@dataclass
class _WF:
    """minimal stand-in for ORM Workflow；只暴露 _matches 读到的字段。"""
    graph_data: dict
    trigger_type: str = TRIGGER_TYPE
    status: str = "published"


def test_matches_empty_cfg_accepts_any():
    wf = _WF(graph_data={"trigger_config": {}})
    assert _matches(wf, kind="stale_docs", kb_id="kb-1", severity="warning")


def test_matches_kind_whitelist():
    wf = _WF(graph_data={"trigger_config": {"kinds": ["stale_docs"]}})
    assert _matches(wf, kind="stale_docs", kb_id="kb", severity="warning")
    assert not _matches(wf, kind="redundancy", kb_id="kb", severity="warning")


def test_matches_kb_whitelist():
    kb_id = str(uuid.uuid4())
    wf = _WF(graph_data={"trigger_config": {"kb_ids": [kb_id]}})
    assert _matches(wf, kind="stale_docs", kb_id=kb_id, severity="warning")
    assert not _matches(
        wf, kind="stale_docs", kb_id=str(uuid.uuid4()), severity="warning",
    )


def test_matches_severity_whitelist():
    wf = _WF(graph_data={"trigger_config": {"severities": ["critical"]}})
    assert _matches(wf, kind="stale_docs", kb_id="kb", severity="critical")
    assert not _matches(wf, kind="stale_docs", kb_id="kb", severity="info")


def test_matches_combined_all_must_pass():
    wf = _WF(graph_data={
        "trigger_config": {
            "kinds": ["redundancy"],
            "severities": ["warning", "critical"],
        }
    })
    assert _matches(wf, kind="redundancy", kb_id="kb", severity="warning")
    assert not _matches(wf, kind="redundancy", kb_id="kb", severity="info")
    assert not _matches(wf, kind="knowledge_gap", kb_id="kb", severity="warning")


def test_matches_missing_trigger_config_accepts_any():
    wf = _WF(graph_data={})
    assert _matches(wf, kind="anything", kb_id="any", severity="any")


def test_matches_trigger_config_not_dict_rejects():
    # 防御：误写成非 dict 时不 crash 而返回 False
    wf = _WF(graph_data={"trigger_config": ["wrong"]})
    assert not _matches(wf, kind="stale_docs", kb_id="kb", severity="warning")


def test_matches_kb_ids_string_coercion():
    # UUID / str 都应能命中
    kb_id_uuid = uuid.uuid4()
    wf = _WF(graph_data={"trigger_config": {"kb_ids": [str(kb_id_uuid)]}})
    assert _matches(wf, kind="stale_docs", kb_id=str(kb_id_uuid), severity="warning")
