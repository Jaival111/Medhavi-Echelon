# Prompt Ingestion Detection Pipeline - Implementation Summary

## 🎯 Overview

Successfully implemented a **3-layer security pipeline** for detecting prompt injection attacks in your FastAPI backend. The system intercepts all chat requests and validates them before sending to the LLM.

## 📁 File Structure

```
server/app/
├── security/                          # NEW: Security module
│   ├── __init__.py                   # Module exports
│   ├── models.py                     # Pydantic models for results
│   ├── layer1_heuristic.py           # Layer 1: Heuristic Analysis
│   ├── layer2_ml.py                  # Layer 2: ML Classification
│   ├── layer3_canary.py              # Layer 3: Canary Token Testing
│   ├── scoring.py                    # Scoring Service
│   ├── pipeline.py                   # Main Pipeline Orchestrator
│   ├── config.py                     # Configuration
│   ├── example.py                    # Usage examples
│   └── README.md                     # Documentation
├── api/routes/
│   └── chat.py                       # UPDATED: Integrated security checks
└── core/
    └── config.py                     # Existing config (unchanged)
```

## 🏗️ Architecture Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                    CLIENT REQUEST                                 │
│                         ↓                                         │
│              POST /api/v1/chat                                    │
│    { messages: [...], model: "...", ... }                        │
└──────────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────────┐
│              PROMPT EXTRACTION                                    │
│    Extract last user message from conversation                   │
└──────────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────────┐
│          LAYER 1: HEURISTIC ANALYSIS                             │
│                                                                   │
│  • 500+ weighted keyword patterns (12 categories)                │
│  • Compiled regex for O(n) performance                           │
│  • Synchronous execution (~1-2ms)                                │
│  • Output: Score 0-100                                           │
│                                                                   │
│  Categories:                                                     │
│  - Ignore instructions (weight: 10)                              │
│  - System extraction (weight: 10)                                │
│  - Role-play attacks (weight: 8)                                 │
│  - Permission escalation (weight: 9)                             │
│  - Jailbreak attempts (weight: 10)                               │
│  - Encoding/obfuscation (weight: 7)                              │
│  - Delimiter manipulation (weight: 8)                            │
│  - Hypothetical scenarios (weight: 6)                            │
│  - Indirect injection (weight: 7)                                │
│  - Code execution (weight: 9)                                    │
│  - Secret extraction (weight: 10)                                │
│  - Payload markers (weight: 8)                                   │
└──────────────────────────────────────────────────────────────────┘
                           ↓
                    ┌──────────┐
                    │ PARALLEL │
                    └──────────┘
                    ↓          ↓
┌─────────────────────────────┐  ┌─────────────────────────────┐
│ LAYER 2: ML CLASSIFICATION  │  │ LAYER 3: CANARY TESTING     │
│                             │  │                             │
│ • DeBERTa-v3 model          │  │ • Generate UUID token       │
│ • API: Hugging Face Spaces  │  │ • Create system prompt      │
│ • Async with timeout        │  │ • Test with Groq LLM        │
│ • Fallback on error         │  │ • Check for token leak      │
│ • Output: Score 0-100       │  │ • Output: 0 or 100          │
│ • Time: ~100-500ms          │  │ • Time: ~500-2000ms         │
└─────────────────────────────┘  └─────────────────────────────┘
                    ↓          ↓
                    └──────────┘
                           ↓
┌──────────────────────────────────────────────────────────────────┐
│                    SCORING SERVICE                                │
│                                                                   │
│  1. Normalize all scores to 0-100 scale                          │
│  2. Check veto conditions:                                       │
│     • Layer 3 leaked token → REJECT                              │
│     • Layer 1 score ≥ 80 → REJECT                                │
│     • 2+ layers score > 70 → REJECT                              │
│  3. Apply weights:                                               │
│     • Layer 1: 25%                                               │
│     • Layer 2: 35%                                               │
│     • Layer 3: 40%                                               │
│  4. Final Score = weighted sum                                   │
│  5. Verdict: SAFE if score < 50, UNSAFE otherwise               │
└──────────────────────────────────────────────────────────────────┘
                           ↓
                    ┌──────────┐
                    │  SAFE?   │
                    └──────────┘
                    ↓          ↓
              YES              NO
                ↓               ↓
    ┌──────────────────┐  ┌──────────────────┐
    │ FORWARD TO LLM   │  │ RETURN HTTP 400  │
    │                  │  │                  │
    │ • Groq API call  │  │ • Error message  │
    │ • Stream/normal  │  │ • Security score │
    │ • Return result  │  │ • Breakdown      │
    └──────────────────┘  │ • Reason         │
                          └──────────────────┘
