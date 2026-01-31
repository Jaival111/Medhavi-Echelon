import pandas as pd
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from tqdm import tqdm

# -----------------------------
# CONFIG
# -----------------------------
MODEL_NAME = "TheDeepDas/Medhavi"
INPUT_CSV = "test.csv"
OUTPUT_CSV = "output_with_scores.csv"
TEXT_COLUMN = "text"
BATCH_SIZE = 16
MAX_LENGTH = 512

device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")

# -----------------------------
# LOAD MODEL
# -----------------------------
print("Loading tokenizer and model...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
model.to(device)
model.eval()

id2label = model.config.id2label

# -----------------------------
# LOAD DATA
# -----------------------------
df = pd.read_csv(INPUT_CSV)

labels = []
scores = []

# -----------------------------
# BATCH INFERENCE
# -----------------------------
for i in tqdm(range(0, len(df), BATCH_SIZE)):
    batch_texts = df[TEXT_COLUMN].iloc[i:i+BATCH_SIZE].tolist()

    inputs = tokenizer(
        batch_texts,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=MAX_LENGTH
    )

    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)
        probs = F.softmax(outputs.logits, dim=-1)

        batch_scores, batch_preds = torch.max(probs, dim=-1)

    for score, pred in zip(batch_scores, batch_preds):
        labels.append(id2label[pred.item()])
        scores.append(float(score.item()))

# -----------------------------
# SAVE RESULTS
# -----------------------------
df["label"] = labels
df["score"] = scores

df.to_csv(OUTPUT_CSV, index=False)

print(f"\n✅ Saved results to {OUTPUT_CSV}")
