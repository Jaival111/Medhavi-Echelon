"""
Main module integrating PatternCompiler, KeywordDictionary, and keywords.json.
Processes a CSV file and adds a heuristic score column based on keyword detection.
"""
import sys
import csv
csv.field_size_limit(sys.maxsize)
import argparse
from pathlib import Path
from typing import Dict, Optional, Pattern

from keyword_dictionary import KeywordDictionary
from pattern_compiler import PatternCompiler


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
# CSV Processing
# ---------------------------------------------------------------------

def process_csv(input_file: str, output_file: str, text_col: str) -> None:
    """Read input CSV, score text column, and write output CSV."""

    with open(input_file, "r", encoding="utf-8-sig", newline="") as infile, \
         open(output_file, "w", encoding="utf-8", newline="") as outfile:

        reader = csv.DictReader(infile)

        if text_col not in reader.fieldnames:
            raise ValueError(
                f"Column '{text_col}' not found. Available columns: {reader.fieldnames}"
            )

        fieldnames = reader.fieldnames + ["heuristic_score"]
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            text = row.get(text_col, "") or ""
            row["heuristic_score"] = round(calculate_heuristic_score(text), 4)
            writer.writerow(row)

    print(f"Scored CSV written to: {output_file}")


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Score text in a CSV file using keyword heuristics"
    )
    parser.add_argument("--input", required=True, help="Input CSV file")
    parser.add_argument("--output", required=True, help="Output CSV file")
    parser.add_argument(
        "--text-col", required=True, help="Name of column containing text"
    )
    parser.add_argument(
        "--keywords",
        help="Optional path to keywords.json (default: script directory)",
    )

    args = parser.parse_args()

    # Load keywords
    load_keywords_from_file(Path(args.keywords) if args.keywords else None)

    # Process CSV
    process_csv(args.input, args.output, args.text_col)


# ---------------------------------------------------------------------

if __name__ == "__main__":
    main()
