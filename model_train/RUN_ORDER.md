# RapidDoc Model Training Bundle — Run Order

Everything needed to build the intent model, summarizer, and task datasets for the
AI features. Run the scripts in the order below.

## Files
| File | Purpose | Needs GPU? | This week? |
|------|---------|-----------|------------|
| `generate_dataset.py` | Generates the intent dataset (final/*.jsonl) | No | Yes |
| `train_intent_classifier.py` | Fine-tunes DistilBERT on the intent dataset | Yes | Yes (main model) |
| `slot_extractor.py` | Rule-based slot extraction (page/text/font/...) | No | Yes |
| `generate_summarization_dataset.py` | Generates multi-section document summarization dataset | No | Yes |
| `train_summarizer.py` | Fine-tunes Seq2Seq complete-document summarizer | Yes | Yes |
| `evaluate_summarizer.py` | Evaluates ROUGE-1/2/L & late-section retention | No | Yes |
| `prepare_task_datasets.py` | Downloads RACE/KP20k/CoEdIT/CNN-DailyMail | No | Later |
| `paraphrase_augment.py` | Optional LLM paraphrasing pass | No | Optional polish |

## Data
- `final/` — the generated intent dataset (train/val/test + charts)
  - train: 6,720 | val: 840 | test: 840 (24 intents, 280 each)
- `task_datasets/` — summarization datasets (train/val/test) & external task sets

## Run order
```bash
# 1. Generate the intent dataset
python generate_dataset.py

# 2. Generate the complete-document summarization dataset
python generate_summarization_dataset.py

# 3. Train the intent classifier (T4 GPU, ~10 min)
python train_intent_classifier.py

# 4. Train the complete-document summarizer (T4 GPU or CPU, ~15 min)
python train_summarizer.py

# 5. Evaluate the summarization system (ROUGE & late-section retention)
python evaluate_summarizer.py

# 6. Optional: Download the 4 external task datasets (5-10 min, needs internet)
pip install datasets requests
python prepare_task_datasets.py

# 7. Optional diversity pass (needs your own free Groq API key)
pip install groq
python paraphrase_augment.py
```

## Install first (once)
```bash
pip install transformers datasets scikit-learn accelerate torch requests
```

## Results to expect
- Intent classifier: near-100% accuracy on the held-out test set.
- Summarization system: >50% ROUGE-1 F1, >95% factual grounding, >90% late-section retention on multi-page documents.
- Slot extractor: ~95% exact slot-match accuracy on the generated dataset.