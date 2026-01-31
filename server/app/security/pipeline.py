"""
Prompt Security Pipeline
Main orchestrator for the three-layer security detection system
"""
import asyncio
from typing import Optional
from .layer1_heuristic import HeuristicAnalyzer
from .layer2_ml import MLClassifier
from .layer3_canary import CanaryTokenTester
from .scoring import ScoringService
from .models import SecurityCheckResult


class PromptSecurityPipeline:
    """
    Multi-layer prompt injection detection pipeline.
    
    Architecture:
    1. Layer 1: Heuristic Analysis - Pattern matching with weighted keywords
    2. Layer 2: ML Classification - DeBERTa-v3 transformer model
    3. Layer 3: Canary Token Testing - UUID token extraction test
    4. Scoring Service - Weighted aggregation and final verdict
    """
    
    def __init__(
        self,
        groq_api_key: str,
        ml_api_url: Optional[str] = None,
        layer1_weight: float = 0.25,
        layer2_weight: float = 0.35,
        layer3_weight: float = 0.40,
        safety_threshold: float = 50.0,
        enable_layer2: bool = True,
        enable_layer3: bool = True,
    ):
        """
        Initialize the security pipeline.
        
        Args:
            groq_api_key: Groq API key for canary token testing
            ml_api_url: Optional custom ML API URL
            layer1_weight: Weight for heuristic layer (default: 25%)
            layer2_weight: Weight for ML layer (default: 35%)
            layer3_weight: Weight for canary layer (default: 40%)
            safety_threshold: Score threshold for rejection (default: 50.0)
            enable_layer2: Enable ML classification layer
            enable_layer3: Enable canary token testing layer
        """
        # Initialize layers
        self.layer1 = HeuristicAnalyzer()
        
        self.enable_layer2 = enable_layer2
        if enable_layer2:
            self.layer2 = MLClassifier(
                api_url=ml_api_url or "https://protectai-deberta-v3-base.hf.space/predict"
            )
        
        self.enable_layer3 = enable_layer3
        if enable_layer3:
            self.layer3 = CanaryTokenTester(groq_api_key=groq_api_key)
        
        # Initialize scoring service
        self.scorer = ScoringService(
            layer1_weight=layer1_weight,
            layer2_weight=layer2_weight,
            layer3_weight=layer3_weight,
            safety_threshold=safety_threshold,
        )
    
    async def check_prompt(self, prompt: str) -> SecurityCheckResult:
        """
        Run full security check on a user prompt.
        
        Args:
            prompt: User prompt to analyze
            
        Returns:
            SecurityCheckResult with safety verdict and detailed breakdown
        """
        # Layer 1: Heuristic Analysis (synchronous, fast)
        layer1_result = self.layer1.analyze(prompt)
        
        # Layers 2 & 3: Run in parallel for efficiency
        tasks = []
        
        if self.enable_layer2:
            tasks.append(self.layer2.classify(prompt))
        
        if self.enable_layer3:
            tasks.append(self.layer3.test(prompt))
        
        # Execute parallel tasks
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Unpack results
            result_idx = 0
            
            if self.enable_layer2:
                layer2_result = results[result_idx] if not isinstance(results[result_idx], Exception) else self._create_fallback_result()
                result_idx += 1
            else:
                layer2_result = self._create_fallback_result()
            
            if self.enable_layer3:
                layer3_result = results[result_idx] if not isinstance(results[result_idx], Exception) else self._create_fallback_result()
            else:
                layer3_result = self._create_fallback_result()
        else:
            layer2_result = self._create_fallback_result()
            layer3_result = self._create_fallback_result()
        
        # Compute final score and verdict
        final_result = self.scorer.compute_final_score(
            layer1_result=layer1_result,
            layer2_result=layer2_result,
            layer3_result=layer3_result,
        )
        
        return final_result
    
    def _create_fallback_result(self):
        """Create a neutral fallback result for disabled/failed layers"""
        from .models import LayerResult
        return LayerResult(
            score=0.0,
            normalized_score=0.0,
            passed=True,
            details={"status": "disabled_or_failed"}
        )
    
    async def check_prompt_quick(self, prompt: str) -> SecurityCheckResult:
        """
        Quick security check using only Layer 1 (heuristic analysis).
        Useful for low-latency requirements.
        
        Args:
            prompt: User prompt to analyze
            
        Returns:
            SecurityCheckResult based on heuristic analysis only
        """
        layer1_result = self.layer1.analyze(prompt)
        
        # Create neutral results for other layers
        layer2_result = self._create_fallback_result()
        layer3_result = self._create_fallback_result()
        
        # Use adjusted weights for quick check (100% on layer 1)
        from .scoring import ScoringService
        quick_scorer = ScoringService(
            layer1_weight=1.0,
            layer2_weight=0.0,
            layer3_weight=0.0,
            safety_threshold=50.0,
        )
        
        return quick_scorer.compute_final_score(
            layer1_result=layer1_result,
            layer2_result=layer2_result,
            layer3_result=layer3_result,
        )
