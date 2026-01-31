"""
CRUD operations for Chat and Message models
"""
import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload

from app.models.ChatModel import Chat, Message


async def create_chat(
    db: AsyncSession,
    user_id: uuid.UUID,
    name: str
) -> Chat:
    """Create a new chat for a user"""
    chat = Chat(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name
    )
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return chat


async def get_chat_by_id(
    db: AsyncSession,
    chat_id: uuid.UUID,
    user_id: uuid.UUID
) -> Optional[Chat]:
    """Get a chat by ID for a specific user with messages"""
    stmt = (
        select(Chat)
        .options(selectinload(Chat.messages))
        .where(Chat.id == chat_id, Chat.user_id == user_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_chats(
    db: AsyncSession,
    user_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100
) -> tuple[List[Chat], int]:
    """Get all chats for a user with message counts"""
    # Get chats
    stmt = (
        select(Chat)
        .where(Chat.user_id == user_id)
        .order_by(Chat.updated_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    chats = result.scalars().all()
    
    # Get total count
    count_stmt = select(func.count(Chat.id)).where(Chat.user_id == user_id)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()
    
    return list(chats), total


async def update_chat(
    db: AsyncSession,
    chat_id: uuid.UUID,
    user_id: uuid.UUID,
    name: Optional[str] = None
) -> Optional[Chat]:
    """Update a chat's metadata"""
    stmt = select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id)
    result = await db.execute(stmt)
    chat = result.scalar_one_or_none()
    
    if not chat:
        return None
    
    if name is not None:
        chat.name = name
    
    chat.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(chat)
    return chat


async def delete_chat(
    db: AsyncSession,
    chat_id: uuid.UUID,
    user_id: uuid.UUID
) -> bool:
    """Delete a chat and all its messages"""
    stmt = delete(Chat).where(Chat.id == chat_id, Chat.user_id == user_id)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0


async def add_messages_to_chat(
    db: AsyncSession,
    chat_id: uuid.UUID,
    messages: List[tuple[str, str]]  # List of (role, content) tuples
) -> List[Message]:
    """Add multiple messages to a chat"""
    # Get the current max sequence number
    stmt = select(func.max(Message.sequence)).where(Message.chat_id == chat_id)
    result = await db.execute(stmt)
    max_sequence = result.scalar_one_or_none() or 0
    
    # Create message objects
    message_objects = []
    for idx, (role, content) in enumerate(messages, start=1):
        message = Message(
            id=uuid.uuid4(),
            chat_id=chat_id,
            role=role,
            content=content,
            sequence=max_sequence + idx
        )
        message_objects.append(message)
        db.add(message)
    
    # Update chat's updated_at timestamp
    stmt = select(Chat).where(Chat.id == chat_id)
    result = await db.execute(stmt)
    chat = result.scalar_one_or_none()
    if chat:
        chat.updated_at = datetime.utcnow()
    
    await db.commit()
    
    # Refresh all messages
    for message in message_objects:
        await db.refresh(message)
    
    return message_objects


async def get_chat_messages(
    db: AsyncSession,
    chat_id: uuid.UUID,
    user_id: uuid.UUID
) -> Optional[List[Message]]:
    """Get all messages for a chat"""
    # First verify the chat belongs to the user
    chat_stmt = select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id)
    chat_result = await db.execute(chat_stmt)
    chat = chat_result.scalar_one_or_none()
    
    if not chat:
        return None
    
    # Get messages
    stmt = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.sequence)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_message_count(
    db: AsyncSession,
    chat_id: uuid.UUID
) -> int:
    """Get the count of messages in a chat"""
    stmt = select(func.count(Message.id)).where(Message.chat_id == chat_id)
    result = await db.execute(stmt)
    return result.scalar_one()
