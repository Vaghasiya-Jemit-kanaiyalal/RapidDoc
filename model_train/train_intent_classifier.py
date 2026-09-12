"""
RapidDoc Intent Classifier
Fine-tunes DistilBERT (distilbert-base-uncased) on the generated intent
dataset (final/train.jsonl) to classify a natural-language document command
into one of 24 intents.

Expected result: near-100% accuracy on the held-out test set, since the
dataset is clean and well-separated by construction.

IMPORTANT: run this from a Colab notebook / terminal with the packages below
installed. Do NOT embed !pip commands in this file - install first:
    pip install transformers datasets scikit-learn accelerate torch
"""

import json
import os
import time

import numpy as np
import torch
from datasets import Dataset, load_dataset
from sklearn.metrics import accuracy_score, classification_report
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
)

# Config
TRAIN_PATH = "final/train.jsonl"
VAL_PATH = "final/val.jsonl"
TEST_PATH = "final/test.jsonl"
OUTPUT_DIR = "rapiddoc_intent_model"
BASE_MODEL = "distilbert-base-uncased"
MAX_LENGTH = 48
EPOCHS = 4
BATCH_SIZE = 32
LEARNING_RATE = 3e-5


def load_records(path):
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main():
    print("\n=== Training rapiddoc intent classifier ===")
    for p in (TRAIN_PATH, VAL_PATH, TEST_PATH):
        if not os.path.exists(p):
            raise FileNotFoundError(f"Dataset file not found at: {p}")

    train_records = load_records(TRAIN_PATH)
    val_records = load_records(VAL_PATH)
    test_records = load_records(TEST_PATH)
    print(f"Loaded {len(train_records)} train / {len(val_records)} val / "
          f"{len(test_records)} test records.")

    # Build label vocabulary from the train split
    labels = sorted({r["intent"] for r in train_records})
    label2id = {lab: i for i, lab in enumerate(labels)}
    id2label = {i: lab for lab, i in label2id.items()}
    print(f"Intent classes ({len(labels)}): {labels}")

    def to_dataset(records):
        return Dataset.from_list([
            {"text": r["prompt"], "labels": label2id[r["intent"]]}
            for r in records
        ])

    train_ds = to_dataset(train_records)
    val_ds = to_dataset(val_records)
    test_ds = to_dataset(test_records)

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(
        BASE_MODEL,
        num_labels=len(labels),
        id2label=id2label,
        label2id=label2id,
    )

    def tokenize(batch):
        return tokenizer(batch["text"], truncation=True, padding=True,
                         max_length=MAX_LENGTH)

    train_ds = train_ds.map(tokenize, batched=True)
    val_ds = val_ds.map(tokenize, batched=True)
    test_ds = test_ds.map(tokenize, batched=True)
    # Keep tokenizer columns (input_ids, attention_mask), drop raw text
    train_ds = train_ds.remove_columns(["text"])
    val_ds = val_ds.remove_columns(["text"])
    test_ds = test_ds.remove_columns(["text"])

    training_args = TrainingArguments(
        output_dir="./checkpoints_intent",
        eval_strategy="epoch",
        save_strategy="epoch",
        learning_rate=LEARNING_RATE,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        weight_decay=0.01,
        num_train_epochs=EPOCHS,
        fp16=torch.cuda.is_available(),
        logging_steps=100,
        save_total_limit=1,
        load_best_model_at_end=True,
        metric_for_best_model="accuracy",
        report_to="none",
    )

    def compute_metrics(eval_pred):
        logits, y_true = eval_pred
        y_pred = np.argmax(logits, axis=-1)
        return {"accuracy": accuracy_score(y_true, y_pred)}

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        processing_class=tokenizer,
        data_collator=DataCollatorWithPadding(tokenizer),
        compute_metrics=compute_metrics,
    )

    print("Starting training...")
    t0 = time.time()
    trainer.train()
    print(f"Training done in {(time.time() - t0) / 60:.1f} min.")

    # Evaluate on the held-out test set
    preds = trainer.predict(test_ds)
    y_true = preds.label_ids
    y_pred = np.argmax(preds.predictions, axis=-1)

    acc = accuracy_score(y_true, y_pred)
    print(f"\nTest Accuracy: {acc * 100:.2f}%")
    print("\nClassification Report:")
    print(classification_report(
        y_true, y_pred, target_names=[id2label[i] for i in range(len(labels))],
        zero_division=0,
    ))

    # Save
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    with open(os.path.join(OUTPUT_DIR, "intent_labels.json"), "w") as f:
        json.dump(labels, f, indent=2)
    print(f"\nModel saved to '{OUTPUT_DIR}/' (labels in intent_labels.json)\n")


if __name__ == "__main__":
    main()