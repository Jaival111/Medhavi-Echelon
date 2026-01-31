from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, AsyncGenerator
from groq import Groq
from sqlalchemy.ext.asyncio import AsyncSession
import json
import uuid

from app.core.config import GROQ_API_KEY
from app.security import PromptSecurityPipeline, SecurityCheckResult
from app.core.database.database import get_async_session
from app.core.database import chat_crud
from app.core.database.chat_schemas import (
    ChatResponse, ChatSummary, ChatListResponse, 
    MessageResponse, ChatCreate, ChatUpdate
)
from app.models.UserModel import User
from app.auth.user import current_active_user

router = APIRouter(tags=["chat"])

def ensure_uuid(value) -> uuid.UUID:
    """Convert a value to UUID if it's not already one"""
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))

class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the message sender (system, user, or assistant)")
    content: str = Field(..., description="Content of the message")

class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., description="List of conversation messages")
    model: str = Field(default="llama-3.3-70b-versatile", description="Groq model to use")
    temperature: float = Field(default=0.7, ge=0, le=2, description="Sampling temperature")
    max_tokens: Optional[int] = Field(default=1024, description="Maximum tokens to generate")
    stream: bool = Field(default=False, description="Whether to stream the response")

class ChatCompletionResponse(BaseModel):
    message: ChatMessage
    usage: Optional[dict] = None

# Initialize Groq client
groq_client = Groq(api_key=GROQ_API_KEY)

# Initialize security pipeline
security_pipeline = None
if GROQ_API_KEY:
    security_pipeline = PromptSecurityPipeline(
        groq_api_key=GROQ_API_KEY,
        layer0_weight=0.15,  # 15% - Intent Analysis
        layer1_weight=0.20,  # 20% - Heuristic Analysis
        layer2_weight=0.30,  # 30% - ML Classification
        layer3_weight=0.35,  # 35% - Canary Token Testing
        safety_threshold=50.0,  # Reject if score >= 50
        enable_layer0=True,  # Enable intent analysis
        enable_layer2=True,  # Enable ML classification
        enable_layer3=True,  # Enable canary token testing
    )

