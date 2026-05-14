"""#2 修复 — Milvus 写操作 retry 行为单测。

不连真实 Milvus；mock MilvusClient.delete 验证 _retry_with_backoff 调用语义：
- 暂时性故障自愈
- 永久性故障最终抛
- 一次成功不退避
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.knowledge.milvus.service import MilvusService


def _make_svc(mock_client: MagicMock) -> MilvusService:
    """构造一个绕过真实连接的 MilvusService。"""
    svc = MilvusService.__new__(MilvusService)  # 跳过 __init__
    svc._client = mock_client
    return svc


def test_delete_by_filter_succeeds_first_try():
    """一次成功 → 不重试，无延迟。"""
    client = MagicMock()
    client.delete.return_value = {"delete_count": 1}
    svc = _make_svc(client)

    with patch("time.sleep") as mock_sleep:
        result = svc.delete_by_filter("coll", 'id == "x"')

    assert result == {"delete_count": 1}
    assert client.delete.call_count == 1
    mock_sleep.assert_not_called()


def test_delete_by_filter_recovers_after_transient_failures():
    """前 2 次失败 + 第 3 次成功 → 自愈，sleep 2 次（指数退避）。"""
    client = MagicMock()
    client.delete.side_effect = [
        ConnectionError("milvus down"),
        ConnectionError("milvus down"),
        {"delete_count": 1},
    ]
    svc = _make_svc(client)

    with patch("time.sleep") as mock_sleep:
        result = svc.delete_by_filter("coll", 'id == "x"')

    assert result == {"delete_count": 1}
    assert client.delete.call_count == 3
    # base_delay=0.4，i=0 → 0.4，i=1 → 0.8
    assert mock_sleep.call_args_list[0].args[0] == pytest.approx(0.4)
    assert mock_sleep.call_args_list[1].args[0] == pytest.approx(0.8)


def test_delete_by_filter_raises_after_all_attempts_fail():
    """3 次全失败 → 抛最后一次异常（不吞）。"""
    client = MagicMock()
    err = ConnectionError("milvus permanently down")
    client.delete.side_effect = [err, err, err]
    svc = _make_svc(client)

    with patch("time.sleep"):
        with pytest.raises(ConnectionError, match="permanently down"):
            svc.delete_by_filter("coll", 'id == "x"')

    assert client.delete.call_count == 3


def test_delete_by_ids_retries_same_pattern():
    """delete_by_ids 走同一个 _retry_with_backoff 包装。"""
    client = MagicMock()
    client.delete.side_effect = [TimeoutError("slow"), {"delete_count": 2}]
    svc = _make_svc(client)

    with patch("time.sleep"):
        result = svc.delete_by_ids("coll", ["a", "b"])

    assert result == {"delete_count": 2}
    assert client.delete.call_count == 2
