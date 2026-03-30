#!/usr/bin/env python3
"""
Config 4 (Owner: Deeraj)
Train meta-llama/Llama-Guard-3-1B with LoRA/QLoRA for prompt-injection detection.

Required assignment coverage:
- Uses xTRam1 train/val/test split files
- Runs multiple seeds (default: 42,43,44)
- Captures GPU RAM + wall-clock profile
- Records LoRA rank/alpha and metric impact
- Exports comparison-ready metrics in results_config4.json
"""
from __future__ import annotations

import argparse
import inspect
import json
import statistics
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import torch
from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
from sklearn.metrics import auc, confusion_matrix, f1_score, precision_recall_curve
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorWithPadding,
    EvalPrediction,
    Trainer,
    TrainingArguments,
    set_seed,
)


def parse_int_csv(raw: str) -> list[int]:
    values = []
    for part in raw.split(","):
        stripped = part.strip()
        if stripped:
            values.append(int(stripped))
    if not values:
        raise ValueError("Expected at least one integer value")
    return values


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train Deeraj Config 4 LoRA pipeline")
    parser.add_argument(
        "--model-name",
        default="meta-llama/Llama-Guard-3-1B",
        help="Base model to fine-tune",
    )
    parser.add_argument("--data-dir", default="data/processed", help="Folder with xtram1 CSV splits")
    parser.add_argument(
        "--output-dir",
        default="layer 2/checkpoints_config4",
        help="Folder to store checkpoints and trainer state",
    )
    parser.add_argument(
        "--results-json",
        default="layer 2/results_config4.json",
        help="Output results file path",
    )

    parser.add_argument("--max-length", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--eval-batch-size", type=int, default=8)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--weight-decay", type=float, default=0.01)

    parser.add_argument("--adapter-lr", type=float, default=1e-4)
    parser.add_argument("--head-lr", type=float, default=2e-5)
    parser.add_argument("--threshold", type=float, default=0.5, help="Classification threshold for label=1")

    parser.add_argument(
        "--seeds",
        default="42,43,44",
        help="Comma-separated random seeds",
    )
    parser.add_argument(
        "--lora-ranks",
        default="16",
        help="Comma-separated LoRA rank values for impact analysis",
    )
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument(
        "--target-modules",
        default="q_proj,v_proj",
        help="Comma-separated module names for LoRA",
    )

    parser.add_argument("--qlora", action="store_true", help="Enable 4-bit QLoRA")
    parser.add_argument(
        "--gradient-checkpointing",
        action="store_true",
        help="Enable gradient checkpointing for lower memory usage",
    )
    parser.add_argument(
        "--force-cpu",
        action="store_true",
        help="Force CPU training when CUDA memory is insufficient",
    )
    parser.add_argument("--latency-samples", type=int, default=128)
    parser.add_argument("--logging-steps", type=int, default=25)
    parser.add_argument("--save-total-limit", type=int, default=2)

    return parser.parse_args()


