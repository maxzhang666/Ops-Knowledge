import uuid
from typing import Any

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy import Select


class PaginationParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    ):
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int


def apply_dept_scope(
    stmt: Select,
    accessible_ids: list[uuid.UUID],
    user_id: uuid.UUID,
    id_column,
    created_by_column,
) -> Select:
    """Filter query to show only resources the user created or has department access to."""
    from sqlalchemy import or_
    return stmt.where(
        or_(
            created_by_column == user_id,
            id_column.in_(accessible_ids),
        )
    )
