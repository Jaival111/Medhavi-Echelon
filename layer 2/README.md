# Layer 2 and Security Pipeline Technical Plan

## 1) Verified Runtime Execution Path (actual code path)

This is where execution really happens in your current backend:

1. Chat request enters API routes in `server/app/api/routes/chat.py`
2. `security_pipeline = PromptSecurityPipeline(...)` is created at module load
3. On requests to `POST /api/v1/chat/` and `POST /api/v1/chat/{chat_id}`, code calls:
  - `await security_pipeline.check_prompt(messages=..., session_id=...)`
4. Pipeline orchestration runs from `server/app/security/pipeline.py`
5. Final allow/reject decision is produced by `server/app/security/scoring.py`
6. Output schema returned to API is defined in `server/app/security/models.py`

## 2) Layer Architecture (confirmed)

Yes, your system currently has **4 detection layers** plus one scoring aggregator:

1. Layer 0 (`layer 0/control_plane.py` via import shim): control-plane and multi-turn intent shift detection
2. Layer 1 (`server/app/security/layer1_heuristic.py`): regex + weighted keyword heuristics
3. Layer 2 (`server/app/security/layer2_ml.py`): transformer classifier (currently `TheDeepDas/prompt-injection-deberta`)
4. Layer 3 (`server/app/security/layer3_canary.py`): active canary-token leakage test via LLM
5. Aggregation (`server/app/security/scoring.py`): weighted scoring + veto rules

## 3) Technical Problem Definition

### Problem
Detect whether an incoming prompt (or latest user message in a conversation) is a prompt-injection attempt before LLM response generation.

### Input
- `prompt` string, or
- `messages` list with role/content

### Output
The pipeline returns `SecurityCheckResult`:
- `safe: bool`
- `score: float` in [0, 100]
- `breakdown: {layer0_intent, layer1_heuristic, layer2_ml, layer3_canary}`
- `layer_details: per-layer debug payload`
- `reason: rejection reason if unsafe`

### Decision logic
- Weighted score threshold comparison (`safety_threshold`)
- Veto triggers can force immediate rejection:
  - Layer 0 veto (intent shift)
  - Layer 3 veto (canary extraction)
  - Multi-layer high-risk combination veto

## 4) Dataset Research and Final Training Dataset

### Dataset candidates evaluated
1. xTRam1/safe-guard-prompt-injection (10,296 rows; broad attack classes)
2. deepset/prompt-injections (small, high-signal set, 662 rows)
3. jackhhao/jailbreak-classification (1,306 rows; jailbreak/benign)
4. Open-Prompt-Injection toolkit (for generating hard synthetic variants)

### Final dataset for training (recommended)
Use only **xTRam1/safe-guard-prompt-injection**.

1. It is the largest directly labeled dataset found in this research set.
2. It has broad attack families already represented.
3. It avoids cross-source label/style mismatch from merged corpora.

### Data policy
1. Deduplicate exact and near-duplicate prompts in this dataset
2. Stratified split (80/10/10)
3. Keep hard-attack challenge slice for final evaluation
4. Track both global metrics and hard-slice metrics

## 5) Four Diverse Model Configurations (not all DeBERTa)

Below is a diverse experimental slate for xTRam1/safe-guard-prompt-injection. One is SOTA-oriented, the others are strong trials to improve accuracy/robustness.

### Config 1 (SOTA-oriented): ModernBERT-large classifier
- Model: `answerdotai/ModernBERT-large`
- Why: Strong recent encoder family for classification with long-context efficiency
- Max length: 384
- LR: 1.5e-5
- Batch size: 16 (use grad accumulation to effective 64)
- Epochs: 4
- Weight decay: 0.01
- Loss: weighted CE + label smoothing (0.03)
- Target: best overall F1 + PR-AUC on challenge split

### Config 2 (high-accuracy baseline): DeBERTa-v3-large
- Model: `microsoft/deberta-v3-large`
- Why: proven strong baseline on many classification tasks
- Max length: 256
- LR: 2e-5
- Batch size: 24
- Epochs: 4
- Weight decay: 0.01
- Loss: focal loss (`gamma=2.0`, class weights from train distribution)
- Target: improve injection recall without large FP growth

### Config 3 (robustness trial): RoBERTa-large + adversarial augmentation
- Model: `roberta-large`
- Why: architecture diversity to avoid single-family failure mode
- Max length: 256
- LR: 1e-5
- Batch size: 32
- Epochs: 5
- Weight decay: 0.05
- Training extras:
  - 30% batches from hard synthetic/obfuscated prompts
  - R-Drop KL regularization = 0.5
- Target: stronger OOD robustness and fewer brittle failures

### Config 4 (guard-specialized trial): Llama-Guard 3 1B (LoRA classification)
- Model: `meta-llama/Llama-Guard-3-1B` (binary safe/unsafe adaptation)
- Why: safety-guard tuned backbone with richer semantic safety priors
- Fine-tuning method: QLoRA/LoRA classifier adaptation
- Max length: 512
- LR: 1e-4 (adapter LR), 2e-5 (head)
- Batch size: 8 (effective 64 with accumulation)
- Epochs: 3
- Target: reduce false negatives on implicit or multi-step injections

## 6) Suggested Experiment Order

1. Run Config 2 first (stable strong baseline)
2. Run Config 1 as SOTA-oriented candidate
3. Run Config 3 for robustness stress-testing
4. Run Config 4 for semantic guard specialization