def read_split(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing dataset split: {path}")
    df = pd.read_csv(path)
    required_cols = {"text", "label"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Split {path} missing columns: {sorted(missing)}")
    df = df.copy()
    df["text"] = df["text"].astype(str).str.strip()
    df["label"] = df["label"].astype(int)
    df = df[df["text"] != ""].reset_index(drop=True)
    return df


def load_splits(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train_df = read_split(data_dir / "xtram1_train.csv")
    val_df = read_split(data_dir / "xtram1_val.csv")
    test_df = read_split(data_dir / "xtram1_test.csv")
    return train_df, val_df, test_df


def as_dataset(frame: pd.DataFrame) -> Dataset:
    use = frame[["text", "label"]].copy()
    ds = Dataset.from_pandas(use, preserve_index=False)
    ds = ds.rename_column("label", "labels")
    return ds


def tokenize_splits(
    tokenizer: Any,
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    max_length: int,
) -> tuple[Dataset, Dataset, Dataset]:
    train_ds = as_dataset(train_df)
    val_ds = as_dataset(val_df)
    test_ds = as_dataset(test_df)

    def tokenization_fn(batch: dict[str, list[Any]]) -> dict[str, Any]:
        return tokenizer(batch["text"], truncation=True, max_length=max_length)

    train_tok = train_ds.map(tokenization_fn, batched=True, remove_columns=["text"])
    val_tok = val_ds.map(tokenization_fn, batched=True, remove_columns=["text"])
    test_tok = test_ds.map(tokenization_fn, batched=True, remove_columns=["text"])
    return train_tok, val_tok, test_tok


def metrics_from_logits(logits: np.ndarray, labels: np.ndarray, threshold: float) -> dict[str, float]:
    logits_tensor = torch.tensor(logits, dtype=torch.float32)
    probs = torch.softmax(logits_tensor, dim=-1).cpu().numpy()
    positive_prob = probs[:, 1]
    preds = (positive_prob >= threshold).astype(int)

    f1_injection = f1_score(labels, preds, pos_label=1)
    f1_macro = f1_score(labels, preds, average="macro")
    f1_micro = f1_score(labels, preds, average="micro")

    precision, recall, _ = precision_recall_curve(labels, positive_prob)
    pr_auc = auc(recall, precision)

    tn, fp, fn, tp = confusion_matrix(labels, preds, labels=[0, 1]).ravel()
    fp_rate_safe = fp / max(tn + fp, 1)

    return {
        "f1_injection": float(f1_injection),
        "f1_macro": float(f1_macro),
        "f1_micro": float(f1_micro),
        "pr_auc": float(pr_auc),
        "fp_rate_safe": float(fp_rate_safe),
        "tp": int(tp),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
    }


def build_compute_metrics(threshold: float) -> Callable[[EvalPrediction], dict[str, float]]:
    def compute(eval_pred: EvalPrediction) -> dict[str, float]:
        logits = eval_pred.predictions
        labels = eval_pred.label_ids
        return metrics_from_logits(logits=logits, labels=labels, threshold=threshold)

    return compute


class DualLrTrainer(Trainer):
    """Custom Trainer with separate LR for LoRA adapters and classification head."""

    def __init__(self, *args: Any, adapter_lr: float, head_lr: float, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.adapter_lr = adapter_lr
        self.head_lr = head_lr

    def create_optimizer(self) -> torch.optim.Optimizer:
        if self.optimizer is not None:
            return self.optimizer

        adapter_params = []
        head_params = []
        other_trainable = []

        for name, param in self.model.named_parameters():
            if not param.requires_grad:
                continue
            lower_name = name.lower()
            if "lora_" in lower_name:
                adapter_params.append(param)
            elif "score" in lower_name or "classifier" in lower_name:
                head_params.append(param)
            else:
                other_trainable.append(param)

        param_groups: list[dict[str, Any]] = []
        if adapter_params:
            param_groups.append(
                {
                    "params": adapter_params,
                    "lr": self.adapter_lr,
                    "weight_decay": self.args.weight_decay,
                }
            )
        if head_params:
            param_groups.append(
                {
                    "params": head_params,
                    "lr": self.head_lr,
                    "weight_decay": self.args.weight_decay,
                }
            )
        if other_trainable:
            param_groups.append(
                {
                    "params": other_trainable,
                    "lr": self.head_lr,
                    "weight_decay": self.args.weight_decay,
                }
            )

        self.optimizer = torch.optim.AdamW(
            param_groups,
            betas=(self.args.adam_beta1, self.args.adam_beta2),
            eps=self.args.adam_epsilon,
        )
        return self.optimizer


def get_device(model: torch.nn.Module) -> torch.device:
    return next(model.parameters()).device


def measure_latency_ms(
    model: torch.nn.Module,
    tokenizer: Any,
    texts: list[str],
    max_length: int,
    sample_size: int,
) -> float:
    if not texts:
        return 0.0

    model.eval()
    device = get_device(model)
    subset = texts[: min(sample_size, len(texts))]

    warmup = subset[: min(4, len(subset))]
    with torch.no_grad():
        for text in warmup:
            encoded = tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=max_length,
            )
            encoded = {key: value.to(device) for key, value in encoded.items()}
            _ = model(**encoded)

    if device.type == "cuda":
        torch.cuda.synchronize(device)

    start = time.perf_counter()
    with torch.no_grad():
        for text in subset:
            encoded = tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=max_length,
            )
            encoded = {key: value.to(device) for key, value in encoded.items()}
            _ = model(**encoded)

    if device.type == "cuda":
        torch.cuda.synchronize(device)

    elapsed = time.perf_counter() - start
    return (elapsed / len(subset)) * 1000.0


def directory_size_mb(path: Path) -> float:
    total_bytes = 0
    if not path.exists():
        return 0.0
    for item in path.rglob("*"):
        if item.is_file():
            total_bytes += item.stat().st_size
    return total_bytes / (1024 * 1024)


def summarize_mean_std(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "std": 0.0}
    if len(values) == 1:
        return {"mean": float(values[0]), "std": 0.0}
    return {
        "mean": float(statistics.mean(values)),
        "std": float(statistics.stdev(values)),
    }


def detect_best_epoch(log_history: list[dict[str, Any]], metric_name: str) -> float | None:
    best_metric = None
    best_epoch = None
    for item in log_history:
        metric_value = item.get(metric_name)
        epoch_value = item.get("epoch")
        if metric_value is None or epoch_value is None:
            continue
        if best_metric is None or metric_value > best_metric:
            best_metric = metric_value
            best_epoch = float(epoch_value)
    return best_epoch


def pick_single_token_id(value: Any) -> int | None:
    """Return a stable single token id from int/list tokenizer config values."""
    if isinstance(value, int):
        return int(value)
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, int):
                return int(item)
    return None


def ensure_tokenizer_pad_token_id(tokenizer: Any) -> None:
    """Normalize tokenizer padding id for models with multi-eos token ids."""
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
    """Normalize model.config.pad_token_id to an int for strict config classes."""
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


def build_training_arguments(
    args: argparse.Namespace,
    output_dir: Path,
    seed: int,
) -> TrainingArguments:
    """Create TrainingArguments compatible with multiple transformers versions."""
    parameters = inspect.signature(TrainingArguments.__init__).parameters

    kwargs: dict[str, Any] = {
        "output_dir": str(output_dir),
        "num_train_epochs": args.epochs,
        "per_device_train_batch_size": args.batch_size,
        "per_device_eval_batch_size": args.eval_batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "weight_decay": args.weight_decay,
        "learning_rate": args.adapter_lr,
        "logging_steps": args.logging_steps,
        "save_total_limit": args.save_total_limit,
        "load_best_model_at_end": True,
        "metric_for_best_model": "eval_f1_injection",
        "greater_is_better": True,
        "report_to": [],
        "seed": seed,
        "data_seed": seed,
        "fp16": torch.cuda.is_available(),
    }

    if args.gradient_checkpointing:
        kwargs["gradient_checkpointing"] = True

    if args.force_cpu:
        kwargs["no_cuda"] = True
        kwargs["fp16"] = False

    if "eval_strategy" in parameters:
        kwargs["eval_strategy"] = "epoch"
    elif "evaluation_strategy" in parameters:
        kwargs["evaluation_strategy"] = "epoch"

    if "save_strategy" in parameters:
        kwargs["save_strategy"] = "epoch"

    if "overwrite_output_dir" in parameters:
        kwargs["overwrite_output_dir"] = True

    if "do_train" in parameters:
        kwargs["do_train"] = True
    if "do_eval" in parameters:
        kwargs["do_eval"] = True

    filtered_kwargs = {key: value for key, value in kwargs.items() if key in parameters}
    return TrainingArguments(**filtered_kwargs)


def build_trainer_kwargs(
    model: torch.nn.Module,
    training_args: TrainingArguments,
    train_tok: Dataset,
    val_tok: Dataset,
    tokenizer: Any,
    threshold: float,
) -> dict[str, Any]:
    """Create Trainer kwargs compatible with multiple Trainer signatures."""
    parameters = inspect.signature(Trainer.__init__).parameters

    kwargs: dict[str, Any] = {
        "model": model,
        "args": training_args,
        "train_dataset": train_tok,
        "eval_dataset": val_tok,
        "data_collator": DataCollatorWithPadding(tokenizer=tokenizer),
        "compute_metrics": build_compute_metrics(threshold),
    }

    if "tokenizer" in parameters:
        kwargs["tokenizer"] = tokenizer
    elif "processing_class" in parameters:
        kwargs["processing_class"] = tokenizer

    return {key: value for key, value in kwargs.items() if key in parameters}


def build_model(
    model_name: str,
    qlora: bool,
    lora_rank: int,
    lora_alpha: int,
    lora_dropout: float,
    target_modules: list[str],
    use_gradient_checkpointing: bool,
) -> torch.nn.Module:
    model_kwargs: dict[str, Any] = {"num_labels": 2}

    if qlora:
        if not torch.cuda.is_available():
            raise RuntimeError("QLoRA requires CUDA GPU. Disable --qlora for CPU training.")
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )
        model_kwargs["quantization_config"] = bnb_config
        model_kwargs["device_map"] = "auto"

    model = AutoModelForSequenceClassification.from_pretrained(model_name, **model_kwargs)

    if qlora:
        model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        task_type=TaskType.SEQ_CLS,
        r=lora_rank,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        target_modules=target_modules,
        bias="none",
        modules_to_save=["score", "classifier"],
    )

    model = get_peft_model(model, lora_config)

    if use_gradient_checkpointing and hasattr(model, "gradient_checkpointing_enable"):
        # Keep activations small on constrained GPUs when requested.
        model.gradient_checkpointing_enable()

    ensure_model_pad_token_id(model)

    return model


