# Prompt Injection Defense System - Technical Overview

## Problem Statement
This project protects an LLM chat backend from prompt-injection attacks before model generation is executed.

The core problem is binary risk detection under real conversational traffic:
1. Separate benign user intent from malicious instruction override attempts.
2. Detect direct and indirect injection patterns (ignore previous instructions, system prompt extraction, jailbreak, encoded payloads, tool-abuse style prompts).
3. Keep false positives low enough to avoid blocking normal user requests.
4. Return an explainable security verdict that can be enforced in API routes.

## How the Problem Occurs in Practice
Prompt injection appears when untrusted text is treated like trusted instruction. In this system, common failure paths are:

1. Direct override attacks:
   - User prompt includes commands such as "ignore previous instructions" or "act as system/admin".
2. Multi-turn intent drift:
   - Early benign turns build trust; later turns gradually shift model behavior toward unsafe actions.
3. Prompt leakage attempts:
   - User asks for hidden instructions, internal prompt text, secret IDs, or system policies.
4. Obfuscated payloads:
   - Attack text is encoded, reformatted, or split to bypass simple keyword filters.
5. Role and boundary confusion:
   - Prompt tries to blur data vs instruction boundaries in chat context.
6. Indirect attack style:
   - Malicious text is embedded in seemingly normal content and executed as instruction by the model.

This is why the architecture mixes four complementary layers: behavior drift detection, heuristic signatures, ML semantic detection, and active canary leakage testing.

## What Input We Process
The security pipeline accepts either:
1. A single prompt string.
2. A full multi-turn message list (`role`, `content`) for session-aware checks.

In production chat flow, full message history is passed so intent-shift and multi-turn attack behavior can be detected.

## Technical Approach Used

### Runtime Execution Path
Actual execution path in this codebase:
1. `server/app/api/routes/chat.py` receives request.
2. `PromptSecurityPipeline` instance is initialized at module level.
3. `await security_pipeline.check_prompt(messages=..., session_id=...)` runs before LLM completion.
4. If unsafe: API returns rejection.
5. If safe: request proceeds to Groq completion and persistence.

### Layered Detection Architecture (4 Layers)

#### Layer 0 - Control Plane Detection
File: `layer 0/control_plane.py`

Purpose:
1. Detect control-plane and intent-shift attacks across turns.
2. Catch role takeover/jailbreak style drift.

Output:
1. LayerResult with normalized risk score in 0-100.
2. Structured details for cause and session context.

#### Layer 1 - Heuristic Analyzer
File: `server/app/security/layer1_heuristic.py`

Purpose:
1. Fast weighted keyword and pattern scoring.
2. Early detection of common attack signatures.

Output:
1. Raw heuristic score.
2. Normalized score.
3. Matched keywords and weights.

#### Layer 2 - ML Classifier
File: `server/app/security/layer2_ml.py`

Purpose:
1. Transformer-based binary prompt classification.
2. Deeper semantic detection beyond hard-coded patterns.

Current configured model:
1. `TheDeepDas/prompt-injection-deberta`
2. Override supported through env var `LAYER2_MODEL_NAME`.

Output:
1. Label (`SAFE` or `INJECTION`).
2. Confidence score.
3. Risk score mapped to normalized 0-100.

#### Layer 3 - Canary Token Test
File: `server/app/security/layer3_canary.py`

Purpose:
1. Active leakage test by embedding a secret canary token in system context.
2. Confirm whether prompt can force secret extraction behavior.

Output:
1. Binary risk signal (pass/fail leak test).
2. Details for canary test status.

### Final Scoring and Verdict
File: `server/app/security/scoring.py`

Approach:
1. Aggregate all normalized layer scores with configurable weights.
2. Apply veto conditions (for immediate reject on critical events).
3. Return final `SecurityCheckResult`.

Returned fields:
1. `safe` (bool)
2. `score` (0-100)
3. `breakdown` per layer
4. `layer_details` for debugging and explainability
5. `reason` when blocked

## Output We Are Dealing With
System output is not only a block/allow flag. It is an explainable security object that the API uses for policy enforcement:

1. `safe=true`: request continues to LLM generation.
2. `safe=false`: request is rejected with reason and per-layer evidence.
3. Logs and telemetry can use per-layer breakdown for tuning thresholds and model updates.

## Deployment Notes From Current Refactor
1. Layer 0 was reorganized into root folder: `layer 0/`.
2. Security pipeline imports Layer 0 via shim in `server/app/security/layer0_control_plane.py`.
3. Layer 2 model name switched from Medhavi to `prompt-injection-deberta` default repo path.

---

## Dataset and Model Experiments for Layer 2 (at the end as requested)

### Final Training Dataset Recommendation
Use only **xTRam1/safe-guard-prompt-injection**.

Reason:
1. It is the largest directly labeled prompt-injection dataset found during research.
2. It already contains broad prompt-injection families in one consistent schema.
3. It avoids cross-dataset label/style mismatch.

Data policy:
1. Deduplicate exact prompt duplicates inside this dataset.
2. Stratified 80/10/10 split by label.
3. Keep a challenge subset from attack-heavy samples for stress testing.

### What We Target in Layer 2 (from xTRam1/safe-guard-prompt-injection)
Based on the largest labeled dataset, Layer 2 is trained to detect these target attack families:

