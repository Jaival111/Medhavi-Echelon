"""
Layer 2: ML Classification
Prompt-injection transformer model for binary classification
"""
import csv
import sys
import math
from typing import List, Tuple, Optional
import os

import torch
import torch.nn.functional as F
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from .models import LayerResult

try:
    from tqdm import tqdm
except ImportError:  # fallback if tqdm isn't installed
    def tqdm(iterable=None, **_kwargs):
        return iterable if iterable is not None else []


MODEL_NAME = os.getenv("LAYER2_MODEL_NAME", "TheDeepDas/prompt-injection-deberta")
BATCH_SIZE = 16
MAX_LENGTH = 512

csv.field_size_limit(min(sys.maxsize, 2147483647))


class MLClassifier:
    """
    Machine learning classifier for prompt injection detection.
    Provides binary classification with risk scoring.
    """
    
    def __init__(
        self,
        model_name: str = MODEL_NAME,
        batch_size: int = BATCH_SIZE,
        max_length: int = MAX_LENGTH,
        min0: float = 0.9996,
        max0: float = 1.0,
        min1: float = 0.9996,
        max1: float = 1.0,
    ):
        """
        Initialize ML classifier.
        
        Args:
            model_name: Name of the HuggingFace model to use
            batch_size: Batch size for processing
            max_length: Maximum token length
            min0, max0: Min/max values for label 0 (safe) scaling
            min1, max1: Min/max values for label 1 (injection) scaling
        """
        self.model_name = model_name
        self.batch_size = batch_size
        self.max_length = max_length
        self.min0 = min0
        self.max0 = max0
        self.min1 = min1
        self.max1 = max1
        
        # Lazy load model
        self._tokenizer = None
        self._model = None
        self._device = None
    
    def _load_model_and_tokenizer(self):
        """Load model and tokenizer (lazy initialization)"""
        if self._model is None:
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self._model.to(self._device)
            self._model.eval()
    
    def _predict_scores(
        self,
        texts: List[str],
    ) -> Tuple[List[float], List[int]]:
        """
        Predict scores and labels for a list of texts.
        
        Args:
            texts: List of text strings to classify
            
        Returns:
            Tuple of (scores, labels)
        """
        self._load_model_and_tokenizer()
        
        scores: List[float] = []
        labels: List[int] = []

        for i in range(0, len(texts), self.batch_size):
            batch_texts = texts[i : i + self.batch_size]
            inputs = self._tokenizer(
                batch_texts,
                return_tensors="pt",
                truncation=True,
                max_length=self.max_length,
                padding=True,
            )
            inputs = {k: v.to(self._device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._model(**inputs)
                probs = F.softmax(outputs.logits, dim=-1)
                batch_scores, batch_labels = torch.max(probs, dim=-1)

            scores.extend(batch_scores.detach().cpu().tolist())
            labels.extend(batch_labels.detach().cpu().tolist())

        return scores, labels
    
    def _min_max_scale(self, value: float, min_val: float, max_val: float) -> float:
        """Scale value using min-max normalization"""
        if max_val == min_val:
            return 0.0
        return (value - min_val) / (max_val - min_val)
    
    async def classify(self, prompt: str) -> LayerResult:
        """
        Classify a single prompt using the configured transformer model.
        
        Args:
            prompt: User prompt to classify
            
        Returns:
            LayerResult with risk score (0.0 to 1.0)
        """
        try:
            # Predict for single text
            scores, labels = self._predict_scores([prompt])
            
            score = scores[0]
            label = labels[0]
            
            # Calculate risk score based on label
            if label == 0:
                scaled = self._min_max_scale(score, self.min0, self.max0)
                risk_score = scaled / 2.0
            else:
                scaled = self._min_max_scale(score, self.min1, self.max1)
                risk_score = (scaled / 2.0) + 0.5
            
            # Normalize to 0-100 scale
            normalized_score = risk_score * 100.0
            
            return LayerResult(
                score=risk_score,
                normalized_score=normalized_score,
                passed=risk_score < 0.5,  # Threshold at 0.5
                details={
                    "label": "INJECTION" if label == 1 else "SAFE",
                    "confidence": score,
                    "risk_score": risk_score,
                    "model": self.model_name
                }
            )
        
        except Exception as e:
            # Fallback on error
            return LayerResult(
                score=0.0,
                normalized_score=0.0,
                passed=True,  # Fail open
                details={
                    "error": str(e),
                    "fallback": True
                }
            )
    
    def batch_process_csv(
        self,
        input_file: str,
        output_file: str,
        text_col: str = "text"
    ) -> None:
        """
        Process a CSV file in batch mode.
        
        Args:
            input_file: Path to input CSV file
            output_file: Path to output CSV file
            text_col: Name of the column containing text to classify
        """
        self._load_model_and_tokenizer()
        
        # Read input CSV
        with open(input_file, "r", encoding="utf-8") as infile:
            reader = csv.DictReader(infile)
            rows = list(reader)
        
        if not rows:
            print("No rows found in input file")
            return
        
        # Extract texts
        texts = [row.get(text_col, "") for row in rows]
        
        # Predict scores
        print(f"Processing {len(texts)} texts...")
        scores, labels = self._predict_scores(texts)
        
        # Add scores to rows
        for i, row in enumerate(rows):
            score = scores[i]
            label = labels[i]
            
            row["score"] = f"{score:.6f}"
            
            if label == 0:
                scaled = self._min_max_scale(score, self.min0, self.max0)
                risk_score = scaled / 2.0
            else:
                scaled = self._min_max_scale(score, self.min1, self.max1)
                risk_score = (scaled / 2.0) + 0.5
            
            row["risk_score"] = f"{risk_score:.6f}"
        
        # Write output CSV
        fieldnames = list(rows[0].keys()) if rows else []
        if "score" not in fieldnames:
            fieldnames.append("score")
        if "risk_score" not in fieldnames:
            fieldnames.append("risk_score")
        
        with open(output_file, "w", encoding="utf-8", newline="") as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"Scored CSV written to: {output_file}")
