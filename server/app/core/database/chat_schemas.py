"""
Pydantic schemas for Chat and Message models
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime
import uuid


class MessageBase(BaseModel):
    """Base message schema"""
    role: str = Field(..., description="Role of the message sender (system, user, or assistant)")
    content: str = Field(..., description="Content of the message")


class MessageCreate(MessageBase):
    """Schema for creating a message"""
    pass


class MessageResponse(MessageBase):
    """Schema for message response"""
    id: uuid.UUID
    chat_id: uuid.UUID
    sequence: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class ChatBase(BaseModel):
    """Base chat schema"""
    name: str = Field(..., description="Name/title of the chat")


class ChatCreate(ChatBase):
    """Schema for creating a chat"""
    pass


class ChatUpdate(BaseModel):
    """Schema for updating a chat"""
    name: Optional[str] = Field(None, description="New name for the chat")


class ChatSummary(ChatBase):
    """Schema for chat summary (without messages)"""
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    message_count: int = Field(default=0, description="Number of messages in the chat")
    
    model_config = ConfigDict(from_attributes=True)


class ChatResponse(ChatBase):
    """Schema for full chat response with messages"""
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse] = []
    
    model_config = ConfigDict(from_attributes=True)


class ChatListResponse(BaseModel):
    """Schema for list of chats"""
    chats: List[ChatSummary]
    total: int
