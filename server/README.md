To run fastapi, 

uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000



┌─────────────────────────────────────────────────────────────────────────┐
│                Prompt Ingestion Detection Pipeline                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   User Prompt                                                           │
│        │                                                                │
│        ▼                                                                │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                    Layer 1: Heuristic Analysis                  │   │
│   │                                                                 │   │
│   │  - Pattern matching against 500+ weighted keywords              │   │
│   │  - Compiled regex for O(n) performance                          │   │
│   │  - Weights derived from statistical analysis of attack datasets │   │
│   │                                                                 │   │
│   │  Output: Cumulative risk score (0 to unbounded)                 │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│        │                                                                │
│        ▼                                                                │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                  Layer 2: ML Classification                     │   │
│   │                                                                 │   │
│   │  - DeBERTa-v3 transformer model (protectai/deberta-v3-base)     │   │
│   │  - FastAPI microservice hosted on Hugging Face Spaces           │   │
│   │  - Binary classification: SAFE / INJECTION                      │   │
│   │                                                                 │   │
│   │  Output: Probability score (0.0 to 1.0)                         │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│        │                                                                │
│        ▼                                                                │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                 Layer 3: Canary Token Testing                   │   │
│   │                                                                 │   │
│   │  - Generates unique UUID canary token per request               │   │
│   │  - Embeds token in system prompt with strict instructions       │   │
│   │  - Tests if user prompt can extract the secret token            │   │
│   │                                                                 │   │
│   │  Output: Binary (0 = passed, 100 = canary leaked)               │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│        │                                                                │
│        ▼                                                                │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                      Scoring Service                            │   │
│   │                                                                 │   │
│   │  - Normalizes all layer scores to 0-100 scale                   │   │
│   │  - Applies configurable weights (default: 25%, 35%, 40%)        │   │
│   │  - Checks veto conditions for immediate rejection               │   │
│   │  - Computes final weighted risk score                           │   │
│   │                                                                 │   │
│   │  Output: Final score + safety verdict                           │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│        │                                                                │
│        ▼                                                                │
│   Response: { safe: bool, score: float, breakdown: {...} }              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