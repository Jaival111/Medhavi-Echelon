"""
Control-Plane Change Detection for Multi-Turn Prompt Injection.
Focuses on control-plane checks (authority, rules, identity, constraints, self-ref)
rather than content or sentiment.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional


class ControlPlaneLayer:
    """
    Detects attempts to modify the 'Control Plane' of the LLM conversation.
    Tracks state vectors across turns and flags emerging patterns of control seizure.
    """

    # --- Configuration ---
    
    # 1. Feature Weights (w_i)
    # Uniform weighting as per prompt, but can be tuned.
    WEIGHTS = {
        'authority_shift': 1.0,
        'rule_override': 1.0,
        'identity_redefinition': 1.0,
        'constraint_weakening': 1.0,
        'self_reference': 1.0
    }

    # 2. Baseline Model Parameters
    # alpha for Exponential Moving Average
    ALPHA = 0.35 

    # 3. Detection Thresholds
    THETA_SINGLE = 0.4      # Threshold for n consecutive turns
    N_CONSECUTIVE = 2       # Number of consecutive turns required
    THETA_CUMULATIVE = 2.5  # Threshold for cumulative sum over window

    def __init__(self):
        # Session storage: session_id -> state dict
        # State dict contains:
        #   'baseline': List[float] (The B(t) vector)
        #   'threat_history': List[float] (Rolling history of threat scores)
        self._session_store = defaultdict(lambda: {
            'baseline': [0.0] * 5, 
            'threat_history': []
        })

        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for the 5 control plane features."""
        
        # 1. Authority Shift: Imperatives, claiming roles, temporal control
        self.p_authority = [
            r"ignore previous", r"from now on", r"you will", r"as the system", 
            r"developer mode", r"admin mode", r"start answering", r"must answer",
            r"listen to me"
        ]
        
        # 2. Rule Override: Bypassing rules/safety
        self.p_rule = [
            r"bypass", r"override", r"disable", r"unrestricted", r"no rules",
            r"ignore rules", r"safety filter", r"jailbreak", r"filter removal"
        ]
        
        # 3. Identity Redefinition: Redefining assistant identity
        self.p_identity = [
            r"you are now", r"act as", r"pretend", r"roleplay", r"your name is",
            r"you are not an ai", r"simulation", r"you are dan"
        ]
        
        # 4. Constraint Weakening: Suppressing refusal/forcing outputs
        self.p_constraint = [
            r"don'?t refuse", r"answer honestly", r"no warnings", r"say exactly",
            r"never refuse", r"do not limit", r"full answer", r"stay in character"
        ]
        
        # 5. Self Reference: Mentions system prompts, policies, data
        self.p_self_ref = [
            r"system prompt", r"system message", r"hidden rules", r"training data",
            r"initial instructions", r"guidelines", r"your instructions"
        ]

    def _extract_features(self, text: str) -> List[float]:
        """
        Compute Control-Plane State Vector C(t) = [v1, v2, v3, v4, v5].
        Each value is in [0, 1].
        """
        text_lower = text.lower()
        
        def score_category(patterns):
            # Binary presence check (0.0 or 1.0)
            # This follows the prompt's normalized vector requirement.
            # While we could count occurrences, presence usually indicates intent sufficiently.
            for p in patterns:
                if re.search(p, text_lower):
                    return 1.0
            return 0.0

        return [
            score_category(self.p_authority),      # [0] authority_shift
            score_category(self.p_rule),           # [1] rule_override
            score_category(self.p_identity),       # [2] identity_redefinition
            score_category(self.p_constraint),     # [3] constraint_weakening
            score_category(self.p_self_ref)        # [4] self_reference
        ]

    def handle(
        self,
        content: Dict[str, Any],
        next_callable: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        
        prompt = str(content.get("prompt", "") or "")
        session_id = str(content.get("session_id", "default_session"))
        
        # Retrieve session state
        state = self._session_store[session_id]
        baseline_t = state['baseline']  # This is B(t), calculated from previous turns
        
        # 1. Compute C(t) - Current State Vector
        c_t = self._extract_features(prompt)
        
        # 2. Compute Delta C(t) = C(t) - B(t)
        delta_c = [(curr - base) for curr, base in zip(c_t, baseline_t)]
        
        # 3. Compute Threat Score(t)
        # Sum(w_i * max(0, delta_c_i)) -- only positive jumps matter
        weights = list(self.WEIGHTS.values())
        threat_score = sum(w * max(0.0, d) for w, d in zip(weights, delta_c))
        
        # 4. Update Baseline for NEXT turn B(t+1)
        # B(t+1) = alpha * C(t) + (1 - alpha) * B(t)
        next_baseline = [
            self.ALPHA * curr + (1.0 - self.ALPHA) * base 
            for curr, base in zip(c_t, baseline_t)
        ]
        state['baseline'] = next_baseline
        
        # 5. Logic: Check Escalation
        history = state['threat_history']
        history.append(threat_score)
        
        # Keep window (e.g., last 5 turns) for cumulative check
        window_size = 5
        if len(history) > window_size:
            history.pop(0)
            
        is_flagged = False
        cause = []

        # Condition A: ThreatScore(t) > theta for n consecutive turns
        if len(history) >= self.N_CONSECUTIVE:
            recent_scores = history[-self.N_CONSECUTIVE:]
            if all(s > self.THETA_SINGLE for s in recent_scores):
                is_flagged = True
                cause.append(f"Consecutive high threat scores detected {recent_scores}")

        # Condition B: Cumulative sum > Theta
        cumulative_score = sum(history)
        if cumulative_score > self.THETA_CUMULATIVE:
            is_flagged = True
            cause.append(f"Cumulative threat score ({cumulative_score:.2f}) exceeded threshold")

        # 6. Construct Analysis Payload
        analysis_entry = {
            "current_vector": c_t,
            "baseline_vector": [round(b, 2) for b in baseline_t],
            "delta": [round(d, 2) for d in delta_c],
            "threat_score": round(threat_score, 2),
            "flagged": is_flagged,
            "cause": "; ".join(cause) if cause else "Safe"
        }
        
        # Inject into content
        analysis = content.setdefault("analysis", {})
        if isinstance(analysis, dict):
            analysis["control_plane_layer"] = analysis_entry
        else:
            content["analysis"] = {"control_plane_layer": analysis_entry}

        # 7. Blocking Action
        if is_flagged:
             content["blocked"] = True
             content["response"] = "I cannot fulfill this request as it violates control-plane policies."
             return content

        if next_callable:
            return next_callable(content)
        
        return content

    def analyze(self, prompt: str = None, messages: list = None, session_id: str = "default_session") -> Dict[str, Any]:
        """
        Analyze control plane threats for pipeline integration.
        
        Args:
            prompt: Single prompt string (legacy support)
            messages: List of message dicts with 'role' and 'content' keys
            session_id: Session identifier for tracking multi-turn attacks
            
        Returns:
            Dict containing control plane analysis with threat score and flagged status
        """
        # Build content dict
        content = {"session_id": session_id}
        
        if messages:
            # Extract last user message from message history
            user_messages = [msg.get("content", "") for msg in messages if msg.get("role") == "user"]
            content["prompt"] = user_messages[-1] if user_messages else ""
        elif prompt:
            content["prompt"] = prompt
        else:
            # No input provided
            return {
                "current_vector": [0.0] * 5,
                "baseline_vector": [0.0] * 5,
                "delta": [0.0] * 5,
                "threat_score": 0.0,
                "flagged": False,
                "cause": "No input provided"
            }
        
        # Run through the handler
        result = self.handle(content)
        
        # Extract and return the analysis
        analysis = result.get("analysis", {}).get("control_plane_layer", {})
        return analysis
