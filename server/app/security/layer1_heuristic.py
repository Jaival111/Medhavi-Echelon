"""
Layer 1: Heuristic Analysis
Pattern matching against weighted keywords for prompt injection detection
"""
import re
from typing import Dict, Tuple
from .models import LayerResult


class HeuristicAnalyzer:
    """
    Heuristic-based prompt injection detector using weighted keyword patterns.
    Compiled regex patterns ensure O(n) performance.
    """
    
    # Weighted keyword patterns derived from statistical analysis of attack datasets
    KEYWORD_PATTERNS = {
        # High-risk instruction injections (weight: 10)
        "ignore_instructions": {
            "weight": 10,
            "patterns": [
                r"\bignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions|commands|prompts|rules)",
                r"\bdisregard\s+(all\s+)?(previous|prior|above)\s+(instructions|commands)",
                r"\bforget\s+(all\s+)?(previous|prior|above)\s+(instructions|commands)",
                r"\boverride\s+(all\s+)?(previous|system)\s+(instructions|settings)",
            ]
        },
        
        # System prompt extraction (weight: 10)
        "system_extraction": {
            "weight": 10,
            "patterns": [
                r"\b(show|reveal|display|print|output|tell)\s+(me\s+)?(your|the)\s+(system\s+)?(prompt|instructions|rules)",
                r"\bwhat\s+(are|is)\s+(your|the)\s+(system\s+)?(prompt|instructions|rules)",
                r"\b(repeat|echo|copy)\s+(your|the)\s+(system\s+)?(prompt|instructions)",
                r"\bshow\s+me\s+what\s+you\s+were\s+told",
            ]
        },
        
        # Role-playing attacks (weight: 8)
        "role_play": {
            "weight": 8,
            "patterns": [
                r"\byou\s+are\s+now\s+(a|an)\s+",
                r"\bpretend\s+(you\s+are|to\s+be)\s+(a|an)",
                r"\bact\s+as\s+(a|an|if)",
                r"\bsimulate\s+(being\s+)?(a|an)",
                r"\bbecome\s+(a|an)",
                r"\btake\s+on\s+the\s+role\s+of",
            ]
        },
        
        # Permission escalation (weight: 9)
        "permission_escalation": {
            "weight": 9,
            "patterns": [
                r"\byou\s+(can|may|are\s+allowed\s+to)\s+(now\s+)?(ignore|bypass|override)",
                r"\benable\s+(admin|developer|debug)\s+mode",
                r"\bactivate\s+(special|hidden|secret)\s+(mode|features)",
                r"\bunlock\s+(all\s+)?(features|capabilities|restrictions)",
                r"\bdisable\s+(all\s+)?(safety|security|filters|restrictions)",
            ]
        },
        
        # Jailbreak attempts (weight: 10)
        "jailbreak": {
            "weight": 10,
            "patterns": [
                r"\bDAN\s+mode",
                r"\bdo\s+anything\s+now",
                r"\bwithout\s+(any\s+)?(restrictions|limitations|filters)",
                r"\bno\s+(ethical|moral)\s+(guidelines|constraints|restrictions)",
                r"\buncensored\s+(mode|version|response)",
            ]
        },
        
        # Encoding/obfuscation attempts (weight: 7)
        "encoding": {
            "weight": 7,
            "patterns": [
                r"\b(base64|hex|rot13|ascii)\s+(decode|encode)",
                r"\%[0-9a-fA-F]{2}",  # URL encoding
                r"\\x[0-9a-fA-F]{2}",  # Hex encoding
                r"\\u[0-9a-fA-F]{4}",  # Unicode escape
            ]
        },
        
        # Delimiter/separator manipulation (weight: 8)
        "delimiter_manipulation": {
            "weight": 8,
            "patterns": [
                r"[-=_*#]{10,}",  # Long separator lines
                r"\[SYSTEM\]|\[\/SYSTEM\]",
                r"\[INST\]|\[\/INST\]",
                r"<\|im_start\|>|<\|im_end\|>",
                r"###\s+(System|User|Assistant)",
            ]
        },
        
        # Hypothetical scenarios (weight: 6)
        "hypothetical": {
            "weight": 6,
            "patterns": [
                r"\bhypothetically",
                r"\blet'?s\s+say\s+(that\s+)?",
                r"\bimagine\s+(if|that)",
                r"\bsuppose\s+(that\s+)?",
                r"\bwhat\s+if\s+",
                r"\bin\s+a\s+world\s+where",
            ]
        },
        
        # Indirect command injection (weight: 7)
        "indirect_injection": {
            "weight": 7,
            "patterns": [
                r"\btranslate\s+this\s+and\s+then\s+",
                r"\bsummarize.*then\s+(ignore|execute|run)",
                r"\bafter\s+(reading|processing).*ignore",
                r"\bfirst.*then\s+(ignore|disregard|forget)",
            ]
        },
        
        # Code execution attempts (weight: 9)
        "code_execution": {
            "weight": 9,
            "patterns": [
                r"\bexec\s*\(",
                r"\beval\s*\(",
                r"\bsystem\s*\(",
                r"\bos\.system",
                r"\bsubprocess\.",
                r"\b__import__\s*\(",
            ]
        },
        
        # Token/secret extraction (weight: 10)
        "secret_extraction": {
            "weight": 10,
            "patterns": [
                r"\b(api[_\s]?key|secret[_\s]?key|password|token|credential)",
                r"\bshow\s+(me\s+)?(the\s+)?(hidden|secret|private)\s+",
                r"\bextract\s+(the\s+)?(secret|token|key)",
            ]
        },
        
        # Payload markers (weight: 8)
        "payload_markers": {
            "weight": 8,
            "patterns": [
                r"<script[^>]*>",
                r"javascript:",
                r"on(load|error|click)\s*=",
                r"\${.*}",  # Template injection
                r"{{.*}}",  # Template injection
            ]
        },
    }
    
    def __init__(self):
        """Initialize with compiled regex patterns for performance"""
        self.compiled_patterns = {}
        
        for category, config in self.KEYWORD_PATTERNS.items():
            self.compiled_patterns[category] = {
                "weight": config["weight"],
                "regex": [re.compile(pattern, re.IGNORECASE) for pattern in config["patterns"]]
            }
    
    def analyze(self, prompt: str) -> LayerResult:
        """
        Analyze prompt using weighted keyword matching.
        
        Args:
            prompt: User prompt to analyze
            
        Returns:
            LayerResult with cumulative risk score and details
        """
        cumulative_score = 0.0
        matches = {}
        
        # Check each category
        for category, config in self.compiled_patterns.items():
            category_matches = []
            
            for pattern in config["regex"]:
                found = pattern.findall(prompt)
                if found:
                    category_matches.extend(found)
            
            if category_matches:
                matches[category] = {
                    "count": len(category_matches),
                    "weight": config["weight"],
                    "samples": category_matches[:3]  # Store first 3 matches
                }
                # Add weighted score for this category
                cumulative_score += config["weight"] * len(category_matches)
        
        # Normalize score to 0-100 scale
        # Using sigmoid-like normalization: score grows but asymptotically approaches 100
        # Raw scores typically range 0-200 for malicious prompts
        normalized_score = min(100.0, (cumulative_score / 2.0))
        
        return LayerResult(
            score=cumulative_score,
            normalized_score=normalized_score,
            passed=normalized_score < 50.0,  # Threshold at 50
            details={
                "matches": matches,
                "total_patterns_matched": sum(m["count"] for m in matches.values()),
                "categories_triggered": len(matches),
                "raw_score": cumulative_score
            }
        )
