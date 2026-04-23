import pytest
from pydantic import ValidationError

from app.workflow.dsl import DSLValidationError, parse_dsl


def _graph(nodes, edges=None):
    return {
        "dsl_version": "1.0",
        "graph": {"nodes": nodes, "edges": edges or []},
        "workflow_variables": [],
    }


def test_empty_dsl_ok():
    parse_dsl(None)
    parse_dsl({"dsl_version": "1.0", "graph": {"nodes": [], "edges": []}, "workflow_variables": []})


def test_minimal_graph_ok():
    parse_dsl(_graph([
        {"id": "s", "type": "start", "data": {}},
        {"id": "a", "type": "answer", "data": {}},
    ], [{"source": "s", "target": "a"}]))


def test_duplicate_node_id_rejected():
    with pytest.raises(DSLValidationError, match="Duplicate"):
        parse_dsl(_graph([
            {"id": "n1", "type": "start", "data": {}},
            {"id": "n1", "type": "answer", "data": {}},
        ]))


def test_edge_reference_missing_node():
    with pytest.raises(DSLValidationError, match="not found"):
        parse_dsl(_graph(
            [{"id": "s", "type": "start", "data": {}}],
            [{"source": "s", "target": "missing"}],
        ))


def test_missing_start_rejected():
    with pytest.raises(DSLValidationError, match="start"):
        parse_dsl(_graph([{"id": "a", "type": "answer", "data": {}}]))


def test_multiple_start_rejected():
    with pytest.raises(DSLValidationError, match="Multiple"):
        parse_dsl(_graph([
            {"id": "s1", "type": "start", "data": {}},
            {"id": "s2", "type": "start", "data": {}},
        ]))


def test_cycle_rejected():
    with pytest.raises(DSLValidationError, match="cycle"):
        parse_dsl(_graph(
            [
                {"id": "s", "type": "start", "data": {}},
                {"id": "a", "type": "llm", "data": {}},
                {"id": "b", "type": "llm", "data": {}},
            ],
            [
                {"source": "s", "target": "a"},
                {"source": "a", "target": "b"},
                {"source": "b", "target": "a"},
            ],
        ))


def test_extra_root_field_rejected():
    bad = _graph([{"id": "s", "type": "start", "data": {}}])
    bad["extra_field"] = 1
    with pytest.raises(ValidationError):
        parse_dsl(bad)


def test_compound_node_sub_edge_reference_validated():
    with pytest.raises(DSLValidationError, match="unknown sub-node"):
        parse_dsl(_graph([
            {
                "id": "s", "type": "start", "data": {},
            },
            {
                "id": "it", "type": "iteration", "data": {},
                "blocks": [{"id": "inner", "type": "llm", "data": {}}],
                "block_edges": [{"source": "inner", "target": "does-not-exist"}],
            },
        ], [{"source": "s", "target": "it"}]))
