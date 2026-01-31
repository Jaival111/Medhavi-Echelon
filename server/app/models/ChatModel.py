"""
Chat and Message models for storing conversation history
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import List, TYPE_CHECKING
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.BaseDatabase import Base

if TYPE_CHECKING:
    from app.models.UserModel import User


class Chat(Base):
    """Chat session model - represents a conversation thread"""
    __tablename__ = "chats"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="chats")
    messages: Mapped[List["Message"]] = relationship("Message", back_populates="chat", cascade="all, delete-orphan", order_by="Message.created_at")
    
    def __repr__(self):
        return f"<Chat(id={self.id}, name={self.name}, user_id={self.user_id})>"


class Message(Base):
    """Message model - represents individual messages in a chat"""
    __tablename__ = "messages"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # 'user', 'assistant', 'system'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)  # Order of messages in chat
    
    # Relationships
    chat: Mapped["Chat"] = relationship("Chat", back_populates="messages")
    
    def __repr__(self):
        return f"<Message(id={self.id}, role={self.role}, chat_id={self.chat_id})>"
