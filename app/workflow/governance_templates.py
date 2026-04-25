"""Built-in Governance Workflow templates (Plan 27 M3).

Seed 3 个开箱即用模板 —— 系统启动时 idempotent 创建（按 name 唯一）：

  1. stale-doc-review          Start → Human Approval → Archive → Notify
  2. redundancy-merge-approval Start → Human Approval → Merge → Notify
  3. knowledge-gap-assign      Start → Notify

模板的 ``trigger_config`` 字段定义了 governance_event 触发时该模板订阅哪类告警。
用户从模板创建 Workflow 后，可在编辑器里调整 kb_ids / severities 范围。
"""
from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.workflow.models import WorkflowTemplate

logger = structlog.get_logger(__name__)


def _graph_stale_doc_review() -> dict:
    return {
        "dsl_version": "1.0",
        "trigger_config": {"kinds": ["stale_docs"]},
        "workflow_variables": [
            {"name": "document_id", "type": "string", "default": ""},
            {"name": "kb_id", "type": "string", "default": ""},
        ],
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {}},
                {
                    "id": "approval",
                    "type": "human_approval",
                    "data": {
                        "prompt": "文档已过期 — 请确认是否归档",
                        "approvers": [],
                    },
                },
                {
                    "id": "archive",
                    "type": "kb_archive_document",
                    "data": {
                        "inputs": {
                            "document_id": ["__trigger__", "document_id"],
                            "archive": True,
                        },
                    },
                },
                {
                    "id": "notify",
                    "type": "kb_notify_owner",
                    "data": {
                        "inputs": {
                            "resource_type": "document",
                            "resource_id": ["__trigger__", "document_id"],
                            "title": "过期文档已归档",
                            "content": "文档治理 Workflow 完成自动归档，如有疑问请联系管理员。",
                        },
                    },
                },
            ],
            "edges": [
                {"source": "start", "target": "approval"},
                {"source": "approval", "target": "archive"},
                {"source": "archive", "target": "notify"},
            ],
        },
    }


def _graph_redundancy_merge_approval() -> dict:
    return {
        "dsl_version": "1.0",
        "trigger_config": {"kinds": ["redundancy"]},
        "workflow_variables": [
            {"name": "chunk_a_id", "type": "string", "default": ""},
            {"name": "chunk_b_id", "type": "string", "default": ""},
        ],
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {}},
                {
                    "id": "approval",
                    "type": "human_approval",
                    "data": {
                        "prompt": "检测到高相似切片对 — 请选择保留方 (a/b/both)",
                    },
                },
                {
                    "id": "merge",
                    "type": "kb_merge_chunks",
                    "data": {
                        "inputs": {
                            "chunk_a_id": ["__trigger__", "chunk_a_id"],
                            "chunk_b_id": ["__trigger__", "chunk_b_id"],
                            "keep": ["approval", "decision"],
                        },
                    },
                },
            ],
            "edges": [
                {"source": "start", "target": "approval"},
                {"source": "approval", "target": "merge"},
            ],
        },
    }


def _graph_knowledge_gap_assign() -> dict:
    return {
        "dsl_version": "1.0",
        "trigger_config": {"kinds": ["knowledge_gap"]},
        "workflow_variables": [
            {"name": "kb_id", "type": "string", "default": ""},
        ],
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {}},
                {
                    "id": "notify",
                    "type": "kb_notify_owner",
                    "data": {
                        "inputs": {
                            "resource_type": "kb",
                            "resource_id": ["__trigger__", "kb_id"],
                            "title": "检测到知识盲区",
                            "content": "用户检索中出现多次无结果查询，建议补充对应主题的知识内容。",
                        },
                    },
                },
            ],
            "edges": [
                {"source": "start", "target": "notify"},
            ],
        },
    }


_TEMPLATES: list[tuple[str, str, dict]] = [
    (
        "stale-doc-review",
        "过期文档审批归档 — Human Approval → Archive → Notify",
        _graph_stale_doc_review(),
    ),
    (
        "redundancy-merge-approval",
        "冗余切片合并审批 — Human Approval → Merge",
        _graph_redundancy_merge_approval(),
    ),
    (
        "knowledge-gap-assign",
        "知识盲区派单通知 — 检索无结果高频话题派给 KB 负责人",
        _graph_knowledge_gap_assign(),
    ),
]


async def seed_governance_templates(db: AsyncSession) -> int:
    """按 name 幂等创建 builtin 模板。返回新增条数。"""
    new_count = 0
    for name, description, graph in _TEMPLATES:
        existing = (await db.execute(
            select(WorkflowTemplate).where(WorkflowTemplate.name == name)
        )).scalar_one_or_none()
        if existing is not None:
            # 更新 graph —— 新版本覆盖，保持 builtin 模板随代码升级
            if existing.is_builtin:
                existing.graph_data = graph
                existing.description = description
            continue
        db.add(WorkflowTemplate(
            id=uuid.uuid4(),
            name=name,
            description=description,
            category="governance",
            graph_data=graph,
            is_builtin=True,
        ))
        new_count += 1
    await db.commit()
    logger.info("governance_templates_seeded", new=new_count)
    return new_count
