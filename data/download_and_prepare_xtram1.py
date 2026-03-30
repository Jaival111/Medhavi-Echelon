#!/usr/bin/env python3
"""
Prepare xTRam1/safe-guard-prompt-injection into standardized CSV splits.

Outputs:
- data/processed/xtram1_train.csv
- data/processed/xtram1_val.csv
- data/processed/xtram1_test.csv
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
from datasets import ClassLabel, Dataset, DatasetDict, load_dataset
from sklearn.model_selection import train_test_split

TEXT_CANDIDATES = ["text", "prompt", "content", "instruction", "query", "input"]
LABEL_CANDIDATES = ["label", "labels", "class", "target", "is_injection", "category"]
POSITIVE_HINTS = {"inject", "attack", "unsafe", "malicious", "jailbreak", "override"}
NEGATIVE_HINTS = {"safe", "benign", "normal", "clean", "harmless", "not injection"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and prepare xTRam1 prompt-injection dataset."
    )
    parser.add_argument(
        "--dataset",
        default="xTRam1/safe-guard-prompt-injection",
        help="Hugging Face dataset name",
    )
    parser.add_argument(
        "--output-dir",
        default="data/processed",
        help="Directory to store processed CSV splits",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for splitting")
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    return parser.parse_args()


def pick_column(columns: Iterable[str], candidates: Iterable[str], kind: str) -> str:
    cols = list(columns)
    lower_lookup = {col.lower(): col for col in cols}

    for candidate in candidates:
        if candidate in cols:
            return candidate

    for candidate in candidates:
        lowered = candidate.lower()
        if lowered in lower_lookup:
            return lower_lookup[lowered]

    raise ValueError(f"Could not infer {kind} column from: {cols}")


def extract_class_names(dataset_obj: Dataset | DatasetDict, label_col: str) -> Optional[list[str]]:
    candidates: list[Dataset] = []

    if isinstance(dataset_obj, DatasetDict):
        candidates.extend(dataset_obj.values())
    elif isinstance(dataset_obj, Dataset):
        candidates.append(dataset_obj)

    for split in candidates:
        feature = split.features.get(label_col)
        if isinstance(feature, ClassLabel):
            return list(feature.names)

    return None


def map_label(raw_value: object, class_names: Optional[list[str]]) -> int:
    if isinstance(raw_value, float) and pd.isna(raw_value):
        raise ValueError("Encountered NaN label")

    if class_names is not None and isinstance(raw_value, (int, float)):
        idx = int(raw_value)
        if 0 <= idx < len(class_names):
            raw_value = class_names[idx]

    if isinstance(raw_value, str):
        text = raw_value.strip().lower()
        if text in {"0", "safe", "benign", "clean", "normal", "negative", "not_injection"}:
            return 0
        if text in {"1", "injection", "attack", "unsafe", "malicious", "positive", "prompt_injection"}:
            return 1
        if any(token in text for token in POSITIVE_HINTS):
            return 1
        if any(token in text for token in NEGATIVE_HINTS):
            return 0

    if isinstance(raw_value, (int, float)):
        value = int(raw_value)
        if value in {0, 1}:
            return value

    raise ValueError(f"Unsupported label value: {raw_value!r}")


def normalize_text_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def load_dataset_as_frame(dataset_name: str) -> tuple[pd.DataFrame, Optional[list[str]], str, str]:
    ds = load_dataset(dataset_name)

    if isinstance(ds, DatasetDict):
        frames = []
        for split_name, split_ds in ds.items():
            split_frame = split_ds.to_pandas()
            split_frame["original_split"] = split_name
            frames.append(split_frame)
        merged = pd.concat(frames, ignore_index=True)
        sample_ds: Dataset = next(iter(ds.values()))
    elif isinstance(ds, Dataset):
        merged = ds.to_pandas()
        merged["original_split"] = "train"
        sample_ds = ds
    else:
        raise TypeError(f"Unexpected dataset type: {type(ds)}")

    text_col = pick_column(merged.columns, TEXT_CANDIDATES, "text")
    label_col = pick_column(merged.columns, LABEL_CANDIDATES, "label")

    class_names = extract_class_names(ds, label_col)

    if class_names is None:
        feature = sample_ds.features.get(label_col)
        if isinstance(feature, ClassLabel):
            class_names = list(feature.names)

    return merged, class_names, text_col, label_col


def normalize_frame(raw_df: pd.DataFrame, text_col: str, label_col: str, class_names: Optional[list[str]]) -> pd.DataFrame:
    normalized = pd.DataFrame()
    normalized["text"] = raw_df[text_col].astype(str).str.strip()
    normalized["label"] = raw_df[label_col].apply(lambda value: map_label(value, class_names))
    normalized["source"] = "xtram1_safe_guard_prompt_injection"

    normalized = normalized[normalized["text"] != ""].reset_index(drop=True)

    normalized["text_key"] = normalized["text"].map(normalize_text_key)
    before = len(normalized)
    normalized = normalized.drop_duplicates(subset=["text_key"]).drop(columns=["text_key"])
    after = len(normalized)

    print(f"Removed duplicates: {before - after}")
    return normalized


def stratified_split(
    df: pd.DataFrame,
    seed: int,
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    total = train_ratio + val_ratio + test_ratio
    if abs(total - 1.0) > 1e-9:
        raise ValueError("train_ratio + val_ratio + test_ratio must equal 1.0")

    train_df, temp_df = train_test_split(
        df,
        test_size=(1.0 - train_ratio),
        random_state=seed,
        stratify=df["label"],
    )

    test_share_of_temp = test_ratio / (val_ratio + test_ratio)
    val_df, test_df = train_test_split(
        temp_df,
        test_size=test_share_of_temp,
        random_state=seed,
        stratify=temp_df["label"],
    )

    return train_df.reset_index(drop=True), val_df.reset_index(drop=True), test_df.reset_index(drop=True)


def print_distribution(name: str, frame: pd.DataFrame) -> None:
    counts = frame["label"].value_counts().sort_index().to_dict()
    total = len(frame)
    safe = counts.get(0, 0)
    injection = counts.get(1, 0)
    print(
        f"{name}: rows={total}, safe={safe} ({safe / total:.2%}), "
        f"injection={injection} ({injection / total:.2%})"
    )


def main() -> None:
    args = parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading dataset: {args.dataset}")
    raw_df, class_names, text_col, label_col = load_dataset_as_frame(args.dataset)
    print(f"Detected columns -> text: '{text_col}', label: '{label_col}'")

    normalized_df = normalize_frame(raw_df, text_col, label_col, class_names)

    train_df, val_df, test_df = stratified_split(
        normalized_df,
        seed=args.seed,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
    )

    train_path = output_dir / "xtram1_train.csv"
    val_path = output_dir / "xtram1_val.csv"
    test_path = output_dir / "xtram1_test.csv"

    train_df.to_csv(train_path, index=False)
    val_df.to_csv(val_path, index=False)
    test_df.to_csv(test_path, index=False)

    print_distribution("Train", train_df)
    print_distribution("Val", val_df)
    print_distribution("Test", test_df)

    print("Saved:")
    print(f"- {train_path}")
    print(f"- {val_path}")
    print(f"- {test_path}")


if __name__ == "__main__":
    main()
