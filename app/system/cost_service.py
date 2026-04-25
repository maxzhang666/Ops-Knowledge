"""Cost aggregation service (Plan 28 M1).

CostRecord 已有完整 token + cost 数据；本 service 提供:
  * summary       —— 时间窗内 total token + cost + 调用数
  * timeline      —— 按天 trim 的 cost 时序，用于 sparkline
  * top_n_groups  —— 按 user / agent / provider / model 维度的 Top N

设计：
  - 所有查询带时间窗参数（默认 30 天）；窗口外数据 (cost_records.created_at < cutoff) 被丢弃
  - 维度切换通过显式 by 参数（避免动态字段拼接）
  - cost 单位为 USD；前端按需换算
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.model.models import CostRecord, ModelProvider

GroupBy = Literal["user", "provider", "model", "call_type"]


@dataclass
class CostSummary:
    total_cost: float
    total_input_tokens: int
    total_output_tokens: int
    call_count: int
    window_days: int


@dataclass
class TimelinePoint:
    date: str          # YYYY-MM-DD
    cost: float
    tokens: int
    calls: int


@dataclass
class TopGroupItem:
    key: str           # 主键 id 或 model_name
    label: str         # 展示用名称
    cost: float
    tokens: int
    calls: int


class CostService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def summary(self, *, window_days: int = 30) -> CostSummary:
        cutoff = _cutoff(window_days)
        row = (await self.db.execute(
            select(
                func.coalesce(func.sum(CostRecord.cost), 0.0),
                func.coalesce(func.sum(CostRecord.input_tokens), 0),
                func.coalesce(func.sum(CostRecord.output_tokens), 0),
                func.count(CostRecord.id),
            ).where(CostRecord.created_at >= cutoff)
        )).one()
        return CostSummary(
            total_cost=float(row[0] or 0.0),
            total_input_tokens=int(row[1] or 0),
            total_output_tokens=int(row[2] or 0),
            call_count=int(row[3] or 0),
            window_days=window_days,
        )

    async def timeline(self, *, window_days: int = 7) -> list[TimelinePoint]:
        cutoff = _cutoff(window_days)
        rows = (await self.db.execute(
            select(
                func.date_trunc("day", CostRecord.created_at).label("day"),
                func.sum(CostRecord.cost),
                func.sum(CostRecord.input_tokens + CostRecord.output_tokens),
                func.count(CostRecord.id),
            )
            .where(CostRecord.created_at >= cutoff)
            .group_by("day")
            .order_by("day")
        )).all()
        observed = {
            r[0].date().isoformat(): (float(r[1] or 0.0), int(r[2] or 0), int(r[3] or 0))
            for r in rows
        }
        # Fill 0 for days without data so frontend always shows full window
        now = datetime.now(timezone.utc)
        days = [(now - timedelta(days=i)).date().isoformat() for i in range(window_days - 1, -1, -1)]
        return [
            TimelinePoint(
                date=d,
                cost=observed.get(d, (0.0, 0, 0))[0],
                tokens=observed.get(d, (0.0, 0, 0))[1],
                calls=observed.get(d, (0.0, 0, 0))[2],
            )
            for d in days
        ]

    async def top_groups(
        self, *, by: GroupBy, window_days: int = 30, limit: int = 10,
    ) -> list[TopGroupItem]:
        cutoff = _cutoff(window_days)
        if by == "provider":
            rows = (await self.db.execute(
                select(
                    CostRecord.provider_id,
                    ModelProvider.name,
                    func.sum(CostRecord.cost),
                    func.sum(CostRecord.input_tokens + CostRecord.output_tokens),
                    func.count(CostRecord.id),
                )
                .join(ModelProvider, ModelProvider.id == CostRecord.provider_id)
                .where(CostRecord.created_at >= cutoff)
                .group_by(CostRecord.provider_id, ModelProvider.name)
                .order_by(func.sum(CostRecord.cost).desc())
                .limit(limit)
            )).all()
            return [
                TopGroupItem(
                    key=str(r[0]), label=r[1] or str(r[0]),
                    cost=float(r[2] or 0.0), tokens=int(r[3] or 0), calls=int(r[4] or 0),
                )
                for r in rows
            ]
        if by == "model":
            rows = (await self.db.execute(
                select(
                    CostRecord.model_name,
                    func.sum(CostRecord.cost),
                    func.sum(CostRecord.input_tokens + CostRecord.output_tokens),
                    func.count(CostRecord.id),
                )
                .where(CostRecord.created_at >= cutoff)
                .group_by(CostRecord.model_name)
                .order_by(func.sum(CostRecord.cost).desc())
                .limit(limit)
            )).all()
            return [
                TopGroupItem(
                    key=r[0], label=r[0],
                    cost=float(r[1] or 0.0), tokens=int(r[2] or 0), calls=int(r[3] or 0),
                )
                for r in rows
            ]
        if by == "user":
            rows = (await self.db.execute(
                select(
                    CostRecord.user_id,
                    User.username,
                    func.sum(CostRecord.cost),
                    func.sum(CostRecord.input_tokens + CostRecord.output_tokens),
                    func.count(CostRecord.id),
                )
                .outerjoin(User, User.id == CostRecord.user_id)
                .where(
                    CostRecord.created_at >= cutoff,
                    CostRecord.user_id.isnot(None),
                )
                .group_by(CostRecord.user_id, User.username)
                .order_by(func.sum(CostRecord.cost).desc())
                .limit(limit)
            )).all()
            return [
                TopGroupItem(
                    key=str(r[0]) if r[0] else "(anonymous)",
                    label=r[1] or "(已删除用户)",
                    cost=float(r[2] or 0.0), tokens=int(r[3] or 0), calls=int(r[4] or 0),
                )
                for r in rows
            ]
        if by == "call_type":
            rows = (await self.db.execute(
                select(
                    CostRecord.call_type,
                    func.sum(CostRecord.cost),
                    func.sum(CostRecord.input_tokens + CostRecord.output_tokens),
                    func.count(CostRecord.id),
                )
                .where(CostRecord.created_at >= cutoff)
                .group_by(CostRecord.call_type)
                .order_by(func.sum(CostRecord.cost).desc())
            )).all()
            return [
                TopGroupItem(
                    key=r[0], label=r[0],
                    cost=float(r[1] or 0.0), tokens=int(r[2] or 0), calls=int(r[3] or 0),
                )
                for r in rows
            ]
        raise ValueError(f"Unknown groupby: {by}")


def _cutoff(window_days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=max(1, window_days))
