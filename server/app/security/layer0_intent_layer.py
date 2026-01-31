"""Intent analysis layer using VADER sentiment for semantic consistency checking."""

from __future__ import annotations

import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from typing import Dict, Optional, Callable, Any

class IntentLayer:
    """
    Analyzes the 'intent' of a prompt using VADER Sentiment Analysis (-1 to 1).
    Flags requests where the intent shifts drastically compared to the previous turn,
    indicating potential Context Switching attacks or abrupt jailbreaks.
    """

    MAX_INTENT_SHIFT = 0.5  # Threshold for flagging drastic changes

    def __init__(self):
        # Ensure VADER lexicon is available
        try:
            nltk.data.find('sentiment/vader_lexicon.zip')
        except LookupError:
            nltk.download('vader_lexicon', quiet=True)
            
        self.analyzer = SentimentIntensityAnalyzer()
        # In-memory store for demo purposes. 
        # In production, use Redis/DB keyed by session_id.
        self._session_history: Dict[str, float] = {}

    def handle(
        self,
        content: Dict[str, Any],
        next_callable: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Calculates sentiment-based intent score [-1, 1].
        Compares with previous prompt's score for the same session.
        """
        
        # Extract prompt from either direct prompt or messages
        if "messages" in content:
            # Get all user messages and concatenate them
            messages = content.get("messages", [])
            user_messages = [msg.get("content", "") for msg in messages if msg.get("role") == "user"]
            prompt = " ".join(user_messages) if user_messages else ""
        else:
            prompt = str(content.get("prompt", "") or "")
        
        session_id = str(content.get("session_id", "default_session"))
        
        # 1. Calculate Current Intent Score (Compound Sentiment)
        # Score is between -1 (Most Negative/Malicious-sounding) and +1 (Most Positive/Safe-sounding)
        scores = self.analyzer.polarity_scores(prompt)
        current_score = scores['compound']
        
        # 2. Retrieve Previous Score
        previous_score = self._session_history.get(session_id, current_score) # Default to current on first run
        
        # 3. Calculate Shift
        intent_shift = abs(current_score - previous_score)
        
        # 4. Update History
        self._session_history[session_id] = current_score
        
        # 5. Analysis Logic
        is_flagged = intent_shift > self.MAX_INTENT_SHIFT
        
        analysis_entry = {
            "score": current_score,
            "previous_score": previous_score,
            "shift": intent_shift,
            "flagged": is_flagged,
            "cause": (
                f"Drastic intent shift detected ({intent_shift:.2f} > {self.MAX_INTENT_SHIFT}). Potential context switch attack."
                if is_flagged
                else "Intent consistent."
            )
        }

        # Attach to analysis payload
        analysis = content.setdefault("analysis", {})
        if isinstance(analysis, dict):
            analysis["intent_layer"] = analysis_entry
        else:
            content["analysis"] = {"intent_layer": analysis_entry}

        # 6. Block or Pass
        if is_flagged:
            # Short-circuit: directly refuse answer
            content["response"] = "Sorry, I cannot answer this as the context changed too abruptly."
            content["blocked"] = True
            return content

        if next_callable is None:
            return content

        return next_callable(content)
    
    def analyze(self, prompt: str = None, messages: list = None, session_id: str = "default_session") -> Dict[str, Any]:
        """
        Analyze intent for pipeline integration.
        
        Args:
            prompt: Single prompt string (legacy support)
            messages: List of message dicts with 'role' and 'content' keys
            session_id: Session identifier for tracking intent shifts
            
        Returns:
            Dict containing intent analysis with score and flagged status
        """
        # Build content dict
        content = {"session_id": session_id}
        
        if messages:
            content["messages"] = messages
        elif prompt:
            content["prompt"] = prompt
        else:
            # No input provided
            return {
                "score": 0.0,
                "previous_score": 0.0,
                "shift": 0.0,
                "flagged": False,
                "cause": "No input provided"
            }
        
        # Run through the handler
        result = self.handle(content)
        
        # Extract and return the analysis
        analysis = result.get("analysis", {}).get("intent_layer", {})
        return analysis
