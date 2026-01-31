"""
Data models for security pipeline
"""
from pydantic import BaseModel, Field
from typing import Dict, Optional


class SecurityCheckResult(BaseModel):
    """Result of the security check"""
    safe: bool = Field(..., description="Whether the prompt is safe to process")
    score: float = Field(..., description="Final weighted risk score (0-100)")
    breakdown: Dict[str, float] = Field(..., description="Individual layer scores")
    layer_details: Dict[str, Dict] = Field(default_factory=dict, description="Detailed results from each layer")
    reason: Optional[str] = Field(None, description="Reason for rejection if unsafe")


class LayerResult(BaseModel):
    """Result from an individual security layer"""
    score: float = Field(..., description="Layer-specific score")
    normalized_score: float = Field(..., description="Normalized score (0-100)")
    passed: bool = Field(..., description="Whether this layer passed")
    details: Dict = Field(default_factory=dict, description="Layer-specific details")
