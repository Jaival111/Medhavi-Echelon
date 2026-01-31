from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Optional, AsyncGenerator
from groq import Groq
import json

from app.core.config import GROQ_API_KEY
from app.security import PromptSecurityPipeline, SecurityCheckResult

router = APIRouter(tags=["chat"])

class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the message sender (system, user, or assistant)")
    content: str = Field(..., description="Content of the message")

class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., description="List of conversation messages")
    model: str = Field(default="llama-3.3-70b-versatile", description="Groq model to use")
    temperature: float = Field(default=0.7, ge=0, le=2, description="Sampling temperature")
    max_tokens: Optional[int] = Field(default=1024, description="Maximum tokens to generate")
    stream: bool = Field(default=False, description="Whether to stream the response")

class ChatResponse(BaseModel):
    message: ChatMessage
    usage: Optional[dict] = None

# Initialize Groq client
groq_client = Groq(api_key=GROQ_API_KEY)

# Initialize security pipeline
security_pipeline = None
if GROQ_API_KEY:
    security_pipeline = PromptSecurityPipeline(
        groq_api_key=GROQ_API_KEY,
        layer1_weight=0.25,  # 25% - Heuristic Analysis
        layer2_weight=0.35,  # 35% - ML Classification
        layer3_weight=0.40,  # 40% - Canary Token Testing
        safety_threshold=50.0,  # Reject if score >= 50
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

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Conversational chat endpoint with Groq API integration.
    Supports both streaming and non-streaming responses.
    Includes multi-layer prompt injection detection.
    """
    if not GROQ_API_KEY:
        raise HTTPException(status_code=500, detail="Groq API key not configured")
    
    try:
        # Extract user prompt from the last message for security check
        # user_messages = [msg for msg in request.messages if msg.role == "user"]
        # if user_messages and security_pipeline:
        #     last_user_prompt = user_messages[-1].content
            
        #     # Run security check
        #     security_result = await security_pipeline.check_prompt(last_user_prompt)
            
        #     # If prompt is unsafe, reject immediately
        #     if not security_result.safe:
        #         raise HTTPException(
        #             status_code=400,
        #             detail={
        #                 "error": "Prompt rejected by security system",
        #                 "reason": security_result.reason,
        #                 "security_score": security_result.score,
        #                 "breakdown": security_result.breakdown,
        #             }
        #         )
        
        # Convert messages to dict format for Groq API
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        
        if request.stream:
            # Return streaming response
            return StreamingResponse(
                stream_chat_response(
                    messages=messages,
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens
                ),
                media_type="text/event-stream"
            )
        else:
            # Non-streaming response
            completion = groq_client.chat.completions.create(
                messages=messages,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            
            assistant_message = completion.choices[0].message
            
            return ChatResponse(
                message=ChatMessage(
                    role=assistant_message.role,
                    content=assistant_message.content
                ),
                usage={
                    "prompt_tokens": completion.usage.prompt_tokens,
                    "completion_tokens": completion.usage.completion_tokens,
                    "total_tokens": completion.usage.total_tokens
                }
            )
    
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
