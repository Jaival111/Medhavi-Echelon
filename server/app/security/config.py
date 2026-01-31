"""
Configuration for the Prompt Security Pipeline
"""
from pydantic_settings import BaseSettings
from typing import Optional


class SecurityConfig(BaseSettings):
    """Security pipeline configuration"""
    
    # Layer weights (must sum to 1.0)
    layer1_weight: float = 0.25  # Heuristic Analysis
    layer2_weight: float = 0.35  # ML Classification
    layer3_weight: float = 0.40  # Canary Token Testing
    
    # Thresholds
    safety_threshold: float = 50.0  # Final score threshold for rejection
    layer1_veto_threshold: float = 80.0  # Layer 1 immediate veto threshold
    
    # Layer toggles
    enable_layer2: bool = True  # ML classification
    enable_layer3: bool = True  # Canary token testing
    
    # ML API configuration
    ml_api_url: str = "https://protectai-deberta-v3-base.hf.space/predict"
    ml_api_timeout: float = 10.0
    
    # Canary testing configuration
    canary_model: str = "llama-3.3-70b-versatile"
    canary_temperature: float = 0.0
    canary_max_tokens: int = 150
    
    # Security features
    layer3_veto: bool = True  # Allow layer 3 to immediately veto
    
    class Config:
        env_prefix = "SECURITY_"
        env_file = ".env"


# Default configuration instance
default_config = SecurityConfig()
