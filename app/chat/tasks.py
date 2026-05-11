import asyncio

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.chat.models import Conversation, Message
from app.core.celery import celery_app
from app.core.config import settings
from app.model.service import AgentModelNotConfigured, ModelService

logger = structlog.get_logger(__name__)

TITLE_SYSTEM = (
    "Generate a short title (max 30 characters) for a conversation that starts with "
    "the following message. Output ONLY the title, no quotes or punctuation."
)

SUMMARY_SYSTEM = (
    "Summarize the following conversation in 2-3 sentences, capturing the key topics "
    "and conclusions. Output ONLY the summary."
)


def _run_async(coro):
    """Run an async coroutine in a new event loop (for Celery sync tasks)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.chat.tasks.generate_title", bind=True, max_retries=2)
def generate_title(self, conversation_id: str, first_message: str):
    """Generate a short title for a conversation based on its first message."""

    async def _run():
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with session_factory() as db:
                model_svc = ModelService(db)

                # Get agent's model config from conversation
                conv = await db.get(Conversation, conversation_id)
                if conv is None:
                    logger.warning("title_gen_conv_not_found", conversation_id=conversation_id)
                    return

                from app.agent.models import Agent
                agent = await db.get(Agent, conv.agent_id)
                if agent is None:
                    logger.warning("title_gen_agent_not_found", agent_id=str(conv.agent_id))
                    return

                messages = [
                    {"role": "system", "content": TITLE_SYSTEM},
                    {"role": "user", "content": first_message},
                ]
                try:
                    response = await model_svc.chat_by_agent(
                        agent, messages, max_tokens=50,
                    )
                except AgentModelNotConfigured:
                    logger.warning(
                        "title_gen_no_model_configured",
                        conversation_id=conversation_id,
                        agent_id=str(conv.agent_id),
                    )
                    return  # permanent error — do not retry
                title = response["choices"][0]["message"]["content"].strip()[:200]

                await db.execute(
                    update(Conversation)
                    .where(Conversation.id == conversation_id)
                    .values(title=title)
                )
                await db.commit()
                logger.info("title_generated", conversation_id=conversation_id, title=title)
        finally:
            await engine.dispose()

    try:
        _run_async(_run())
    except Exception as exc:
        logger.exception("generate_title_failed", conversation_id=conversation_id)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="app.chat.tasks.summarize_conversation", bind=True, max_retries=2)
def summarize_conversation(self, conversation_id: str):
    """Summarize older messages when conversation exceeds 10 messages."""

    async def _run():
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with session_factory() as db:
                conv = await db.get(Conversation, conversation_id)
                if conv is None or conv.message_count <= 10:
                    return

                model_svc = ModelService(db)

                from app.agent.models import Agent
                agent = await db.get(Agent, conv.agent_id)
                if agent is None:
                    return

                # Get older messages (all except last 6)
                result = await db.scalars(
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.created_at.asc())
                )
                all_msgs = list(result.all())

                if len(all_msgs) <= 10:
                    return

                older = all_msgs[:-6]
                conversation_text = "\n".join(
                    f"{m.role}: {m.content}" for m in older
                )

                messages = [
                    {"role": "system", "content": SUMMARY_SYSTEM},
                    {"role": "user", "content": conversation_text},
                ]
                try:
                    response = await model_svc.chat_by_agent(
                        agent, messages, max_tokens=500,
                    )
                except AgentModelNotConfigured:
                    logger.warning(
                        "summarize_no_model_configured",
                        conversation_id=conversation_id,
                        agent_id=str(conv.agent_id),
                    )
                    return  # permanent error — do not retry
                summary = response["choices"][0]["message"]["content"].strip()

                await db.execute(
                    update(Conversation)
                    .where(Conversation.id == conversation_id)
                    .values(memory_summary=summary)
                )
                await db.commit()
                logger.info("conversation_summarized", conversation_id=conversation_id)
        finally:
            await engine.dispose()

    try:
        _run_async(_run())
    except Exception as exc:
        logger.exception("summarize_conversation_failed", conversation_id=conversation_id)
        raise self.retry(exc=exc, countdown=60)