def param_counts(model: torch.nn.Module) -> tuple[int, int]:
    trainable = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
    total = sum(parameter.numel() for parameter in model.parameters())
    return trainable, total


def run_single_seed(
    seed: int,
    lora_rank: int,
    args: argparse.Namespace,
    tokenizer: Any,
    train_tok: Dataset,
    val_tok: Dataset,
    test_tok: Dataset,
    test_texts: list[str],
    run_root: Path,
) -> dict[str, Any]:
    set_seed(seed)

    seed_root = run_root / f"seed_{seed}"
    trainer_output = seed_root / "trainer_state"
    adapter_output = seed_root / "best_adapter"
    trainer_output.mkdir(parents=True, exist_ok=True)
    adapter_output.mkdir(parents=True, exist_ok=True)

    model = build_model(
        model_name=args.model_name,
        qlora=args.qlora,
        lora_rank=lora_rank,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=[part.strip() for part in args.target_modules.split(",") if part.strip()],
        use_gradient_checkpointing=args.gradient_checkpointing,
    )

    trainable_params, total_params = param_counts(model)
    print(
        f"Seed {seed}, rank {lora_rank}: trainable={trainable_params:,}, total={total_params:,}"
    )

    training_args = build_training_arguments(
        args=args,
        output_dir=trainer_output,
        seed=seed,
    )

    trainer = DualLrTrainer(
        **build_trainer_kwargs(
            model=model,
            training_args=training_args,
            train_tok=train_tok,
            val_tok=val_tok,
            tokenizer=tokenizer,
            threshold=args.threshold,
        ),
        adapter_lr=args.adapter_lr,
        head_lr=args.head_lr,
    )

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()

    start = time.perf_counter()
    trainer.train()
    wall_time_sec = time.perf_counter() - start

    best_epoch = detect_best_epoch(trainer.state.log_history, "eval_f1_injection")

    val_metrics = trainer.evaluate(eval_dataset=val_tok, metric_key_prefix="val")
    test_metrics = trainer.evaluate(eval_dataset=test_tok, metric_key_prefix="test")

    trainer.model.save_pretrained(adapter_output)
    tokenizer.save_pretrained(adapter_output)

    peak_gpu_ram_gb = None
    if torch.cuda.is_available():
        peak_gpu_ram_gb = float(torch.cuda.max_memory_allocated() / (1024 ** 3))

    latency_ms = measure_latency_ms(
        model=trainer.model,
        tokenizer=tokenizer,
        texts=test_texts,
        max_length=args.max_length,
        sample_size=args.latency_samples,
    )

    checkpoint_size = directory_size_mb(adapter_output)

    result = {
        "seed": seed,
        "lora_rank": lora_rank,
        "lora_alpha": args.lora_alpha,
        "target_modules": [part.strip() for part in args.target_modules.split(",") if part.strip()],
        "best_validation_epoch": best_epoch,
        "best_checkpoint_path": str(adapter_output),
        "train_wall_time_seconds": float(wall_time_sec),
        "train_wall_time_minutes": float(wall_time_sec / 60.0),
        "peak_gpu_ram_gb": peak_gpu_ram_gb,
        "trainable_params": int(trainable_params),
        "total_params": int(total_params),
        "checkpoint_size_mb": float(checkpoint_size),
        "latency_ms_per_sample": float(latency_ms),
        "val_f1_injection": float(val_metrics.get("val_f1_injection", 0.0)),
        "val_f1_macro": float(val_metrics.get("val_f1_macro", 0.0)),
        "val_f1_micro": float(val_metrics.get("val_f1_micro", 0.0)),
        "val_pr_auc": float(val_metrics.get("val_pr_auc", 0.0)),
        "val_fp_rate_safe": float(val_metrics.get("val_fp_rate_safe", 0.0)),
        "test_f1_injection": float(test_metrics.get("test_f1_injection", 0.0)),
        "test_f1_macro": float(test_metrics.get("test_f1_macro", 0.0)),
        "test_f1_micro": float(test_metrics.get("test_f1_micro", 0.0)),
        "test_pr_auc": float(test_metrics.get("test_pr_auc", 0.0)),
        "test_fp_rate_safe": float(test_metrics.get("test_fp_rate_safe", 0.0)),
        "test_tp": int(test_metrics.get("test_tp", 0)),
        "test_tn": int(test_metrics.get("test_tn", 0)),
        "test_fp": int(test_metrics.get("test_fp", 0)),
        "test_fn": int(test_metrics.get("test_fn", 0)),
    }

    # Free memory early between seeds.
    del trainer
    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return result


