#!/usr/bin/env python3
"""
Config 3 (Owner: Jaival)
Train roberta-large for prompt-injection detection with:
- Optional hard-negative batch mixing (ablation-ready)
- R-Drop regularization
- Multi-seed evaluation summary
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from datasets import Dataset
from sklearn.metrics import auc, confusion_matrix, f1_score, precision_recall_curve
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    EvalPrediction,
    Trainer,
    TrainingArguments,
    set_seed,
)


def parse_int_csv(raw: str) -> list[int]:
    out = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            out.append(int(part))
    if not out:
        raise ValueError("Expected at least one integer in CSV argument.")
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Jaival Config 3 roberta-large pipeline")
    parser.add_argument("--model-name", default="roberta-large")
    parser.add_argument("--data-dir", default="data/processed")
    parser.add_argument("--output-dir", default="layer 2/checkpoints_config3")
    parser.add_argument("--results-json", default="layer 2/results_config3.json")
    parser.add_argument("--seeds", default="42,43,44")

    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--eval-batch-size", type=int, default=32)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=1)
    parser.add_argument("--epochs", type=float, default=5.0)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--weight-decay", type=float, default=0.05)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--rdrop-alpha", type=float, default=0.5, help="R-Drop KL coefficient")

    parser.add_argument(
        "--with-hard-negatives",
        action="store_true",
        help="Enable hard-negative batch mix for this run.",
    )
    parser.add_argument(
        "--hard-negative-ratio",
        type=float,
        default=0.30,
        help="Portion of mixed training set replaced by mined hard negatives.",
    )

    parser.add_argument("--logging-steps", type=int, default=25)
    parser.add_argument("--latency-samples", type=int, default=128)
    return parser.parse_args()


def load_split(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing split file: {path}")
    df = pd.read_csv(path)
    needed = {"text", "label"}
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(f"Split {path} missing columns: {sorted(missing)}")
    out = df.copy()
    out["text"] = out["text"].astype(str).str.strip()
    out["label"] = out["label"].astype(int)
    out = out[out["text"] != ""].reset_index(drop=True)
    return out


def load_splits(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        load_split(data_dir / "xtram1_train.csv"),
        load_split(data_dir / "xtram1_val.csv"),
        load_split(data_dir / "xtram1_test.csv"),
    )


def mine_hard_negative_pool(df: pd.DataFrame) -> pd.DataFrame:
    triggers = [
        "ignore",
        "bypass",
        "override",
        "system",
        "developer",
        "admin",
        "prompt",
        "instruction",
        "secret",
        "token",
        "policy",
        "jailbreak",
        "act as",
        "pretend",
        "role",
        "base64",
        "decode",
        "rot13",
    ]
    mask = (df["label"] == 0) & (
        df["text"].str.lower().str.contains("|".join([f"\\b{t}\\b" for t in triggers]), regex=True)
    )
    return df[mask].copy()


def apply_hard_negative_mix(train_df: pd.DataFrame, ratio: float, seed: int) -> pd.DataFrame:
    if ratio <= 0:
        return train_df.copy()
    hard_pool = mine_hard_negative_pool(train_df)
    if hard_pool.empty:
        return train_df.copy()

    rng = random.Random(seed)
    mixed = train_df.copy()
    replace_count = min(int(len(mixed) * ratio), len(hard_pool))
    if replace_count <= 0:
        return mixed

    replace_indices = rng.sample(list(mixed.index), replace_count)
    sampled_pool = hard_pool.sample(n=replace_count, random_state=seed).reset_index(drop=True)
    for i, idx in enumerate(replace_indices):
        mixed.loc[idx, ["text", "label"]] = sampled_pool.loc[i, ["text", "label"]]
    return mixed.reset_index(drop=True)


def to_dataset(frame: pd.DataFrame) -> Dataset:
    use = frame[["text", "label"]].copy()
    ds = Dataset.from_pandas(use, preserve_index=False)
    return ds.rename_column("label", "labels")


def tokenize_splits(
    tokenizer: Any,
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    max_length: int,
) -> tuple[Dataset, Dataset, Dataset]:
    train_ds = to_dataset(train_df)
    val_ds = to_dataset(val_df)
    test_ds = to_dataset(test_df)

    def tok(batch: dict[str, list[Any]]) -> dict[str, Any]:
        return tokenizer(batch["text"], truncation=True, max_length=max_length)

    train_tok = train_ds.map(tok, batched=True, remove_columns=["text"])
    val_tok = val_ds.map(tok, batched=True, remove_columns=["text"])
    test_tok = test_ds.map(tok, batched=True, remove_columns=["text"])
    return train_tok, val_tok, test_tok


def metrics_from_logits(logits: np.ndarray, labels: np.ndarray, threshold: float) -> dict[str, float]:
    probs = torch.softmax(torch.tensor(logits, dtype=torch.float32), dim=-1).cpu().numpy()[:, 1]
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


def build_compute_metrics(threshold: float):
    def compute(eval_pred: EvalPrediction) -> dict[str, float]:
        return metrics_from_logits(eval_pred.predictions, eval_pred.label_ids, threshold)

    return compute


def _symmetric_kl(logits_a: torch.Tensor, logits_b: torch.Tensor) -> torch.Tensor:
    logp_a = F.log_softmax(logits_a, dim=-1)
    logp_b = F.log_softmax(logits_b, dim=-1)
    p_a = logp_a.exp()
    p_b = logp_b.exp()
    kl_ab = F.kl_div(logp_a, p_b, reduction="batchmean")
    kl_ba = F.kl_div(logp_b, p_a, reduction="batchmean")
    return 0.5 * (kl_ab + kl_ba)


class RDropTrainer(Trainer):
    def __init__(self, *args: Any, rdrop_alpha: float = 0.0, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.rdrop_alpha = float(max(rdrop_alpha, 0.0))

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):  # type: ignore[override]
        labels = inputs.get("labels")

        outputs1 = model(**inputs)
        logits1 = outputs1.logits
        ce1 = F.cross_entropy(logits1, labels)

        if self.rdrop_alpha > 0:
            outputs2 = model(**inputs)
            logits2 = outputs2.logits
            ce2 = F.cross_entropy(logits2, labels)
            ce = 0.5 * (ce1 + ce2)
            kl = _symmetric_kl(logits1, logits2)
            loss = ce + self.rdrop_alpha * kl
        else:
            loss = ce1
            logits2 = None

        if return_outputs:
            if logits2 is not None:
                merged_logits = 0.5 * (logits1 + logits2)
                outputs1.logits = merged_logits
            return loss, outputs1
        return loss


def measure_latency_ms(model: torch.nn.Module, tokenizer: Any, texts: list[str], max_length: int, sample_size: int) -> float:
    if not texts:
        return 0.0
    device = next(model.parameters()).device
    model.eval()
    subset = texts[: min(sample_size, len(texts))]
    with torch.no_grad():
        for text in subset[:4]:
            encoded = tokenizer(text, return_tensors="pt", truncation=True, max_length=max_length)
            encoded = {k: v.to(device) for k, v in encoded.items()}
            _ = model(**encoded)
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    start = time.perf_counter()
    with torch.no_grad():
        for text in subset:
            encoded = tokenizer(text, return_tensors="pt", truncation=True, max_length=max_length)
            encoded = {k: v.to(device) for k, v in encoded.items()}
            _ = model(**encoded)
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    return ((time.perf_counter() - start) / len(subset)) * 1000.0


def summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "std": 0.0}
    if len(values) == 1:
        return {"mean": float(values[0]), "std": 0.0}
    return {"mean": float(statistics.mean(values)), "std": float(statistics.stdev(values))}


def run_seed(
    seed: int,
    args: argparse.Namespace,
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    run_root: Path,
) -> dict[str, Any]:
    set_seed(seed)
    train_use = (
        apply_hard_negative_mix(train_df, args.hard_negative_ratio, seed)
        if args.with_hard_negatives
        else train_df.copy()
    )

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = AutoModelForSequenceClassification.from_pretrained(args.model_name, num_labels=2)

    train_tok, val_tok, test_tok = tokenize_splits(
        tokenizer=tokenizer,
        train_df=train_use,
        val_df=val_df,
        test_df=test_df,
        max_length=args.max_length,
    )

    out_dir = run_root / f"seed_{seed}"
    out_dir.mkdir(parents=True, exist_ok=True)
    best_dir = out_dir / "best_checkpoint"
    best_dir.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(out_dir),
        overwrite_output_dir=True,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.eval_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        logging_steps=args.logging_steps,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="eval_f1_injection",
        greater_is_better=True,
        report_to=[],
        seed=seed,
        data_seed=seed,
        fp16=torch.cuda.is_available(),
    )

    trainer = RDropTrainer(
        model=model,
        args=training_args,
        train_dataset=train_tok,
        eval_dataset=val_tok,
        tokenizer=tokenizer,
        data_collator=DataCollatorWithPadding(tokenizer=tokenizer),
        compute_metrics=build_compute_metrics(args.threshold),
        rdrop_alpha=args.rdrop_alpha,
    )

    start = time.perf_counter()
    trainer.train()
    train_wall_sec = time.perf_counter() - start

    val_metrics = trainer.evaluate(eval_dataset=val_tok, metric_key_prefix="val")
    test_metrics = trainer.evaluate(eval_dataset=test_tok, metric_key_prefix="test")

    trainer.model.save_pretrained(best_dir)
    tokenizer.save_pretrained(best_dir)
    latency_ms = measure_latency_ms(
        model=trainer.model,
        tokenizer=tokenizer,
        texts=test_df["text"].tolist(),
        max_length=args.max_length,
        sample_size=args.latency_samples,
    )

    run = {
        "seed": seed,
        "with_hard_negatives": bool(args.with_hard_negatives),
        "hard_negative_ratio": float(args.hard_negative_ratio if args.with_hard_negatives else 0.0),
        "rdrop_alpha": float(args.rdrop_alpha),
        "best_checkpoint_path": str(best_dir),
        "train_rows_effective": int(len(train_use)),
        "train_wall_time_minutes": float(train_wall_sec / 60.0),
        "latency_ms_per_sample": float(latency_ms),
        "val_f1_injection": float(val_metrics.get("val_f1_injection", 0.0)),
        "val_pr_auc": float(val_metrics.get("val_pr_auc", 0.0)),
        "val_fp_rate_safe": float(val_metrics.get("val_fp_rate_safe", 0.0)),
        "test_f1_injection": float(test_metrics.get("test_f1_injection", 0.0)),
        "test_pr_auc": float(test_metrics.get("test_pr_auc", 0.0)),
        "test_fp_rate_safe": float(test_metrics.get("test_fp_rate_safe", 0.0)),
        "test_tp": int(test_metrics.get("test_tp", 0)),
        "test_tn": int(test_metrics.get("test_tn", 0)),
        "test_fp": int(test_metrics.get("test_fp", 0)),
        "test_fn": int(test_metrics.get("test_fn", 0)),
    }

    del trainer
    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return run


def main() -> None:
    args = parse_args()
    seeds = parse_int_csv(args.seeds)
    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = Path(args.results_json)
    results_path.parent.mkdir(parents=True, exist_ok=True)

    train_df, val_df, test_df = load_splits(data_dir)
    mode = "with_hard_negatives" if args.with_hard_negatives else "without_hard_negatives"
    run_root = output_dir / mode
    run_root.mkdir(parents=True, exist_ok=True)

    seed_runs = []
    for seed in seeds:
        seed_runs.append(run_seed(seed, args, train_df, val_df, test_df, run_root))

    aggregated = {
        "test_f1_injection": summarize([x["test_f1_injection"] for x in seed_runs]),
        "test_pr_auc": summarize([x["test_pr_auc"] for x in seed_runs]),
        "test_fp_rate_safe": summarize([x["test_fp_rate_safe"] for x in seed_runs]),
        "latency_ms_per_sample": summarize([x["latency_ms_per_sample"] for x in seed_runs]),
    }

    payload = {
        "assignment_owner": "Jaival",
        "assignment_config": {
            "model": args.model_name,
            "max_length": args.max_length,
            "learning_rate": args.learning_rate,
            "batch_size": args.batch_size,
            "gradient_accumulation_steps": args.gradient_accumulation_steps,
            "effective_batch_size": args.batch_size * args.gradient_accumulation_steps,
            "epochs": args.epochs,
            "weight_decay": args.weight_decay,
            "rdrop_alpha": args.rdrop_alpha,
            "seeds": seeds,
            "with_hard_negatives": bool(args.with_hard_negatives),
            "hard_negative_ratio": float(args.hard_negative_ratio if args.with_hard_negatives else 0.0),
            "mode": mode,
        },
        "runs": {str(item["seed"]): item for item in seed_runs},
        "aggregated": aggregated,
    }

    if results_path.exists():
        current = json.loads(results_path.read_text(encoding="utf-8"))
        current[mode] = payload
        merged = current
    else:
        merged = {mode: payload}

    results_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    print(f"Saved config 3 results: {results_path}")
    print(f"Mode: {mode}")


if __name__ == "__main__":
    main()
