"""Regex compilation logic mirroring the PHP PatternCompiler."""

from __future__ import annotations

import re
from threading import Lock
from typing import Dict, Optional, Pattern, Tuple

from keyword_dictionary import KeywordDictionary

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
