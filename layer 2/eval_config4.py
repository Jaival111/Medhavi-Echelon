#!/usr/bin/env python3
"""
Evaluate Deeraj Config 4 checkpoints and create submission artifacts.

Outputs:
- layer 2/comparison_baseline.json
- layer 2/failure_analysis.txt
- Updates layer 2/results_config4.json with evaluation details
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
from peft import PeftModel
from sklearn.metrics import auc, confusion_matrix, f1_score, precision_recall_curve
from transformers import AutoModelForSequenceClassification, AutoTokenizer


PATTERN_RULES: dict[str, list[str]] = {
    "role_play": ["you are", "act as", "pretend", "role-play", "roleplay"],
    "system_extraction": [
        "system prompt",
        "hidden instructions",
        "developer message",
        "internal rules",
    ],
    "obfuscation": ["base64", "rot13", "hex", "decode", "cipher", "obfuscat"],
    "override": ["ignore previous", "disregard", "bypass", "override", "jailbreak"],
    "multi_step": ["step by step", "first", "then", "after that", "multi-step"],
}


def pick_single_token_id(value: Any) -> int | None:
    if isinstance(value, int):
        return int(value)
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, int):
                return int(item)
    return None


def ensure_tokenizer_pad_token_id(tokenizer: Any) -> None:
    if isinstance(getattr(tokenizer, "pad_token_id", None), int):
        return

    candidate = pick_single_token_id(getattr(tokenizer, "eos_token_id", None))
    if candidate is None:
        candidate = pick_single_token_id(getattr(tokenizer, "bos_token_id", None))
    if candidate is None:
        candidate = pick_single_token_id(getattr(tokenizer, "unk_token_id", None))

    if candidate is not None:
        tokenizer.pad_token_id = int(candidate)


def ensure_model_pad_token_id(model: torch.nn.Module) -> None:
    current = getattr(model.config, "pad_token_id", None)
    if isinstance(current, int):
        return

    candidate = pick_single_token_id(getattr(model.config, "eos_token_id", None))
    if candidate is None:
        candidate = pick_single_token_id(getattr(model.config, "bos_token_id", None))
    if candidate is None:
        candidate = pick_single_token_id(current)

    if candidate is not None:
        model.config.pad_token_id = int(candidate)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Deeraj Config 4 checkpoints")
    parser.add_argument("--results-json", default="layer 2/results_config4.json")
    parser.add_argument("--data-dir", default="data/processed")
    parser.add_argument("--comparison-json", default="layer 2/comparison_baseline.json")
    parser.add_argument("--failure-file", default="layer 2/failure_analysis.txt")
    parser.add_argument(
        "--baseline-model",
        default="",
        help="Optional baseline encoder checkpoint/model id for same-test-set comparison",
    )
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--top-errors", type=int, default=20)
    return parser.parse_args()


def directory_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total / (1024 * 1024)


def count_params(model: torch.nn.Module) -> int:
    return int(sum(param.numel() for param in model.parameters()))


def run_predictions(
    model: torch.nn.Module,
    tokenizer: Any,
    texts: list[str],
    batch_size: int,
    max_length: int,
) -> tuple[np.ndarray, float]:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    model.eval()

    probs: list[float] = []

    if device.type == "cuda":
        torch.cuda.synchronize(device)
    start = time.perf_counter()

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
            encoded = {key: value.to(device) for key, value in encoded.items()}
            logits = model(**encoded).logits.float()
            batch_probs = torch.softmax(logits, dim=-1)[:, 1].detach().cpu().numpy().tolist()
            probs.extend(batch_probs)

    if device.type == "cuda":
        torch.cuda.synchronize(device)

    elapsed = time.perf_counter() - start
    latency_ms = (elapsed / max(len(texts), 1)) * 1000.0

    return np.array(probs, dtype=np.float32), float(latency_ms)


def metrics_from_probs(labels: np.ndarray, probs: np.ndarray, threshold: float) -> dict[str, float | int]:
    preds = (probs >= threshold).astype(int)

    f1_injection = f1_score(labels, preds, pos_label=1)
    f1_macro = f1_score(labels, preds, average="macro")
    f1_micro = f1_score(labels, preds, average="micro")
    precision, recall, _ = precision_recall_curve(labels, probs)
    pr_auc = auc(recall, precision)

    tn, fp, fn, tp = confusion_matrix(labels, preds, labels=[0, 1]).ravel()
    fp_rate_safe = fp / max(tn + fp, 1)

    return {
        "test_f1_injection": float(f1_injection),
        "test_f1_macro": float(f1_macro),
        "test_f1_micro": float(f1_micro),
        "test_pr_auc": float(pr_auc),
        "test_fp_rate_safe": float(fp_rate_safe),
        "test_tp": int(tp),
        "test_tn": int(tn),
        "test_fp": int(fp),
        "test_fn": int(fn),
    }


def summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "std": 0.0}
    if len(values) == 1:
        return {"mean": float(values[0]), "std": 0.0}
    return {
        "mean": float(statistics.mean(values)),
        "std": float(statistics.stdev(values)),
    }


def classify_pattern(text: str) -> str:
    lowered = text.lower()
    for label, keywords in PATTERN_RULES.items():
        if any(keyword in lowered for keyword in keywords):
            return label
    return "other"


def build_failure_rows(
    frame: pd.DataFrame,
    probs: np.ndarray,
    labels: np.ndarray,
    threshold: float,
    top_k: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int], dict[str, int]]:
    preds = (probs >= threshold).astype(int)

    fp_indices = np.where((labels == 0) & (preds == 1))[0].tolist()
    fn_indices = np.where((labels == 1) & (preds == 0))[0].tolist()

    # Most confident mistakes first.
    fp_indices = sorted(fp_indices, key=lambda idx: probs[idx], reverse=True)[:top_k]
    fn_indices = sorted(fn_indices, key=lambda idx: probs[idx])[:top_k]

    fp_rows = []
    fn_rows = []
    fp_patterns = Counter()
    fn_patterns = Counter()

    for idx in fp_indices:
        prompt = str(frame.iloc[idx]["text"])
        pattern = classify_pattern(prompt)
        fp_patterns[pattern] += 1
        fp_rows.append(
            {
                "index": int(idx),
                "prob_injection": float(probs[idx]),
                "pattern": pattern,
                "text": prompt,
            }
        )

    for idx in fn_indices:
        prompt = str(frame.iloc[idx]["text"])
        pattern = classify_pattern(prompt)
        fn_patterns[pattern] += 1
        fn_rows.append(
            {
                "index": int(idx),
                "prob_injection": float(probs[idx]),
                "pattern": pattern,
                "text": prompt,
            }
        )

    return fp_rows, fn_rows, dict(fp_patterns), dict(fn_patterns)


def evaluate_lora_checkpoint(
    base_model_name: str,
    checkpoint_path: Path,
    texts: list[str],
    labels: np.ndarray,
    threshold: float,
    batch_size: int,
    max_length: int,
) -> tuple[dict[str, Any], np.ndarray]:
    tokenizer = AutoTokenizer.from_pretrained(str(checkpoint_path))
    ensure_tokenizer_pad_token_id(tokenizer)

    base_model = AutoModelForSequenceClassification.from_pretrained(base_model_name, num_labels=2)
    ensure_model_pad_token_id(base_model)
    model = PeftModel.from_pretrained(base_model, str(checkpoint_path))
    ensure_model_pad_token_id(model)

    probs, latency_ms = run_predictions(
        model=model,
        tokenizer=tokenizer,
        texts=texts,
        batch_size=batch_size,
        max_length=max_length,
    )

    metrics = metrics_from_probs(labels=labels, probs=probs, threshold=threshold)
    metrics["latency_ms_per_sample"] = float(latency_ms)
    metrics["checkpoint_size_mb"] = float(directory_size_mb(checkpoint_path))
    metrics["model_params_million"] = float(count_params(model) / 1_000_000.0)

    del model
    del base_model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return metrics, probs


def evaluate_baseline_model(
    baseline_model: str,
    texts: list[str],
    labels: np.ndarray,
    threshold: float,
    batch_size: int,
    max_length: int,
) -> dict[str, Any]:
    tokenizer = AutoTokenizer.from_pretrained(baseline_model)
    ensure_tokenizer_pad_token_id(tokenizer)

    model = AutoModelForSequenceClassification.from_pretrained(baseline_model)
    ensure_model_pad_token_id(model)

    probs, latency_ms = run_predictions(
        model=model,
        tokenizer=tokenizer,
        texts=texts,
        batch_size=batch_size,
        max_length=max_length,
    )

    metrics = metrics_from_probs(labels=labels, probs=probs, threshold=threshold)
    metrics["latency_ms_per_sample"] = float(latency_ms)
    metrics["model_params_million"] = float(count_params(model) / 1_000_000.0)
    metrics["model"] = baseline_model

    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return metrics


def build_failure_report(
    output_path: Path,
    owner: str,
    run_name: str,
    seed: str,
    fp_rows: list[dict[str, Any]],
    fn_rows: list[dict[str, Any]],
    fp_patterns: dict[str, int],
    fn_patterns: dict[str, int],
) -> None:
    lines: list[str] = []
    lines.append(f"=== {owner} CONFIG 4 FAILURE ANALYSIS ===")
    lines.append(f"Best run: {run_name}")
    lines.append(f"Best seed: {seed}")
    lines.append("")

    lines.append("Top false-positive patterns (safe prompts flagged as injection):")
    for pattern, count in sorted(fp_patterns.items(), key=lambda item: item[1], reverse=True)[:5]:
        lines.append(f"- {pattern}: {count}")

    lines.append("")
    lines.append("Top false-negative patterns (injections predicted safe):")
    for pattern, count in sorted(fn_patterns.items(), key=lambda item: item[1], reverse=True)[:5]:
        lines.append(f"- {pattern}: {count}")

    lines.append("")
    lines.append("Sample false positives:")
    for row in fp_rows[:5]:
        short_text = row["text"].replace("\n", " ")[:240]
        lines.append(
            f"- idx={row['index']}, p_inj={row['prob_injection']:.4f}, pattern={row['pattern']} | {short_text}"
        )

    lines.append("")
    lines.append("Sample false negatives:")
    for row in fn_rows[:5]:
        short_text = row["text"].replace("\n", " ")[:240]
        lines.append(
            f"- idx={row['index']}, p_inj={row['prob_injection']:.4f}, pattern={row['pattern']} | {short_text}"
        )

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()

    results_path = Path(args.results_json)
    if not results_path.exists():
        raise FileNotFoundError(f"Missing results file: {results_path}")

    payload = json.loads(results_path.read_text(encoding="utf-8"))

    base_model_name = payload["assignment_config"]["model"]
    owner = payload.get("assignment_owner", "Deeraj")

    data_dir = Path(args.data_dir)
    test_path = data_dir / "xtram1_test.csv"
    if not test_path.exists():
        raise FileNotFoundError(f"Missing test split: {test_path}")

    test_df = pd.read_csv(test_path)
    if "text" not in test_df.columns or "label" not in test_df.columns:
        raise ValueError(f"{test_path} must contain text,label columns")

    test_df["text"] = test_df["text"].astype(str)
    labels = test_df["label"].astype(int).to_numpy()
    texts = test_df["text"].tolist()

    run_eval: dict[str, Any] = {}

    for run_name, run_data in payload["runs"].items():
        per_seed = run_data.get("seeds", {})
        evaluated_seeds: dict[str, Any] = {}

        for seed, seed_payload in per_seed.items():
            checkpoint_path = Path(seed_payload["best_checkpoint_path"])
            if not checkpoint_path.exists():
                raise FileNotFoundError(
                    f"Checkpoint for run={run_name}, seed={seed} not found: {checkpoint_path}"
                )

            metrics, _ = evaluate_lora_checkpoint(
                base_model_name=base_model_name,
                checkpoint_path=checkpoint_path,
                texts=texts,
                labels=labels,
                threshold=args.threshold,
                batch_size=args.batch_size,
                max_length=args.max_length,
            )
            evaluated_seeds[seed] = metrics

        run_eval[run_name] = evaluated_seeds

    best_run_name = max(
        run_eval,
        key=lambda run: statistics.mean(
            [seed_m["test_f1_injection"] for seed_m in run_eval[run].values()]
        ),
    )

    best_seed = max(
        run_eval[best_run_name],
        key=lambda seed_key: run_eval[best_run_name][seed_key]["test_f1_injection"],
    )

    best_seed_checkpoint = Path(payload["runs"][best_run_name]["seeds"][best_seed]["best_checkpoint_path"])
    best_metrics, best_probs = evaluate_lora_checkpoint(
        base_model_name=base_model_name,
        checkpoint_path=best_seed_checkpoint,
        texts=texts,
        labels=labels,
        threshold=args.threshold,
        batch_size=args.batch_size,
        max_length=args.max_length,
    )

    fp_rows, fn_rows, fp_patterns, fn_patterns = build_failure_rows(
        frame=test_df,
        probs=best_probs,
        labels=labels,
        threshold=args.threshold,
        top_k=args.top_errors,
    )

    failure_path = Path(args.failure_file)
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    build_failure_report(
        output_path=failure_path,
        owner=owner,
        run_name=best_run_name,
        seed=best_seed,
        fp_rows=fp_rows,
        fn_rows=fn_rows,
        fp_patterns=fp_patterns,
        fn_patterns=fn_patterns,
    )

    aggregated = {
        "test_f1_injection": summarize(
            [metric["test_f1_injection"] for run in run_eval.values() for metric in run.values()]
        ),
        "test_f1_macro": summarize(
            [metric["test_f1_macro"] for run in run_eval.values() for metric in run.values()]
        ),
        "test_f1_micro": summarize(
            [metric["test_f1_micro"] for run in run_eval.values() for metric in run.values()]
        ),
        "test_pr_auc": summarize(
            [metric["test_pr_auc"] for run in run_eval.values() for metric in run.values()]
        ),
        "test_fp_rate_safe": summarize(
            [metric["test_fp_rate_safe"] for run in run_eval.values() for metric in run.values()]
        ),
        "latency_ms_per_sample": summarize(
            [metric["latency_ms_per_sample"] for run in run_eval.values() for metric in run.values()]
        ),
    }

    baseline_metrics: dict[str, Any] | None = None
    if args.baseline_model:
        baseline_metrics = evaluate_baseline_model(
            baseline_model=args.baseline_model,
            texts=texts,
            labels=labels,
            threshold=args.threshold,
            batch_size=args.batch_size,
            max_length=args.max_length,
        )

    comparison_payload: dict[str, Any] = {
        "owner": owner,
        "config4_model": base_model_name,
        "selected_best_run": best_run_name,
        "selected_best_seed": best_seed,
        "config4_best_seed_metrics": best_metrics,
        "config4_aggregated_across_runs_and_seeds": aggregated,
        "baseline_encoder": baseline_metrics,
        "delta_vs_baseline": None,
        "failure_analysis_file": str(failure_path),
    }

    if baseline_metrics is not None:
        comparison_payload["delta_vs_baseline"] = {
            "f1_injection_delta": float(best_metrics["test_f1_injection"] - baseline_metrics["test_f1_injection"]),
            "f1_macro_delta": float(best_metrics["test_f1_macro"] - baseline_metrics["test_f1_macro"]),
            "f1_micro_delta": float(best_metrics["test_f1_micro"] - baseline_metrics["test_f1_micro"]),
            "pr_auc_delta": float(best_metrics["test_pr_auc"] - baseline_metrics["test_pr_auc"]),
            "fp_rate_safe_delta": float(best_metrics["test_fp_rate_safe"] - baseline_metrics["test_fp_rate_safe"]),
            "latency_ms_delta": float(best_metrics["latency_ms_per_sample"] - baseline_metrics["latency_ms_per_sample"]),
        }

    comparison_path = Path(args.comparison_json)
    comparison_path.parent.mkdir(parents=True, exist_ok=True)
    comparison_path.write_text(json.dumps(comparison_payload, indent=2), encoding="utf-8")

    payload.setdefault("evaluation", {})
    payload["evaluation"]["per_run_seed_metrics"] = run_eval
    payload["evaluation"]["best_run"] = best_run_name
    payload["evaluation"]["best_seed"] = best_seed
    payload["evaluation"]["best_seed_metrics"] = best_metrics
    payload["evaluation"]["failure_patterns"] = {
        "false_positive": fp_patterns,
        "false_negative": fn_patterns,
    }
    payload["evaluation"]["comparison_file"] = str(comparison_path)
    payload["evaluation"]["failure_file"] = str(failure_path)

    results_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Saved comparison report: {comparison_path}")
    print(f"Saved failure analysis: {failure_path}")
    print(f"Updated results file: {results_path}")


if __name__ == "__main__":
    main()
