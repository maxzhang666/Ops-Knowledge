import uuid

import structlog
from sqlalchemy import bindparam, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.models import Conversation, Message
from app.core.exceptions import NotFoundError

logger = structlog.get_logger(__name__)


class ConversationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_conversation(
        self,
        agent_id: uuid.UUID,
        user_id: uuid.UUID,
        title: str | None = None,
    ) -> Conversation:
        conv = Conversation(
            agent_id=agent_id,
            user_id=user_id,
            title=title,
        )
        self.db.add(conv)
        await self.db.flush()
        await self.db.refresh(conv)
        logger.info("conversation_created", conversation_id=str(conv.id))
        return conv

    async def get_conversation(self, conversation_id: uuid.UUID) -> Conversation:
        conv = await self.db.get(Conversation, conversation_id)
        if conv is None:
            raise NotFoundError("Conversation", str(conversation_id))
        return conv

    async def list_conversations(
        self,
        agent_id: uuid.UUID,
        user_id: uuid.UUID,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Conversation], int]:
        base = select(Conversation).where(
            Conversation.agent_id == agent_id,
            Conversation.user_id == user_id,
        )

        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        rows = await self.db.scalars(
            base.order_by(Conversation.updated_at.desc()).offset(offset).limit(limit)
        )
        return list(rows.all()), total

    async def add_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        status: str | None = None,
        metadata: dict | None = None,
        token_usage: dict | None = None,
        trace_id: str | None = None,
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            status=status,
            metadata_=metadata,
            token_usage=token_usage,
            trace_id=trace_id,
        )
        self.db.add(msg)
        await self.db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(message_count=Conversation.message_count + 1)
        )
        await self.db.flush()
        return msg

    async def get_messages(
        self,
        conversation_id: uuid.UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Message]:
        result = await self.db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.all())

    async def get_message(
        self,
        message_id: uuid.UUID,
    ) -> Message:
        msg = await self.db.get(Message, message_id)
        if msg is None:
            raise NotFoundError("Message", str(message_id))
        return msg

    async def update_message(
        self,
        message_id: uuid.UUID,
        **kwargs,
    ) -> Message:
        msg = await self.get_message(message_id)
        for k, v in kwargs.items():
            if v is not None:
                setattr(msg, k, v)
        await self.db.flush()
        return msg

    async def update_conversation(
        self,
        conversation_id: uuid.UUID,
        **kwargs,
    ) -> Conversation:
        conv = await self.get_conversation(conversation_id)
        for k, v in kwargs.items():
            if v is not None:
                setattr(conv, k, v)
        await self.db.flush()
        await self.db.refresh(conv)
        return conv

    async def delete_conversation(self, conversation_id: uuid.UUID) -> None:
        """Hard delete. ``messages`` cascade via FK. Associated LangGraph
        checkpoints (thread_id = conversation_id) are deleted in the same
        transaction so the engine tables don't accumulate orphan rows."""
        conv = await self.get_conversation(conversation_id)
        # LangGraph checkpoint rows are keyed by the bare text thread_id,
        # which for Workflow Agent runs is ``str(conversation_id)`` (see
        # app/chat/workflow_pipeline.py). Clean all three LangGraph-managed
        # tables before dropping the Conversation itself.
        thread_id = str(conversation_id)
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            stmt = text(
                f"DELETE FROM {table} WHERE thread_id IN :ids"
            ).bindparams(bindparam("ids", expanding=True))
            await self.db.execute(stmt, {"ids": [thread_id]})
        await self.db.delete(conv)
        await self.db.flush()
        logger.info("conversation_deleted", conversation_id=str(conversation_id))
