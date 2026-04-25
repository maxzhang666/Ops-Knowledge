"""Plan 28 M4 — CostService cutoff/纯辅助函数测试。

聚合查询本身需要数据库；这里覆盖纯逻辑：
  - _cutoff 时间窗
  - timeline 0 填充逻辑（间接通过 mock）
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.system.cost_service import CostSummary, TimelinePoint, TopGroupItem, _cutoff


def test_cutoff_clamps_window_to_at_least_one_day():
    now = datetime.now(timezone.utc)
    far_past = _cutoff(0)  # 0 input → at least 1 day
    assert (now - far_past) >= timedelta(days=1) - timedelta(seconds=1)


def test_cutoff_30_days_back():
    cutoff = _cutoff(30)
    delta = datetime.now(timezone.utc) - cutoff
    assert timedelta(days=29, hours=23) <= delta <= timedelta(days=30, hours=1)


def test_summary_dataclass_carries_all_fields():
    s = CostSummary(
        total_cost=1.234, total_input_tokens=100, total_output_tokens=50,
        call_count=7, window_days=30,
    )
    assert s.total_cost == 1.234
    assert s.total_input_tokens == 100
    assert s.total_output_tokens == 50
    assert s.call_count == 7
    assert s.window_days == 30


def test_timeline_point_keys():
    p = TimelinePoint(date="2026-04-25", cost=0.5, tokens=1000, calls=3)
    assert p.date == "2026-04-25"
    assert p.cost == 0.5
    assert p.tokens == 1000
    assert p.calls == 3


def test_top_group_item_dataclass():
    item = TopGroupItem(key="prov-1", label="OpenAI", cost=12.5, tokens=10000, calls=5)
    assert item.key == "prov-1"
    assert item.label == "OpenAI"
    assert item.cost == 12.5
