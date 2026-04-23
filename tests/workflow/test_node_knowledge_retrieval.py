import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.workflow.nodes._knowledge_retrieval import KnowledgeRetrievalNode
from app.workflow.nodes.base import NodeContext


def _ctx(kb_ids: list[str] | None = None, query: str = "q", **extras) -> NodeContext:
    config: dict = {"knowledge_base_ids": kb_ids or [str(uuid.uuid4())]}
    config.update(extras)
    return NodeContext(
        node_id="kr", node_type="knowledge-retrieval",
        inputs={"query": query}, config=config,
    )


@pytest.mark.asyncio
async def test_validate_rejects_missing_kb():
    node = KnowledgeRetrievalNode()
    ctx = NodeContext(
        node_id="kr", node_type="knowledge-retrieval",
        inputs={"query": "q"}, config={"knowledge_base_ids": []},
    )
    with pytest.raises(ValueError, match="at least one"):
        await node.validate(ctx)


@pytest.mark.asyncio
async def test_validate_rejects_missing_query():
    node = KnowledgeRetrievalNode()
    ctx = NodeContext(
        node_id="kr", node_type="knowledge-retrieval",
        inputs={}, config={"knowledge_base_ids": [str(uuid.uuid4())]},
    )
    with pytest.raises(ValueError, match="missing 'query'"):
        await node.validate(ctx)


@pytest.mark.asyncio
async def test_execute_delegates_to_facade():
    """Post-plan-21 the node goes through workflow_to_knowledge.retrieve.
    Patch the facade directly."""
    node = KnowledgeRetrievalNode()

    class _Sess:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    fake_chunks = [
        {"id": "c1", "content": "hi", "score": 0.9, "document_id": "d1",
         "document_title": "doc1", "folder_id": None, "level": 0, "source_kb_id": None},
    ]
    with patch("app.workflow.nodes._knowledge_retrieval.async_session", return_value=_Sess()), \
         patch("app.workflow.nodes._knowledge_retrieval.wtok.retrieve",
               AsyncMock(return_value=fake_chunks)):
        res = await node.execute(_ctx(score_threshold=0.0))
    assert res.outputs["chunks"] == fake_chunks
    assert res.outputs["is_empty"] is False


@pytest.mark.asyncio
async def test_empty_results_flag():
    node = KnowledgeRetrievalNode()

    class _Sess:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    with patch("app.workflow.nodes._knowledge_retrieval.async_session", return_value=_Sess()), \
         patch("app.workflow.nodes._knowledge_retrieval.wtok.retrieve",
               AsyncMock(return_value=[])):
        res = await node.execute(_ctx())
    assert res.outputs["chunks"] == []
    assert res.outputs["is_empty"] is True
