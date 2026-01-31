"""Keyword dictionary utilities for the heuristic layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional


class KeywordDictionary:
    """Provides keyword-to-score mappings for heuristic detection.

    The backing store is intentionally simple: call ``configure`` once at
    startup with your keyword payload (mirroring the PHP static dictionary)
    and the mapping will be available to the rest of the pipeline. Keys are
    normalised to lowercase to match the behaviour of the original
    implementation where lookups were case-insensitive.
    """

    _keyword_map: Dict[str, float] = {}
    _default_path: Path = Path(__file__).resolve().parent.parent / "keywords.json"
    _is_configured: bool = False

    @classmethod
    def configure(cls, keyword_map: Dict[str, float]) -> None:
        """Register the keyword map used by the detector.

        Args:
            keyword_map: Mapping of keyword/phrase (any casing) to numeric
                score. Values are coerced to ``float`` for consistency with
                the PHP implementation.
        """

        cls._keyword_map = {key.lower(): float(value) for key, value in keyword_map.items()}
        cls._is_configured = True

    @classmethod
    def load_from_file(cls, path: Optional[Path] = None) -> None:
        """Load keyword definitions from a JSON file and configure the store."""

        json_path = Path(path) if path is not None else cls._default_path
        with json_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        if not isinstance(data, dict):
            raise ValueError(f"Keyword payload in {json_path} must be a JSON object")

        cls.configure(data)

    @classmethod
    def get_list(cls) -> Dict[str, float]:
        """Return the currently configured keyword dictionary.

        Returns:
            A dictionary keyed by lowercase keyword/phrase with float scores.
        """

        if not cls._is_configured and cls._default_path.exists():
            cls.load_from_file()

        return cls._keyword_map
