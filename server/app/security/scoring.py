"""
Scoring Service
Normalizes layer scores, applies weights, and computes final security verdict
"""
from typing import Dict, Tuple
from .models import LayerResult, SecurityCheckResult


class ScoringService:
    """
    Aggregates and scores results from all security layers.
    Applies configurable weights and veto conditions.
    """
    
    def __init__(
        self,
        layer0_weight: float = 0.25,  # 25% - Intent Analysis
        layer1_weight: float = 0.10,  # 10% - Heuristic Analysis
        layer2_weight: float = 0.30,  # 30% - ML Classification
        layer3_weight: float = 0.35,  # 35% - Canary Token Testing
        safety_threshold: float = 50.0,  # Final score threshold
        layer3_veto: bool = True,  # Layer 3 can veto (immediate rejection)
        layer1_veto_threshold: float = 80.0,  # Layer 1 high-confidence veto
        layer0_veto: bool = True,  # Layer 0 can veto (intent shift)
    ):
        """
        Initialize scoring service.
        
        Args:
            layer0_weight: Weight for intent analysis (0-1)
            layer1_weight: Weight for heuristic analysis (0-1)
            layer2_weight: Weight for ML classification (0-1)
            layer3_weight: Weight for canary token testing (0-1)
            safety_threshold: Threshold above which prompt is rejected
            layer3_veto: Whether layer 3 can immediately reject
            layer1_veto_threshold: Threshold for layer 1 immediate rejection
            layer0_veto: Whether layer 0 can immediately reject on intent shift
        """
        # Validate weights sum to 1.0
        total_weight = layer0_weight + layer1_weight + layer2_weight + layer3_weight
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total_weight}")
        
        self.layer0_weight = layer0_weight
        self.layer1_weight = layer1_weight
        self.layer2_weight = layer2_weight
        self.layer3_weight = layer3_weight
        self.safety_threshold = safety_threshold
        self.layer3_veto = layer3_veto
        self.layer1_veto_threshold = layer1_veto_threshold
        self.layer0_veto = layer0_veto
    
    def compute_final_score(
        self,
        layer0_result: LayerResult,
        layer1_result: LayerResult,
        layer2_result: LayerResult,
        layer3_result: LayerResult
    ) -> SecurityCheckResult:
        """
        Compute final weighted security score.
        
        Args:
            layer0_result: Intent analysis result
            layer1_result: Heuristic analysis result
            layer2_result: ML classification result
            layer3_result: Canary token testing result
            
        Returns:
            SecurityCheckResult with final verdict
        """
        # Extract normalized scores (all on 0-100 scale)
        layer0_score = layer0_result.normalized_score
        layer1_score = layer1_result.normalized_score
        layer2_score = layer2_result.normalized_score
        layer3_score = layer3_result.normalized_score
        
        # Check veto conditions (immediate rejection)
        veto_triggered, veto_reason = self._check_veto_conditions(
            layer0_result, layer1_result, layer2_result, layer3_result
        )
        
        if veto_triggered:
            return SecurityCheckResult(
                safe=False,
                score=100.0,  # Maximum risk score
                breakdown={
                    "layer0_intent": layer0_score,
                    "layer1_heuristic": layer1_score,
                    "layer2_ml": layer2_score,
                    "layer3_canary": layer3_score,
                },
                layer_details={
                    "layer0": layer0_result.details,
                    "layer1": layer1_result.details,
                    "layer2": layer2_result.details,
                    "layer3": layer3_result.details,
                },
                reason=veto_reason
            )
        
        # Compute weighted final score
        final_score = (
            (layer0_score * self.layer0_weight) +
            (layer1_score * self.layer1_weight) +
            (layer2_score * self.layer2_weight) +
            (layer3_score * self.layer3_weight)
        )
        
        # Determine safety verdict
        is_safe = final_score < self.safety_threshold
        
        # Generate reason if unsafe
        reason = None if is_safe else self._generate_rejection_reason(
            final_score, layer0_score, layer1_score, layer2_score, layer3_score
        )
        
        return SecurityCheckResult(
            safe=is_safe,
            score=round(final_score, 2),
            breakdown={
                "layer0_intent": round(layer0_score, 2),
                "layer1_heuristic": round(layer1_score, 2),
                "layer2_ml": round(layer2_score, 2),
                "layer3_canary": round(layer3_score, 2),
            },
            layer_details={
                "layer0": layer0_result.details,
                "layer1": layer1_result.details,
                "layer2": layer2_result.details,
                "layer3": layer3_result.details,
            },
            reason=reason
        )
    
    def _check_veto_conditions(
        self,
        layer0_result: LayerResult,
        layer1_result: LayerResult,
        layer2_result: LayerResult,
        layer3_result: LayerResult
    ) -> Tuple[bool, str]:
        """
        Check if any veto conditions are met for immediate rejection.
        
        Args:
            layer0_result: Intent analysis result
            layer1_result: Heuristic analysis result
            layer2_result: ML classification result
            layer3_result: Canary token testing result
            
        Returns:
            Tuple of (veto_triggered, reason)
        """
        # Layer 0 veto: Drastic intent shift detected
        if self.layer0_veto and layer0_result.normalized_score == 100.0:
            intent_details = layer0_result.details.get("cause", "Intent shift detected")
            return (
                True,
                f"VETO: {intent_details}"
            )
        
        # Layer 3 veto: Canary token leaked
        if self.layer3_veto and layer3_result.normalized_score == 100.0:
            return (
                True,
                "VETO: Canary token extraction detected - prompt injection confirmed"
            )
        
        # Combined veto: Multiple layers indicate high risk
        layers_high_risk = sum([
            layer0_result.normalized_score > 70,
            layer1_result.normalized_score > 70,
            layer2_result.normalized_score > 70,
            layer3_result.normalized_score > 0,
        ])
        
        if layers_high_risk >= 2:
            return (
                True,
                "VETO: Multiple layers detected high-risk patterns"
            )
        
        return (False, "")
    
    def _generate_rejection_reason(
        self,
        final_score: float,
        layer0_score: float,
        layer1_score: float,
        layer2_score: float,
        layer3_score: float
    ) -> str:
        """
        Generate human-readable rejection reason.
        
        Args:
            final_score: Final weighted score
            layer0_score: Layer 0 score
            layer1_score: Layer 1 score
            layer2_score: Layer 2 score
            layer3_score: Layer 3 score
            
        Returns:
            Rejection reason string
        """
        reasons = []
        
        if layer0_score > 50:
            reasons.append(f"intent shift detected (score: {layer0_score:.1f})")
        
        if layer1_score > 50:
            reasons.append(f"suspicious patterns detected (score: {layer1_score:.1f})")
        
        if layer2_score > 50:
            reasons.append(f"ML classifier flagged as injection (score: {layer2_score:.1f})")
        
        if layer3_score > 0:
            reasons.append("canary token test failed")
        
        reason_text = ", ".join(reasons) if reasons else "risk threshold exceeded"
        
        return f"Prompt rejected (final score: {final_score:.1f}): {reason_text}"
