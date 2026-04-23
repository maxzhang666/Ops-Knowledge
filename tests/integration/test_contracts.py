"""Signature stability — catches accidental API drift across plan landings.

If one of these asserts fails, a facade signature changed — review callers
and decide whether to rename / migrate / bump contract version before merging.
"""
import inspect

from app.integration import workflow_to_knowledge


def test_retrieve_signature_stable():
    sig = inspect.signature(workflow_to_knowledge.retrieve)
    params = list(sig.parameters)
    assert params == [
        "db", "query", "kb_ids", "top_k",
        "folder_ids", "score_threshold", "rewrite",
    ]


def test_retrieve_is_async():
    assert inspect.iscoroutinefunction(workflow_to_knowledge.retrieve)


def test_get_kb_summary_signature_stable():
    sig = inspect.signature(workflow_to_knowledge.get_kb_summary)
    assert list(sig.parameters) == ["db", "kb_id"]
