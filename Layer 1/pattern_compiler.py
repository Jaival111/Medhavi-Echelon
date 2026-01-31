import re
from functools import lru_cache
from typing import Dict, Any, Tuple


class KeywordDictionary:
    @staticmethod
    def get_list() -> Dict[str, Any]:
        """
        keyword -> weight (severity). Higher weight = more risky.
        Edit these keywords/weights to match your real dictionary.
        """
        return {
            "drop table": 40,
            "union select": 35,
            "or 1=1": 30,
            "sleep(": 25,
            "--": 15,
            "/*": 15,
            "*/": 15,
            "drop": 10,
            "select": 5,
        }


class PatternCompiler:
    @staticmethod
    @lru_cache(maxsize=1)
    def _compiled() -> Tuple[re.Pattern, Dict[str, int]]:
        keywords = KeywordDictionary.get_list()
        keys = list(keywords.keys())

        # Longest first to prefer long phrases
        keys.sort(key=len, reverse=True)

        escaped = [re.escape(k) for k in keys]

        # No \b boundaries (SQL tokens include punctuation like --, /*, sleep()
        pattern = r"(" + "|".join(escaped) + r")"
        regex = re.compile(pattern, flags=re.IGNORECASE)

        weights: Dict[str, int] = {}
        for k in keys:
            v = keywords.get(k)
            weights[k.lower()] = max(1, int(v)) if isinstance(v, (int, float)) else 1

        return regex, weights

    def risk_score(self, text: str) -> float:
        """
        Returns normalized risk score in [0.0, 1.0]
        """
        if not text:
            return 0.0

        regex, weights = self._compiled()
        matches = regex.findall(str(text))
        if not matches:
            return 0.0

        # Count unique matched patterns (prevents repetition from inflating too much)
        unique = {m.lower() for m in matches}
        raw_score = sum(weights.get(m, 1) for m in unique)

        # Saturating normalization: approaches 1.0 as raw_score grows
        k = 50.0
        score = 1.0 - (k / (k + raw_score))

        # Keep in [0,1] and round for CSV readability
        return round(max(0.0, min(1.0, score)), 6)

