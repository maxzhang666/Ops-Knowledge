from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import get_db
from app.core.models import Base
from app.main import app

TEST_DATABASE_URL = settings.DATABASE_URL.replace("/ops_knowledge", "/ops_knowledge_test")

engine_test = create_async_engine(TEST_DATABASE_URL, echo=False)
async_session_test = async_sessionmaker(engine_test, class_=AsyncSession, expire_on_commit=False)


# 2026-05-14: 之前自定义的 session-scope `event_loop` fixture 与 pytest-asyncio 0.21+
# 的事件循环管理冲突——首个测试关闭 loop 后续用例报 "no current event loop"，
# 导致 evaluation_judges / query_rewriter_v2 / raptor_algorithm 等纯单元测试在
# 全量 run 时 24 个失败（单独跑全过）。删自定义 fixture 改用 pytest-asyncio 默认
# function-scope loop；asyncio_mode=auto 已在 pyproject.toml 配好。
#
# 同步把 setup_db 改成 autouse=False —— 真单元测试（不碰 DB / API）不再被强制
# 创建 + 销毁 PG schema。需要 DB 的测试通过 db_session / client 依赖链触发。


@pytest.fixture
async def setup_db():
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session(setup_db) -> AsyncGenerator[AsyncSession, None]:
    async with async_session_test() as session:
        yield session


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