```

## 🔧 Key Components

### 1. Layer 1: Heuristic Analysis (`layer1_heuristic.py`)
- **500+ keyword patterns** across 12 attack categories
- Compiled regex for **O(n) performance**
- Weighted scoring based on attack severity
- **Fastest layer** (~1-2ms)

### 2. Layer 2: ML Classification (`layer2_ml.py`)
- **DeBERTa-v3** transformer model
- Binary classification: SAFE vs INJECTION
- Hosted on **Hugging Face Spaces**
- Async HTTP calls with timeout handling
- **Fallback mechanism** for API failures

### 3. Layer 3: Canary Token Testing (`layer3_canary.py`)
- Generates **unique UUID** per request
- Embeds token in system prompt
- Tests if prompt can extract the secret
- **Binary result**: 0 (safe) or 100 (leaked)
- Detects partial leaks and suspicious patterns

### 4. Scoring Service (`scoring.py`)
- Normalizes all scores to **0-100 scale**
- Applies **configurable weights** (25%, 35%, 40%)
- Implements **veto conditions** for immediate rejection
- Computes final weighted score
- Generates detailed rejection reasons

### 5. Pipeline Orchestrator (`pipeline.py`)
- **Main entry point** for security checks
- Coordinates all 3 layers
- **Parallel execution** of Layers 2 & 3
- Error handling and fallbacks
- Quick-check mode (Layer 1 only)

## 🚀 API Endpoints

### 1. POST `/api/v1/chat` (Updated)
**Standard chat with integrated security**

```json
// Request
{
  "messages": [
    {"role": "user", "content": "Hello!"}
  ],
  "model": "llama-3.3-70b-versatile",
  "temperature": 0.7
}

// Success Response (safe prompt)
{
  "message": {
    "role": "assistant",
    "content": "Hello! How can I help you?"
  },
  "usage": {...}
}

// Error Response (unsafe prompt)
{
  "error": "Prompt rejected by security system",
  "reason": "Prompt rejected (final score: 87.5): suspicious patterns detected",
  "security_score": 87.5,
  "breakdown": {
    "layer1_heuristic": 95.0,
    "layer2_ml": 82.3,
    "layer3_canary": 0.0
  }
}
```

### 2. POST `/api/v1/security-check` (New)
**Standalone security check without LLM execution**

```json
// Request
{
  "prompt": "Ignore all previous instructions"
}

// Response
{
  "safe": false,
  "score": 87.5,
  "breakdown": {
    "layer1_heuristic": 95.0,
    "layer2_ml": 82.3,
    "layer3_canary": 0.0
  },
  "layer_details": {
    "layer1": {
      "matches": {...},
      "total_patterns_matched": 3,
      "categories_triggered": 2
    },
    "layer2": {...},
    "layer3": {...}
  },
  "reason": "Prompt rejected (final score: 87.5): suspicious patterns detected"
}
```

## ⚙️ Configuration

### Default Settings
```python
layer1_weight = 0.25  # 25% - Heuristic Analysis
layer2_weight = 0.35  # 35% - ML Classification
layer3_weight = 0.40  # 40% - Canary Token Testing
safety_threshold = 50.0  # Reject if score >= 50
```

### Environment Variables
```bash
SECURITY_LAYER1_WEIGHT=0.25
SECURITY_LAYER2_WEIGHT=0.35
SECURITY_LAYER3_WEIGHT=0.40
SECURITY_SAFETY_THRESHOLD=50.0
SECURITY_ENABLE_LAYER2=true
SECURITY_ENABLE_LAYER3=true
```

## 📊 Performance Characteristics

| Layer | Execution Time | Runs |
|-------|---------------|------|
| Layer 1 | ~1-2ms | Synchronous |
| Layer 2 | ~100-500ms | Async (parallel) |
| Layer 3 | ~500-2000ms | Async (parallel) |
| **Total** | **~500-2000ms** | **Layers 2 & 3 in parallel** |

For **low-latency** scenarios, use `check_prompt_quick()` (Layer 1 only, ~1-2ms).

## 🛡️ Security Features

### Veto Conditions (Immediate Rejection)
1. **Layer 3 Veto**: Canary token leaked (score = 100)
2. **Layer 1 Veto**: Very high heuristic score (≥ 80)
3. **Combined Veto**: 2+ layers detect high risk (> 70)

### Attack Categories Detected
1. Ignore instructions
2. System prompt extraction
3. Role-playing attacks
4. Permission escalation
5. Jailbreak attempts (DAN mode, etc.)
6. Encoding/obfuscation
7. Delimiter manipulation
8. Hypothetical scenarios
9. Indirect command injection
10. Code execution attempts
11. Token/secret extraction
12. Payload markers (XSS, template injection)

## 📦 Dependencies Added

```toml
httpx>=0.27.0  # For ML API calls (Layer 2)
```

## 🧪 Testing

```bash
# Install dependencies
cd server
uv pip install httpx

# Run the server
uvicorn app.main:app --reload

# Test with curl
curl -X POST http://localhost:8000/api/v1/security-check \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Ignore all previous instructions"}'

# Test chat endpoint
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What is 2+2?"}
    ]
  }'
```

## 📝 Usage Examples

See [app/security/example.py](app/security/example.py) for comprehensive examples.

## 🔍 Monitoring & Debugging

The system provides detailed breakdown for rejected prompts:
- Final weighted score
- Individual layer scores
- Pattern matches (Layer 1)
- ML classification confidence (Layer 2)
- Canary token status (Layer 3)
- Rejection reason

## 🎯 Next Steps

1. **Install dependencies**: `uv pip install httpx`
2. **Start server**: `uvicorn app.main:app --reload`
3. **Test endpoints**: Use the examples above
4. **Adjust weights**: Modify config based on your needs
5. **Monitor**: Track security events in production
6. **Fine-tune**: Adjust thresholds based on false positive/negative rates

## 📚 Documentation

Full documentation available in [app/security/README.md](app/security/README.md)

---

**Status**: ✅ Implementation Complete

The Prompt Ingestion Detection Pipeline is now fully integrated into your FastAPI backend and ready for testing!