1. Instruction override and policy bypass:
   - "ignore/disregard previous instructions", "developer mode", "DAN-style" prompts.
2. Prompt extraction and secret retrieval:
   - Requests to reveal system prompt, hidden rules, keys, or internal messages.
3. Jailbreak-style harmful steering:
   - Prompts designed to push the model outside safety policy boundaries.
4. Role takeover and authority spoofing:
   - User impersonates system/developer/admin roles.
5. Obfuscated or transformed attack content:
   - Rephrased, encoded, or noisy variants intended to evade pattern-only detection.
6. Mixed benign + malicious prompts:
   - Prompts that appear normal but contain latent attack instructions.

This target set is fully aligned to one dataset distribution, which simplifies training and evaluation.

### How to Add the Dataset (step-by-step)

Use this process to build the single-source Layer 2 training set locally.

1. Install dependencies in your training environment:

```bash
pip install datasets pandas pyarrow scikit-learn
```

2. Create folder structure at repo base:

```text
data/
  raw/
  processed/
```

3. Download dataset from Hugging Face:

```python
from datasets import load_dataset

ds_xtram = load_dataset("xTRam1/safe-guard-prompt-injection")
```

4. Normalize into common schema:
   - Required columns:
     - `text` (string)
     - `label` (0=safe, 1=injection)
     - `source` (fixed value: `xtram1_safe_guard_prompt_injection`)

5. Map labels:
   - Map xTRam1 attack/injection class to `1`
   - Map xTRam1 safe/benign class to `0`

6. Deduplicate rows:
   - Exact dedup on normalized text
   - Optional near-dedup with lowercase + whitespace collapse

7. Split with stratification:
   - Train/Val/Test = 80/10/10
   - Stratify by label

8. Save artifacts:
   - `data/processed/xtram1_train.csv`
   - `data/processed/xtram1_val.csv`
   - `data/processed/xtram1_test.csv`

9. Verify quality before training:
   - Check class balance
   - Check duplicate leakage across splits

Example normalization sketch:

```python
import pandas as pd

def normalize(df, text_col, label_col, pos_values, source):
    out = pd.DataFrame()
    out["text"] = df[text_col].astype(str).str.strip()
    out["label"] = df[label_col].apply(lambda x: 1 if x in pos_values else 0)
    out["source"] = source
    return out
```

### Team Assignment: 4 People Testing 4 Models

Each person owns one model track end-to-end on the same dataset split (`xtram1_train/val/test.csv`) for fair comparison.

Common rules for all 4 members:
1. Use same preprocessing and same train/val/test files.
2. Run at least 3 seeds per config (`42, 43, 44`).
3. Report mean and std for key metrics.
4. Save best checkpoint and inference latency.
5. Submit final results in the shared comparison template.

#### Config 1 - Owner: Deep
1. Model: `answerdotai/ModernBERT-large`
2. Max length: 384
3. LR: 1.5e-5
4. Batch: 16 (accumulate to effective 64)
5. Epochs: 4
6. Loss: weighted CE + label smoothing 0.03

Deep must submit:
1. Best threshold for inference (not only 0.5).
2. Confusion matrix on test set.
3. Failure analysis for 20 false positives and 20 false negatives.

#### Config 2 - Owner: Yash
1. Model: `microsoft/deberta-v3-large`
2. Max length: 256
3. LR: 2e-5
4. Batch: 24
5. Epochs: 4
6. Loss: focal loss (`gamma=2.0`) with class weights

Yash must submit:
1. Effect of focal loss vs plain CE (ablation run).
2. Injection-class recall trend across epochs.
3. Precision-recall curve image or exported values.

#### Config 3 - Owner: Jaival
1. Model: `roberta-large`
2. Max length: 256
3. LR: 1e-5
4. Batch: 32
5. Epochs: 5
6. Extras: hard-negative batch mix + R-Drop regularization

Jaival must submit:
1. Robustness comparison with and without hard-negative mix.
2. OOD-style evaluation on obfuscated prompts subset.
3. Calibration check (confidence vs correctness buckets).

#### Config 4 - Owner: Deeraj
1. Model: `meta-llama/Llama-Guard-3-1B` (LoRA/QLoRA adaptation)
2. Max length: 512
3. Adapter LR: 1e-4, head LR: 2e-5
4. Batch: 8 (accumulate to effective 64)
5. Epochs: 3
6. Focus: improve detection of implicit and multi-step attacks

Deeraj must submit:
1. Memory and training-time profile (GPU RAM + wall time).
2. LoRA rank/alpha used and impact on metrics.
3. Comparison against best encoder baseline on same test set.

### Shared Results Template (all 4 members)
Every person should report these final fields:
1. Model name and exact config
2. Best validation epoch/checkpoint
3. Test F1 (injection class)
4. Test PR-AUC
5. Test false positive rate on safe prompts
6. Inference latency (ms per sample)
7. Model size (params / checkpoint size)
8. Top 5 failure patterns observed

### Selection Criteria
Choose final Layer 2 checkpoint by:
1. Highest injection-class F1.
2. Highest PR-AUC on hard-attack subset.
3. Lowest false-positive rate on clean benign traffic.
4. Acceptable latency/memory for server deployment.
