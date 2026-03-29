from __future__ import annotations
from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy.orm import relationship, Mapped
from typing import List, TYPE_CHECKING

from app.models.BaseDatabase import Base

if TYPE_CHECKING:
    from app.models.ChatModel import Chat

class User(SQLAlchemyBaseUserTableUUID, Base):
    # Relationships
    chats: Mapped[List["Chat"]] = relationship("Chat", back_populates="user", cascade="all, delete-orphan")