"""Regex compilation logic mirroring the PHP PatternCompiler."""

from __future__ import annotations

import sys
import csv
# Fix for Windows: use a smaller but still large enough limit
try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    # Windows limitation: use maximum safe value for 32-bit signed integer
    csv.field_size_limit(int(2**31 - 1))
import re
from threading import Lock
from pathlib import Path
from typing import Dict, Optional, Pattern, Tuple

from .keyword_dictionary import KeywordDictionary
from .models import LayerResult

class PatternCompiler:
    """Builds and caches a single optimised regex for keyword detection."""

    _cache_lock: Lock = Lock()
    _cached_key: Optional[Tuple[str, ...]] = None
    _cached_pattern: Optional[Pattern[str]] = None

    def get_compiled_regex(self) -> Optional[Pattern[str]]:
        """Return a compiled regex for all currently registered keywords.

        The regex is cached and rebuilt only when the underlying dictionary
        changes. Keywords are sorted by length (descending) to ensure longest
        phrases match first, replicating the PHP behaviour that leveraged
        ``usort`` with string length.
        """

        keyword_map = KeywordDictionary.get_list()
        if not keyword_map:
            return None

        cache_key = tuple(sorted(keyword_map.keys(), key=lambda item: (-len(item), item)))

        with self._cache_lock:
            if cache_key == self._cached_key and self._cached_pattern is not None:
                return self._cached_pattern

            pattern = self._build_pattern(keyword_map)
            self._cached_key = cache_key
            self._cached_pattern = pattern
            return pattern

    @staticmethod
    def _build_pattern(keyword_map: Dict[str, float]) -> Pattern[str]:
        """Construct the compiled regex used for keyword detection."""

        # Sort by length (DESC) to emulate the PHP usort-based ordering
        sorted_keywords = sorted(keyword_map.keys(), key=len, reverse=True)
        escaped = [re.escape(keyword) for keyword in sorted_keywords]
        pattern = rf"\b(?:{'|'.join(escaped)})\b"
        return re.compile(pattern, re.IGNORECASE)


# ---------------------------------------------------------------------
# Keyword + Pattern Utilities
# ---------------------------------------------------------------------

def load_keywords_from_file(file_path: Optional[Path] = None) -> None:
    """Load keywords from a JSON file into the dictionary."""
    if file_path is None:
        file_path = Path(__file__).parent / "keywords.json"

    KeywordDictionary.load_from_file(file_path)
    print(f"Loaded {len(KeywordDictionary.get_list())} keywords from {file_path}")


def get_keyword_mapping() -> Dict[str, float]:
    """Get the current keyword mapping."""
    return KeywordDictionary.get_list()


def get_compiled_regex() -> Optional[Pattern]:
    """Get the compiled regex pattern for keyword detection."""
    compiler = PatternCompiler()
    return compiler.get_compiled_regex()


def detect_keywords(text: str) -> Dict[str, float]:
    """Detect keywords in the given text and return their scores."""
    pattern = get_compiled_regex()
    if not pattern:
        return {}

    keyword_map = get_keyword_mapping()
    matches = pattern.findall(text.lower())

    detected = {}
    for match in matches:
        if match in keyword_map:
            detected[match] = keyword_map[match]

    return detected


def calculate_heuristic_score(text: str) -> float:
    """Calculate heuristic score based on detected keywords."""
    detected = detect_keywords(text)
    return sum(detected.values()) if detected else 0.0


# ---------------------------------------------------------------------
# HeuristicAnalyzer Class
# ---------------------------------------------------------------------

class HeuristicAnalyzer:
    """
    Layer 1: Heuristic-based prompt injection detection.
    Uses pattern matching with weighted keywords.
    """
    
    def __init__(self, keywords_file: Optional[Path] = None):
        """
        Initialize the heuristic analyzer.
        
        Args:
            keywords_file: Optional path to keywords file. If None, uses default.
        """
        # Load keywords on initialization
        load_keywords_from_file(keywords_file)
        self.compiler = PatternCompiler()
    
    def analyze(self, text: str) -> LayerResult:
        """
        Analyze text for prompt injection indicators.
        
        Args:
            text: User prompt to analyze
            
        Returns:
            LayerResult with score and detected keywords
        """
        # Detect keywords and calculate raw score
        detected_keywords = detect_keywords(text)
        raw_score = calculate_heuristic_score(text)
        
        # Normalize score to 0-100 range
        # Assuming raw scores typically range from 0-20, adjust as needed
        max_expected_score = 20.0
        normalized_score = min((raw_score / max_expected_score) * 100, 100.0)
        
        # Determine if passed (inverse: high score = high risk = fail)
        passed = normalized_score < 50.0
        
        return LayerResult(
            score=raw_score,
            normalized_score=normalized_score,
            passed=passed,
            details={
                "detected_keywords": detected_keywords,
                "keyword_count": len(detected_keywords),
                "total_weight": raw_score,
            }
        )
