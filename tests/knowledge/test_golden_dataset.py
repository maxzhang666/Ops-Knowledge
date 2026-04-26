"""Plan 38 M4 — Golden Dataset aggregation pure-function tests."""
from __future__ import annotations

from app.knowledge.evaluation.golden_service import aggregate_metrics


def test_empty_input_returns_empty_dict():
    assert aggregate_metrics([]) == {}


def test_single_question_passthrough():
    out = aggregate_metrics([{"faithfulness": 0.8, "answer_relevancy": 0.9}])
    assert out["faithfulness"] == 0.8
    assert out["answer_relevancy"] == 0.9


def test_average_across_questions():
    out = aggregate_metrics([
        {"faithfulness": 0.8, "answer_relevancy": 0.9},
        {"faithfulness": 0.6, "answer_relevancy": 0.7},
    ])
    assert abs(out["faithfulness"] - 0.7) < 1e-6
    assert abs(out["answer_relevancy"] - 0.8) < 1e-6


def test_missing_metrics_in_some_questions_handled():
    out = aggregate_metrics([
        {"faithfulness": 0.8, "answer_relevancy": 0.9},
        {"faithfulness": 0.6},  # answer_relevancy missing
    ])
    assert abs(out["faithfulness"] - 0.7) < 1e-6
    # answer_relevancy 仅一题给值，平均=0.9
    assert out["answer_relevancy"] == 0.9


def test_none_values_excluded_from_average():
    out = aggregate_metrics([
        {"faithfulness": 0.8},
        {"faithfulness": None},
        {"faithfulness": 0.6},
    ])
    assert abs(out["faithfulness"] - 0.7) < 1e-6


def test_all_none_for_metric_excluded():
    out = aggregate_metrics([
        {"a": None},
        {"a": None},
    ])
    assert "a" not in out


def test_rounding_to_4_decimals():
    out = aggregate_metrics([
        {"x": 0.1},
        {"x": 0.2},
        {"x": 0.3},
    ])
    # 0.2 整 — 验证四舍五入
    assert out["x"] == 0.2
