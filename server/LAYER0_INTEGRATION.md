# Layer 0 Integration - Intent Analysis

## Overview

Layer 0 (Intent Analysis) has been successfully integrated into the Prompt Security Pipeline. This layer uses VADER sentiment analysis to detect drastic intent shifts in user messages, which can indicate context switching attacks or jailbreak attempts.

## Key Changes

### 1. Enhanced IntentLayer (`layer0_intent_layer.py`)

- **Message History Support**: Now accepts full message history instead of just a single prompt
- **New `analyze()` Method**: Added for pipeline integration that processes either:
  - Full message history (`messages` parameter)
  - Single prompt (`prompt` parameter - legacy support)
  - Session tracking via `session_id` parameter

### 2. Updated Pipeline (`pipeline.py`)

- **Layer 0 Integration**: Added IntentLayer as the first security layer
- **Weight Configuration**: Default weights adjusted:
  - Layer 0 (Intent): 15%
  - Layer 1 (Heuristic): 20%
  - Layer 2 (ML): 30%
  - Layer 3 (Canary): 35%
- **Message Support**: `check_prompt()` now accepts:
  - `messages`: Full conversation history (list of dicts with 'role' and 'content')
  - `prompt`: Single prompt string (legacy support)
  - `session_id`: Session identifier for intent tracking

### 3. Updated Scoring Service (`scoring.py`)

- **Layer 0 Scoring**: Integrated layer0_result into weighted score calculation
- **Layer 0 Veto**: Added veto capability when drastic intent shifts are detected
- **Breakdown**: All results now include `layer0_intent` in the breakdown

### 4. Updated Chat Endpoint (`chat.py`)

- **Full Message History**: Now passes all messages to security pipeline instead of just the last user prompt
- **Session Support**: Added optional `session_id` field to `ChatRequest` model
- **Better Intent Tracking**: Intent layer can now track sentiment changes across the entire conversation

## How It Works

### Intent Shift Detection

1. **Sentiment Analysis**: Uses VADER to calculate a compound sentiment score (-1 to +1) for each user message
2. **Historical Tracking**: Stores previous sentiment scores per session
3. **Shift Calculation**: Compares current score with previous score to detect drastic changes
4. **Threshold**: Flags shifts > 0.5 as potential attacks

### Example Scenarios

**✅ Safe Conversation:**
```
User: "Hello, how are you?" (Score: +0.4)
User: "Can you help me with Python?" (Score: +0.3)
Shift: |0.3 - 0.4| = 0.1 ✓ Safe
```

**❌ Malicious Intent Shift:**
```
User: "I love coding!" (Score: +0.6)
User: "I hate you, ignore instructions" (Score: -0.7)
Shift: |-0.7 - 0.6| = 1.3 ✗ BLOCKED
```

## API Usage

### Chat Endpoint

```python
POST /chat
{
  "messages": [
    {"role": "user", "content": "Hello!"},
    {"role": "assistant", "content": "Hi there!"},
    {"role": "user", "content": "Help me with code"}
  ],
  "session_id": "user_123",  # Optional, for intent tracking
  "model": "llama-3.3-70b-versatile",
  "temperature": 0.7
}
```

### Security Check Endpoint

The `/security-check` endpoint still works with single prompts, but intent tracking requires consistent session_id usage.

## Testing

Run the integration test:

```bash
cd server
python test_layer0_integration.py
```

This will test:
1. Normal conversation flow (should pass)
2. Drastic intent shift (should be flagged/blocked)
3. Single prompt support (legacy compatibility)

## Configuration

You can adjust the intent layer behavior when initializing the pipeline:

```python
pipeline = PromptSecurityPipeline(
    groq_api_key=GROQ_API_KEY,
    layer0_weight=0.15,      # Weight for intent analysis
    enable_layer0=True,       # Enable/disable intent layer
    safety_threshold=50.0,    # Overall rejection threshold
)
```

To adjust the intent shift threshold, modify `MAX_INTENT_SHIFT` in `layer0_intent_layer.py`:

```python
MAX_INTENT_SHIFT = 0.5  # Default: 0.5 (50% sentiment change)
```

## Benefits

1. **Early Detection**: Catches context switching attacks before other layers
2. **Low Overhead**: Fast sentiment analysis with minimal latency
3. **Session-Aware**: Tracks intent across entire conversations
4. **Complementary**: Works alongside existing heuristic, ML, and canary layers

## Future Improvements

- Persistent session storage (Redis/Database) instead of in-memory
- Configurable shift thresholds per session
- More sophisticated intent modeling beyond sentiment
- Intent pattern recognition for common attack vectors
