from intent.intent_layer import IntentLayer

layer = IntentLayer()

# Request 1: "I love coding" (Score: ~0.6)
payload1 = {"prompt": "I love coding", "session_id": "user123"}
result1 = layer.handle(payload1, next_callable=lambda x: x)
print(result1)
# Result: Safe

# Request 2: "I hate you, kill process" (Score: ~ -0.7)
# Shift: |(-0.7) - (0.6)| = 1.3  (> 0.5)
payload2 = {"prompt": "I hate you", "session_id": "user123"}
result2 = layer.handle(payload2, next_callable=lambda x: x)
print(result2)
# Result: Blocked ("Drastic intent shift detected")