async def stream_chat_response(
    messages: List[dict],
    model: str,
    temperature: float,
    max_tokens: int
) -> AsyncGenerator[str, None]:
    """Stream chat completion from Groq API"""
    try:
        stream = groq_client.chat.completions.create(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        
        for chunk in stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                yield f"data: {json.dumps({'content': content})}\n\n"
        
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"

@router.post("/", response_model=ChatResponse)
async def converse(
    request: ChatRequest,
    # user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Create a new chat or continue existing conversation.
    Automatically creates a new chat for the first message.
    Supports both streaming and non-streaming responses.
    Includes multi-layer prompt injection detection.
    """
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="Groq API key not configured")
    
    try:
        # Create a new chat with auto-generated name from first message
        first_user_message = next((msg.content for msg in request.messages if msg.role == "user"), "New Chat")
        chat_name = first_user_message[:50] + "..." if len(first_user_message) > 50 else first_user_message
        
        chat = await chat_crud.create_chat(
            db=db,
            user_id=uuid.UUID("78d8dd0e-d404-4f82-97fb-f3b3cb82b61e"),
            name=chat_name
        )
        
        # Pass all messages to security check for intent analysis
        if security_pipeline:
            # Convert messages to dict format for security pipeline
            messages_dict = [{"role": msg.role, "content": msg.content} for msg in request.messages]
            
            # Run security check with full message history
            security_result = await security_pipeline.check_prompt(
                messages=messages_dict,
                session_id=str(chat.id)
            )
            
            # If prompt is unsafe, reject immediately and delete the chat
            if not security_result.safe:
                await chat_crud.delete_chat(db, chat.id, uuid.UUID("78d8dd0e-d404-4f82-97fb-f3b3cb82b61e"))
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Prompt rejected by security system",
                        "reason": security_result.reason,
                        "security_score": security_result.score,
                        "breakdown": security_result.breakdown,
                    }
                )
        
        # Convert messages to dict format for Groq API
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        
        if request.stream:
            # For streaming, we'll handle message storage separately
            raise HTTPException(status_code=400, detail="Streaming not supported for new chats. Use /{chat_id} endpoint.")
        else:
            # Non-streaming response
            completion = groq_client.chat.completions.create(
                messages=messages,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            
            assistant_message = completion.choices[0].message
            
            # Store all messages in database
            messages_to_store = [
                (msg["role"], msg["content"]) for msg in messages
            ]
            # Add assistant response
            messages_to_store.append((assistant_message.role, assistant_message.content))
            
            await chat_crud.add_messages_to_chat(
                db=db,
                chat_id=chat.id,
                messages=messages_to_store
            )
            
            # Fetch the complete chat with messages
            chat_with_messages = await chat_crud.get_chat_by_id(db, chat.id, uuid.UUID("78d8dd0e-d404-4f82-97fb-f3b3cb82b61e"))
            
            return ChatResponse.model_validate(chat_with_messages)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat completion failed: {str(e)}")

@router.post("/{chat_id}", response_model=ChatResponse)
async def add_message(
    chat_id: str,
    request: ChatRequest,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Add message to an existing chat conversation.
    Supports both streaming and non-streaming responses.
    Includes multi-layer prompt injection detection.
    """
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="Groq API key not configured")
    
    try:
        # Parse chat_id
        try:
            chat_uuid = uuid.UUID(chat_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid chat_id format")
        
        # Verify chat exists and belongs to user
        chat = await chat_crud.get_chat_by_id(db, chat_uuid, user.id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        # Pass all messages to security check for intent analysis
        if security_pipeline:
            # Convert messages to dict format for security pipeline
            messages_dict = [{"role": msg.role, "content": msg.content} for msg in request.messages]
            
            # Run security check with full message history
            security_result = await security_pipeline.check_prompt(
                messages=messages_dict,
                session_id=chat_id
            )
            
            # If prompt is unsafe, reject immediately
            if not security_result.safe:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Prompt rejected by security system",
                        "reason": security_result.reason,
                        "security_score": security_result.score,
                        "breakdown": security_result.breakdown,
                    }
                )
        
        # Convert messages to dict format for Groq API
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        
        if request.stream:
            # For streaming, we'll handle message storage separately
            raise HTTPException(status_code=400, detail="Streaming not supported for new chats. Use /{chat_id} endpoint.")
        else:
            # Non-streaming response
            completion = groq_client.chat.completions.create(
                messages=messages,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            
            assistant_message = completion.choices[0].message
            
            # Store all messages in database
            messages_to_store = [
                (msg["role"], msg["content"]) for msg in messages
            ]
            # Add assistant response
            messages_to_store.append((assistant_message.role, assistant_message.content))
            
            await chat_crud.add_messages_to_chat(
                db=db,
                chat_id=chat.id,
                messages=messages_to_store
            )
            
            # Fetch the complete chat with messages
            chat_with_messages = await chat_crud.get_chat_by_id(db, chat.id, user.id)
            
            return ChatResponse.model_validate(chat_with_messages)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat completion failed: {str(e)}")


@router.get("/models")
async def list_models():
    """List available Groq models"""
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="Groq API key not configured")
    
    try:
        models = groq_client.models.list()
        return {
            "models": [
                {
                    "id": model.id,
                    "owned_by": model.owned_by,
                    "created": model.created
                }
                for model in models.data
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch models: {str(e)}")


@router.get("/chats", response_model=ChatListResponse)
async def get_user_chats(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
    skip: int = 0,
    limit: int = 100
):
    """
    Get all chats for the authenticated user with message counts.
    """
    try:
        chats, total = await chat_crud.get_user_chats(db, user.id, skip, limit)
        
        # Build chat summaries with message counts
        chat_summaries = []
        for chat in chats:
            message_count = await chat_crud.get_message_count(db, chat.id)
            chat_summary = ChatSummary(
                id=chat.id,
                user_id=chat.user_id,
                name=chat.name,
                created_at=chat.created_at,
                updated_at=chat.updated_at,
                message_count=message_count
            )
            chat_summaries.append(chat_summary)
        
        return ChatListResponse(chats=chat_summaries, total=total)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chats: {str(e)}")


@router.get("/chats/{chat_id}", response_model=ChatResponse)
async def get_chat(
    chat_id: str,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get a specific chat with all its messages for the authenticated user.
    """
    try:
        # Parse chat_id
        try:
            chat_uuid = uuid.UUID(chat_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid chat_id format")
        
        chat = await chat_crud.get_chat_by_id(db, chat_uuid, user.id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        return ChatResponse.model_validate(chat)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chat: {str(e)}")


@router.get("/chats/{chat_id}/messages", response_model=List[MessageResponse])
async def get_chat_messages(
    chat_id: str,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Get all messages for a specific chat.
    """
    try:
        # Parse chat_id
        try:
            chat_uuid = uuid.UUID(chat_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid chat_id format")
        
        messages = await chat_crud.get_chat_messages(db, chat_uuid, user.id)
        if messages is None:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        return [MessageResponse.model_validate(msg) for msg in messages]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch messages: {str(e)}")


@router.patch("/chats/{chat_id}", response_model=ChatResponse)
async def update_chat(
    chat_id: str,
    chat_update: ChatUpdate,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Update a chat's metadata (e.g., rename).
    """
    try:
        # Parse chat_id
        try:
            chat_uuid = uuid.UUID(chat_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid chat_id format")
        
        updated_chat = await chat_crud.update_chat(
            db, chat_uuid, user.id, name=chat_update.name
        )
        if not updated_chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        # Fetch with messages
        chat_with_messages = await chat_crud.get_chat_by_id(db, chat_uuid, user.id)
        return ChatResponse.model_validate(chat_with_messages)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update chat: {str(e)}")


@router.delete("/chats/{chat_id}")
async def delete_chat(
    chat_id: str,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    Delete a chat and all its messages.
    """
    try:
        # Parse chat_id
        try:
            chat_uuid = uuid.UUID(chat_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid chat_id format")
        
        deleted = await chat_crud.delete_chat(db, chat_uuid, user.id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        return {"message": "Chat deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete chat: {str(e)}")


class SecurityCheckRequest(BaseModel):
    prompt: str = Field(..., description="Prompt to check for security risks")


@router.post("/security-check", response_model=SecurityCheckResult)
async def security_check(request: SecurityCheckRequest):
    """
    Check a prompt for potential security risks without executing it.
    Returns detailed analysis from all security layers.
    """
    if not security_pipeline:
        raise HTTPException(status_code=500, detail="Security pipeline not initialized")
    
    try:
        result = await security_pipeline.check_prompt(request.prompt)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Security check failed: {str(e)}")
