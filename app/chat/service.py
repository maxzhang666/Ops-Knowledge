import uuid

import structlog
from sqlalchemy import func, select, update
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
        limit: int = 50,
    ) -> list[Message]:
        result = await self.db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        return list(result.all())

    async def delete_conversation(self, conversation_id: uuid.UUID) -> None:
        conv = await self.get_conversation(conversation_id)
        await self.db.delete(conv)
        await self.db.flush()
        logger.info("conversation_deleted", conversation_id=str(conversation_id))
