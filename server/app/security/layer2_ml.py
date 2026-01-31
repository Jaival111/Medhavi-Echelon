"""
Layer 2: ML Classification
DeBERTa-v3 transformer model for binary prompt injection classification
"""
import httpx
from typing import Optional
from .models import LayerResult


class MLClassifier:
    """
    Machine learning classifier using DeBERTa-v3 model hosted on Hugging Face Spaces.
    Provides binary classification: SAFE vs INJECTION with probability scores.
    """
    
    def __init__(
        self,
        api_url: str = "https://protectai-deberta-v3-base.hf.space/predict",
        timeout: float = 10.0,
        fallback_score: float = 0.0
    ):
        """
        Initialize ML classifier.
        
        Args:
            api_url: URL of the Hugging Face Spaces endpoint
            timeout: Request timeout in seconds
            fallback_score: Score to use if API is unavailable
        """
        self.api_url = api_url
        self.timeout = timeout
        self.fallback_score = fallback_score
    
    async def classify(self, prompt: str) -> LayerResult:
        """
        Classify prompt using DeBERTa-v3 model.
        
        Args:
            prompt: User prompt to classify
            
        Returns:
            LayerResult with probability score (0.0 to 1.0)
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.api_url,
                    json={"text": prompt}
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # Expected response format: {"label": "INJECTION"/"SAFE", "score": 0.95}
                    label = result.get("label", "SAFE")
                    confidence = result.get("score", 0.0)
                    
                    # If INJECTION detected, use confidence score
                    # If SAFE, use (1 - confidence) as injection probability
                    injection_probability = confidence if label == "INJECTION" else (1 - confidence)
                    
                    # Normalize to 0-100 scale
                    normalized_score = injection_probability * 100.0
                    
                    return LayerResult(
                        score=injection_probability,
                        normalized_score=normalized_score,
                        passed=normalized_score < 50.0,  # Threshold at 50
                        details={
                            "label": label,
                            "confidence": confidence,
                            "api_status": "success",
                            "model": "protectai/deberta-v3-base"
                        }
                    )
                else:
                    # API error - use fallback
                    return self._fallback_result(
                        f"API returned status {response.status_code}"
                    )
        
        except httpx.TimeoutException:
            return self._fallback_result("API request timeout")
        
        except Exception as e:
            return self._fallback_result(f"Error: {str(e)}")
    
    def _fallback_result(self, reason: str) -> LayerResult:
        """Return fallback result when API is unavailable"""
        return LayerResult(
            score=self.fallback_score,
            normalized_score=self.fallback_score * 100.0,
            passed=True,  # Fail open - don't block on API errors
            details={
                "api_status": "failed",
                "reason": reason,
                "fallback": True
            }
        )
