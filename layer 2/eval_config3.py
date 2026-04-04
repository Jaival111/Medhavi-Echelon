#!/usr/bin/env python3
"""
Evaluate Jaival Config 3 runs:
- Hard-negative ablation comparison
- OOD-style obfuscation subset evaluation
- Calibration analysis (confidence vs correctness buckets)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import auc, confusion_matrix, f1_score, precision_recall_curve
from transformers import AutoModelForSequenceClassification, AutoTokenizer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Jaival Config 3 artifacts")
    parser.add_argument("--results-json", default="layer 2/results_config3.json")
    parser.add_argument("--data-dir", default="data/processed")
    parser.add_argument("--report-json", default="layer 2/comparison_config3.json")
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--calibration-bins", type=int, default=10)
    return parser.parse_args()


def load_test(data_dir: Path) -> pd.DataFrame:
    path = data_dir / "xtram1_test.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    df = pd.read_csv(path)
    if "text" not in df.columns or "label" not in df.columns:
        raise ValueError("xtram1_test.csv must contain text,label columns")
    df["text"] = df["text"].astype(str)
    df["label"] = df["label"].astype(int)
    return df


def run_probs(
    model: torch.nn.Module,
    tokenizer: Any,
    texts: list[str],
    batch_size: int,
    max_length: int,
) -> np.ndarray:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()
    probs: list[float] = []
    with torch.no_grad():
        for offset in range(0, len(texts), batch_size):
            batch = texts[offset : offset + batch_size]
            encoded = tokenizer(
                batch,
                return_tensors="pt",
                truncation=True,
                padding=True,
                max_length=max_length,
            )
            encoded = {k: v.to(device) for k, v in encoded.items()}
            logits = model(**encoded).logits.float()
            p = torch.softmax(logits, dim=-1)[:, 1].detach().cpu().numpy().tolist()
            probs.extend(p)
    return np.array(probs, dtype=np.float32)


def compute_metrics(labels: np.ndarray, probs: np.ndarray, threshold: float) -> dict[str, float | int]:
    preds = (probs >= threshold).astype(int)
    precision, recall, _ = precision_recall_curve(labels, probs)
    pr_auc = auc(recall, precision)
    tn, fp, fn, tp = confusion_matrix(labels, preds, labels=[0, 1]).ravel()
    return {
        "f1_injection": float(f1_score(labels, preds, pos_label=1)),
        "f1_macro": float(f1_score(labels, preds, average="macro")),
        "f1_micro": float(f1_score(labels, preds, average="micro")),
        "pr_auc": float(pr_auc),
        "fp_rate_safe": float(fp / max(tn + fp, 1)),
        "tp": int(tp),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
    }


def mark_obfuscated_subset(df: pd.DataFrame) -> pd.Series:
    patterns = [
        r"\bbase64\b",
        r"\brot13\b",
        r"\bhex\b",
        r"\bdecode\b",
        r"\bcipher\b",
        r"\bobfuscat",
        r"[A-Za-z0-9+/]{20,}={0,2}",
        r"(?:0x[0-9a-fA-F]{2,}\s*){4,}",
    ]
    joined = "|".join(patterns)
    return df["text"].str.lower().str.contains(joined, regex=True)


def calibration_report(labels: np.ndarray, probs: np.ndarray, bins: int) -> dict[str, Any]:
    conf = np.maximum(probs, 1.0 - probs)
    preds = (probs >= 0.5).astype(int)
    correct = (preds == labels).astype(int)
    edges = np.linspace(0.0, 1.0, bins + 1)
    rows: list[dict[str, Any]] = []
    ece = 0.0
    n = max(len(labels), 1)

    for i in range(bins):
        lo = edges[i]
        hi = edges[i + 1]
        if i == bins - 1:
            mask = (conf >= lo) & (conf <= hi)
        else:
            mask = (conf >= lo) & (conf < hi)
        count = int(mask.sum())
        if count == 0:
            rows.append(
                {
                    "bin": i,
                    "range": [float(lo), float(hi)],
                    "count": 0,
                    "avg_confidence": None,
                    "accuracy": None,
                    "abs_gap": None,
                }
            )
            continue
        avg_conf = float(conf[mask].mean())
        acc = float(correct[mask].mean())
        gap = abs(avg_conf - acc)
        ece += (count / n) * gap
        rows.append(
            {
                "bin": i,
                "range": [float(lo), float(hi)],
                "count": count,
                "avg_confidence": avg_conf,
                "accuracy": acc,
                "abs_gap": float(gap),
            }
        )
    return {"ece": float(ece), "bins": rows}


def evaluate_checkpoint(
    checkpoint_dir: Path,
    test_df: pd.DataFrame,
    threshold: float,
    batch_size: int,
    max_length: int,
    calibration_bins: int,
) -> dict[str, Any]:
    tokenizer = AutoTokenizer.from_pretrained(str(checkpoint_dir))
    model = AutoModelForSequenceClassification.from_pretrained(str(checkpoint_dir))

    labels = test_df["label"].to_numpy()
    texts = test_df["text"].tolist()
    probs = run_probs(model, tokenizer, texts, batch_size, max_length)

    full_metrics = compute_metrics(labels, probs, threshold)

    ood_mask = mark_obfuscated_subset(test_df).to_numpy()
    if int(ood_mask.sum()) > 0:
        ood_metrics = compute_metrics(labels[ood_mask], probs[ood_mask], threshold)
        ood_size = int(ood_mask.sum())
    else:
        ood_metrics = None
        ood_size = 0

    calibration = calibration_report(labels, probs, bins=calibration_bins)

    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return {
        "full_test_metrics": full_metrics,
        "ood_obfuscated_subset_size": ood_size,
        "ood_obfuscated_metrics": ood_metrics,
        "calibration": calibration,
    }


def best_seed_from_mode(mode_payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    runs = mode_payload["runs"]
    best_seed = max(runs, key=lambda seed: runs[seed]["test_f1_injection"])
    return best_seed, runs[best_seed]


def main() -> None:
    args = parse_args()
    results_path = Path(args.results_json)
    if not results_path.exists():
        raise FileNotFoundError(f"Missing results JSON: {results_path}")
    payload = json.loads(results_path.read_text(encoding="utf-8"))

    required_modes = ["without_hard_negatives", "with_hard_negatives"]
    for mode in required_modes:
        if mode not in payload:
            raise ValueError(
                f"Missing mode '{mode}' in results JSON. Run train script for both ablations first."
            )

    test_df = load_test(Path(args.data_dir))

    out: dict[str, Any] = {"owner": "Jaival", "modes": {}}
    for mode in required_modes:
        best_seed, best_seed_payload = best_seed_from_mode(payload[mode])
        checkpoint = Path(best_seed_payload["best_checkpoint_path"])
        if not checkpoint.exists():
            raise FileNotFoundError(f"Missing checkpoint for mode={mode}, seed={best_seed}: {checkpoint}")
        mode_eval = evaluate_checkpoint(
            checkpoint_dir=checkpoint,
            test_df=test_df,
            threshold=args.threshold,
            batch_size=args.batch_size,
            max_length=args.max_length,
            calibration_bins=args.calibration_bins,
        )
        out["modes"][mode] = {
            "best_seed": best_seed,
            "checkpoint": str(checkpoint),
            "aggregated_training_metrics": payload[mode]["aggregated"],
            "evaluation": mode_eval,
        }

    with_hn = out["modes"]["with_hard_negatives"]["evaluation"]["full_test_metrics"]
    without_hn = out["modes"]["without_hard_negatives"]["evaluation"]["full_test_metrics"]
    out["hard_negative_ablation_delta"] = {
        "f1_injection_delta": float(with_hn["f1_injection"] - without_hn["f1_injection"]),
        "pr_auc_delta": float(with_hn["pr_auc"] - without_hn["pr_auc"]),
        "fp_rate_safe_delta": float(with_hn["fp_rate_safe"] - without_hn["fp_rate_safe"]),
    }

    report_path = Path(args.report_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Saved Config 3 evaluation report: {report_path}")


if __name__ == "__main__":
    main()
