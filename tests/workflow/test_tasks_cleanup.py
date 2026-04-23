"""plan 20 Task 5 cleanup — pure-Python tests for the retention helper."""
from app.workflow.tasks import _retention_days


def test_default_retention_when_missing():
    assert _retention_days({}) == 30
    assert _retention_days({"workflow": {}}) == 30


def test_custom_retention_from_settings():
    assert _retention_days({"workflow": {"retention_days": 14}}) == 14


def test_bogus_retention_falls_back_to_default():
    assert _retention_days({"workflow": {"retention_days": "NaN"}}) == 30
    assert _retention_days({"workflow": {"retention_days": None}}) == 30


def test_clamps_below_one():
    assert _retention_days({"workflow": {"retention_days": 0}}) == 1
    assert _retention_days({"workflow": {"retention_days": -5}}) == 1