def aggregate_seed_results(seed_runs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "test_f1_injection": summarize_mean_std([run["test_f1_injection"] for run in seed_runs]),
        "test_f1_macro": summarize_mean_std([run["test_f1_macro"] for run in seed_runs]),
        "test_f1_micro": summarize_mean_std([run["test_f1_micro"] for run in seed_runs]),
        "test_pr_auc": summarize_mean_std([run["test_pr_auc"] for run in seed_runs]),
        "test_fp_rate_safe": summarize_mean_std([run["test_fp_rate_safe"] for run in seed_runs]),
        "latency_ms_per_sample": summarize_mean_std([run["latency_ms_per_sample"] for run in seed_runs]),
        "peak_gpu_ram_gb": summarize_mean_std(
            [run["peak_gpu_ram_gb"] for run in seed_runs if run["peak_gpu_ram_gb"] is not None]
        ),
        "train_wall_time_minutes": summarize_mean_std(
            [run["train_wall_time_minutes"] for run in seed_runs]
        ),
        "checkpoint_size_mb": summarize_mean_std([run["checkpoint_size_mb"] for run in seed_runs]),
    }


def main() -> None:
    args = parse_args()

    seeds = parse_int_csv(args.seeds)
    lora_ranks = parse_int_csv(args.lora_ranks)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results_json_path = Path(args.results_json)
    results_json_path.parent.mkdir(parents=True, exist_ok=True)

    data_dir = Path(args.data_dir)
    train_df, val_df, test_df = load_splits(data_dir)
    print(
        f"Loaded splits from {data_dir}: "
        f"train={len(train_df)}, val={len(val_df)}, test={len(test_df)}"
    )

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    ensure_tokenizer_pad_token_id(tokenizer)

    train_tok, val_tok, test_tok = tokenize_splits(
        tokenizer=tokenizer,
        train_df=train_df,
        val_df=val_df,
        test_df=test_df,
        max_length=args.max_length,
    )

    run_map: dict[str, Any] = {}

    for lora_rank in lora_ranks:
        run_name = f"rank_{lora_rank}_alpha_{args.lora_alpha}"
        print(f"\\n=== Running {run_name} ===")

        run_root = output_dir / run_name
        run_root.mkdir(parents=True, exist_ok=True)

        seed_results: list[dict[str, Any]] = []
        for seed in seeds:
            seed_result = run_single_seed(
                seed=seed,
                lora_rank=lora_rank,
                args=args,
                tokenizer=tokenizer,
                train_tok=train_tok,
                val_tok=val_tok,
                test_tok=test_tok,
                test_texts=test_df["text"].tolist(),
                run_root=run_root,
            )
            seed_results.append(seed_result)

        run_map[run_name] = {
            "lora_rank": lora_rank,
            "lora_alpha": args.lora_alpha,
            "seeds": {str(item["seed"]): item for item in seed_results},
            "aggregated": aggregate_seed_results(seed_results),
        }

    # Pick best run by mean test F1.
    best_run_name = max(
        run_map,
        key=lambda key: run_map[key]["aggregated"]["test_f1_injection"]["mean"],
    )

    rank_impact = []
    for name, run_data in run_map.items():
        rank_impact.append(
            {
                "run": name,
                "lora_rank": run_data["lora_rank"],
                "lora_alpha": run_data["lora_alpha"],
                "test_f1_injection_mean": run_data["aggregated"]["test_f1_injection"]["mean"],
                "test_f1_macro_mean": run_data["aggregated"]["test_f1_macro"]["mean"],
                "test_f1_micro_mean": run_data["aggregated"]["test_f1_micro"]["mean"],
                "test_pr_auc_mean": run_data["aggregated"]["test_pr_auc"]["mean"],
                "test_fp_rate_safe_mean": run_data["aggregated"]["test_fp_rate_safe"]["mean"],
            }
        )

    payload = {
        "assignment_owner": "Deeraj",
        "assignment_config": {
            "model": args.model_name,
            "max_length": args.max_length,
            "batch_size": args.batch_size,
            "effective_batch_size": args.batch_size * args.gradient_accumulation_steps,
            "epochs": args.epochs,
            "adapter_lr": args.adapter_lr,
            "head_lr": args.head_lr,
            "seeds": seeds,
            "lora_alpha": args.lora_alpha,
            "lora_ranks": lora_ranks,
            "target_modules": [part.strip() for part in args.target_modules.split(",") if part.strip()],
            "qlora": bool(args.qlora),
            "gradient_checkpointing": bool(args.gradient_checkpointing),
            "force_cpu": bool(args.force_cpu),
        },
        "required_submission_fields": {
            "memory_and_training_profile": "Included per seed as peak_gpu_ram_gb and train_wall_time_minutes",
            "lora_rank_alpha_and_impact": "Included as lora_rank/lora_alpha and lora_rank_impact table",
            "comparison_against_best_encoder_baseline": "Use layer 2/eval_config4.py to generate comparison_baseline.json",
        },
        "runs": run_map,
        "selected_best_run": best_run_name,
        "lora_rank_impact": rank_impact,
    }

    results_json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\\nSaved training report: {results_json_path}")
    print(f"Selected best run: {best_run_name}")


if __name__ == "__main__":
    main()
