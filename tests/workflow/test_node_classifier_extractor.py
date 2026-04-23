import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workflow.nodes._parameter_extractor import ParameterExtractorNode
from app.workflow.nodes._question_classifier import QuestionClassifierNode
from app.workflow.nodes.base import NodeContext


class _Sess:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


def _qc_ctx(query: str = "q"):
    return NodeContext(
        node_id="qc", node_type="question-classifier",
        inputs={"query": query},
        config={
            "model_provider_id": str(uuid.uuid4()),
            "model_name": "m",
            "categories": [
                {"id": "a", "name": "A"},
                {"id": "b", "name": "B"},
            ],
        },
    )


@pytest.mark.asyncio
async def test_classifier_happy_path():
    svc = MagicMock()
    svc.chat = AsyncMock(return_value={
        "choices": [{"message": {"content": '{"category_id": "b"}'}}],
    })
    with patch("app.workflow.nodes._question_classifier.async_session", return_value=_Sess()), \
         patch("app.workflow.nodes._question_classifier.ModelService", return_value=svc):
        res = await QuestionClassifierNode().execute(_qc_ctx())
    assert res.outputs == {"category_id": "b", "category_name": "B"}
    assert res.branch == "b"


@pytest.mark.asyncio
async def test_classifier_substring_fallback():
    svc = MagicMock()
    svc.chat = AsyncMock(return_value={
        "choices": [{"message": {"content": 'The answer is a.'}}],
    })
    with patch("app.workflow.nodes._question_classifier.async_session", return_value=_Sess()), \
         patch("app.workflow.nodes._question_classifier.ModelService", return_value=svc):
        res = await QuestionClassifierNode().execute(_qc_ctx())
    assert res.outputs["category_id"] == "a"


@pytest.mark.asyncio
async def test_classifier_invalid_output_raises():
    svc = MagicMock()
    # Use text that doesn't contain any valid category id as a substring either.
    svc.chat = AsyncMock(return_value={
        "choices": [{"message": {"content": 'xxx yyy zzz'}}],
    })
    with patch("app.workflow.nodes._question_classifier.async_session", return_value=_Sess()), \
         patch("app.workflow.nodes._question_classifier.ModelService", return_value=svc):
        with pytest.raises(RuntimeError, match="did not match"):
            await QuestionClassifierNode().execute(_qc_ctx())


def _pe_ctx(text: str = "my age is 30"):
    return NodeContext(
        node_id="pe", node_type="parameter-extractor",
        inputs={"text": text},
        config={
            "model_provider_id": str(uuid.uuid4()),
            "model_name": "m",
            "parameters": [
                {"name": "age", "type": "number", "required": True},
                {"name": "name", "type": "string"},
            ],
        },
    )


@pytest.mark.asyncio
async def test_extractor_happy_path_with_coercion():
    svc = MagicMock()
    svc.chat = AsyncMock(return_value={
        "choices": [{"message": {"content": '{"age": "30", "name": "Max"}'}}],
    })
    with patch("app.workflow.nodes._parameter_extractor.async_session", return_value=_Sess()), \
         patch("app.workflow.nodes._parameter_extractor.ModelService", return_value=svc):
        res = await ParameterExtractorNode().execute(_pe_ctx())
    assert res.outputs == {"age": 30, "name": "Max"}


@pytest.mark.asyncio
async def test_extractor_required_missing_raises():
    svc = MagicMock()
    svc.chat = AsyncMock(return_value={
        "choices": [{"message": {"content": '{"name": "only"}'}}],
    })
    with patch("app.workflow.nodes._parameter_extractor.async_session", return_value=_Sess()), \
         patch("app.workflow.nodes._parameter_extractor.ModelService", return_value=svc):
        with pytest.raises(RuntimeError, match="missing required"):
            await ParameterExtractorNode().execute(_pe_ctx())


@pytest.mark.asyncio
async def test_extractor_invalid_json_raises():
    svc = MagicMock()
    svc.chat = AsyncMock(return_value={
        "choices": [{"message": {"content": "not json at all"}}],
    })
    with patch("app.workflow.nodes._parameter_extractor.async_session", return_value=_Sess()), \
         patch("app.workflow.nodes._parameter_extractor.ModelService", return_value=svc):
        with pytest.raises(RuntimeError, match="invalid JSON"):
            await ParameterExtractorNode().execute(_pe_ctx())
