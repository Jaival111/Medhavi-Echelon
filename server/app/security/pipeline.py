"""
Prompt Security Pipeline
Main orchestrator for the multi-layer security detection system
"""
import asyncio
from typing import Optional, List, Dict
from .layer0_control_plane import ControlPlaneLayer
from .layer1_heuristic import HeuristicAnalyzer
from .layer2_ml import MLClassifier
from .layer3_canary import CanaryTokenTester
from .scoring import ScoringService
from .models import SecurityCheckResult


class PromptSecurityPipeline:
    """
    Multi-layer prompt injection detection pipeline.
    
    Architecture:
    0. Layer 0: Control Plane Detection - Multi-turn prompt injection via control-plane changes
    1. Layer 1: Heuristic Analysis - Pattern matching with weighted keywords
    2. Layer 2: ML Classification - DeBERTa-v3 transformer model
    3. Layer 3: Canary Token Testing - UUID token extraction test
    4. Scoring Service - Weighted aggregation and final verdict
    """
    
    def __init__(
        self,
        groq_api_key: str,
        ml_api_url: Optional[str] = None,
        layer0_weight: float = 0.15,
        layer1_weight: float = 0.20,
        layer2_weight: float = 0.30,
        layer3_weight: float = 0.35,
        safety_threshold: float = 50.0,
        enable_layer0: bool = True,
        enable_layer2: bool = True,
        enable_layer3: bool = True,
    ):
        """
        Initialize the security pipeline.
        
        Args:
            groq_api_key: Groq API key for canary token testing
            ml_api_url: Optional custom ML API URL
            layer0_weight: Weight for control plane layer (default: 15%)
            layer1_weight: Weight for heuristic layer (default: 20%)
            layer2_weight: Weight for ML layer (default: 30%)
            layer3_weight: Weight for canary layer (default: 35%)
            safety_threshold: Score threshold for rejection (default: 50.0)
            enable_layer0: Enable control plane detection layer
            enable_layer2: Enable ML classification layer
            enable_layer3: Enable canary token testing layer
        """
        # Initialize layers
        self.enable_layer0 = enable_layer0
        if enable_layer0:
            self.layer0 = ControlPlaneLayer()
        
        self.layer1 = HeuristicAnalyzer()
        
        self.enable_layer2 = enable_layer2
        if enable_layer2:
            self.layer2 = MLClassifier()
        
        self.enable_layer3 = enable_layer3
        if enable_layer3:
            self.layer3 = CanaryTokenTester(groq_api_key=groq_api_key)
        
        # Initialize scoring service
        self.scorer = ScoringService(
            layer0_weight=layer0_weight,
            layer1_weight=layer1_weight,
            layer2_weight=layer2_weight,
            layer3_weight=layer3_weight,
            safety_threshold=safety_threshold,
        )
    
    async def check_prompt(
        self, 
        prompt: str = None, 
        messages: List[Dict] = None,
        session_id: str = "default_session"
    ) -> SecurityCheckResult:
        """
        Run full security check on a user prompt or message history.
        
        Args:
            prompt: User prompt to analyze (legacy support)
            messages: Full message history with role and content
            session_id: Session identifier for intent tracking
            
        Returns:
            SecurityCheckResult with safety verdict and detailed breakdown
        """
        # Use last user message as prompt if not provided
        if prompt is None and messages:
            user_messages = [msg.get("content", "") for msg in messages if msg.get("role") == "user"]
            prompt = user_messages[-1] if user_messages else ""
        elif prompt is None:
            prompt = ""
        
        # Layer 0: Intent Analysis (synchronous, fast)
        if self.enable_layer0:
            layer0_analysis = self.layer0.analyze(
                prompt=prompt,
                messages=messages,
                session_id=session_id
            )
            # Convert to LayerResult format
            from .models import LayerResult
            layer0_result = LayerResult(
                score=100.0 if layer0_analysis.get("flagged", False) else 0.0,
                normalized_score=100.0 if layer0_analysis.get("flagged", False) else 0.0,
                passed=not layer0_analysis.get("flagged", False),
                details=layer0_analysis
            )
        else:
            layer0_result = self._create_fallback_result()
        
        print("Layer 0:", layer0_result)
        
        # Layer 1: Heuristic Analysis (synchronous, fast)
        layer1_result = self.layer1.analyze(prompt)

        print("Layer 1:", layer1_result)
        
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

        print("Layer 2:", layer2_result)
        print("Layer 3:", layer3_result)
        
        # Compute final score and verdict
        final_result = self.scorer.compute_final_score(
            layer0_result=layer0_result,
            layer1_result=layer1_result,
            layer2_result=layer2_result,
            layer3_result=layer3_result,
        )

        print("Final:", final_result)
        
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
        layer0_result = self._create_fallback_result()
        layer2_result = self._create_fallback_result()
        layer3_result = self._create_fallback_result()
        
        # Use adjusted weights for quick check (100% on layer 1)
        from .scoring import ScoringService
        quick_scorer = ScoringService(
            layer0_weight=0.0,
            layer1_weight=1.0,
            layer2_weight=0.0,
            layer3_weight=0.0,
            safety_threshold=50.0,
        )
        
        return quick_scorer.compute_final_score(
            layer0_result=layer0_result,
            layer1_result=layer1_result,
            layer2_result=layer2_result,
            layer3_result=layer3_result,
        )
