import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

# alembic runs env.py in an isolated process; pyproject.toml's pytest
# `pythonpath` doesn't apply here. Put the repo root on sys.path so that
# the `app.*` imports below resolve regardless of how alembic was invoked.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.core.models import Base
from app.auth.models import User  # noqa: F401
from app.department.models import Department, UserDepartment, DepartmentResource  # noqa: F401
from app.system.models import ApiKey, Notification, SystemSettings  # noqa: F401
from app.model.models import ModelProvider  # noqa: F401
from app.knowledge.models import KnowledgeBase, Folder, Document, Chunk  # noqa: F401
from app.agent.models import Agent  # noqa: F401
from app.chat.models import Conversation, Message  # noqa: F401
from app.workflow.models import Workflow, WorkflowVersion, WorkflowExecution, NodeExecution, WorkflowTemplate  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