## 7) Final Model Selection Rule

Pick model by this strict order:

1. Highest injection-class F1 on validation
2. Highest PR-AUC on hard-attack challenge split
3. Lowest false positive rate on clean benign prompts
4. Stable latency and memory footprint for deployment

## 8) Important Current-State Note

Current production Layer 2 in code is **not DeBERTa-v3-base**. It is:

- `MODEL_NAME = os.getenv("LAYER2_MODEL_NAME", "TheDeepDas/prompt-injection-deberta")` in `server/app/security/layer2_ml.py`

If you move to any config above, update model loading in Layer 2 and revalidate end-to-end scoring thresholds.

## 9) Deeraj Config 4 Runbook (implemented)

The repository now includes an end-to-end workflow for Deeraj's required Config 4 deliverables.

### Files added for Config 4

1. `data/download_and_prepare_xtram1.py`
2. `layer 2/train_config4_llama_guard.py`
3. `layer 2/eval_config4.py`
4. `layer 2/requirements_config4.txt`
5. `layer 2/results_config4.json`
6. `layer 2/comparison_baseline.json`
7. `layer 2/failure_analysis.txt`

### Step A: Install dependencies

```bash
pip install -r "layer 2/requirements_config4.txt"
```

### Step B: Build the required shared dataset splits

```bash
python data/download_and_prepare_xtram1.py --output-dir data/processed --seed 42
```

Expected outputs:

1. `data/processed/xtram1_train.csv`
2. `data/processed/xtram1_val.csv`
3. `data/processed/xtram1_test.csv`

### Step C: Train Deeraj Config 4

```bash
python "layer 2/train_config4_llama_guard.py" \
  --data-dir data/processed \
  --model-name meta-llama/Llama-Guard-3-1B \
  --seeds 42,43,44 \
  --lora-ranks 8,16,32 \
  --lora-alpha 32 \
  --batch-size 8 \
  --gradient-accumulation-steps 8 \
  --epochs 3 \
  --adapter-lr 1e-4 \
  --head-lr 2e-5 \
  --max-length 512
```

Optional 4-bit training:

```bash
python "layer 2/train_config4_llama_guard.py" --qlora
```

### Step D: Evaluate and compare against baseline encoder

```bash
python "layer 2/eval_config4.py" \
  --results-json "layer 2/results_config4.json" \
  --data-dir data/processed \
  --baseline-model answerdotai/ModernBERT-large
```

### Assignment requirement mapping

1. Memory and training-time profile:
  - written per seed in `results_config4.json` as `peak_gpu_ram_gb` and `train_wall_time_minutes`
2. LoRA rank/alpha and impact on metrics:
  - written in `results_config4.json` as run config fields and `lora_rank_impact`
3. Comparison against best encoder baseline:
  - written in `comparison_baseline.json` from `eval_config4.py`

### Submission artifacts

1. `layer 2/results_config4.json`
2. `layer 2/comparison_baseline.json`
3. `layer 2/failure_analysis.txt`

## 10) Jaival Config 3 Runbook (implemented)

The repository now includes an end-to-end workflow for Jaival's required Config 3 deliverables.

### Files added for Config 3

1. `layer 2/train_config3_roberta.py`
2. `layer 2/eval_config3.py`
3. `layer 2/requirements_config3.txt`

### Step A: Install dependencies

```bash
pip install -r "layer 2/requirements_config3.txt"
```

### Step B: Build shared dataset splits (if not already created)

```bash
python data/download_and_prepare_xtram1.py --output-dir data/processed --seed 42
```

### Step C1: Train baseline without hard-negative mix

```bash
python "layer 2/train_config3_roberta.py" \
  --data-dir data/processed \
  --model-name roberta-large \
  --seeds 42,43,44 \
  --max-length 256 \
  --learning-rate 1e-5 \
  --batch-size 4 \
  --gradient-accumulation-steps 8 \
  --epochs 5 \
  --rdrop-alpha 0.5
```

### Step C2: Train with hard-negative mix (ablation pair)

```bash
python "layer 2/train_config3_roberta.py" \
  --data-dir data/processed \
  --model-name roberta-large \
  --seeds 42,43,44 \
  --max-length 256 \
  --learning-rate 1e-5 \
  --batch-size 4 \
  --gradient-accumulation-steps 8 \
  --epochs 5 \
  --rdrop-alpha 0.5 \
  --with-hard-negatives \
  --hard-negative-ratio 0.30
```

Both runs are merged into:

1. `layer 2/results_config3.json`

### Step D: Generate required Jaival evaluation report

```bash
python "layer 2/eval_config3.py" \
  --results-json "layer 2/results_config3.json" \
  --data-dir data/processed \
  --report-json "layer 2/comparison_config3.json" \
  --threshold 0.5 \
  --batch-size 32 \
  --max-length 256 \
  --calibration-bins 10
```

### Assignment requirement mapping (Jaival)

1. Robustness comparison with and without hard-negative mix:
  - `hard_negative_ablation_delta` in `comparison_config3.json`
2. OOD-style evaluation on obfuscated prompts:
  - `ood_obfuscated_metrics` and `ood_obfuscated_subset_size` per mode
3. Calibration check:
  - `calibration.ece` and per-bucket entries under `calibration.bins`
