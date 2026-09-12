# RapidDoc Model Training Bundle — Run Order

Everything needed to build the intent model + the 4 task datasets for the
AI features. Run the scripts in the order below.

## Files
| File | Purpose | Needs GPU? | This week? |
|------|---------|-----------|------------|
| `generate_dataset.py` | Generates the intent dataset (final/*.jsonl) | No | Yes |
| `train_intent_classifier.py` | Fine-tunes DistilBERT on the intent dataset | Yes | Yes (main model) |
| `slot_extractor.py` | Rule-based slot extraction (page/text/font/...) | No | Yes |
| `prepare_task_datasets.py` | Downloads RACE/KP20k/CoEdIT/CNN-DailyMail | No | Later |
| `paraphrase_augment.py` | Optional LLM paraphrasing pass | No | Optional polish |

## Data
- `final/` — the generated intent dataset (train/val/test + charts)
  - train: 6,720 | val: 840 | test: 840 (24 intents, 280 each)
- `task_datasets/` — created by `prepare_task_datasets.py`

## Run order
```bash
# 1. (Optional) regenerate the intent dataset
python generate_dataset.py

# 2. Quick sanity check of the slot extractor (no GPU)
python slot_extractor.py

# 3. Train the intent classifier (T4 GPU, ~10 min)
#    Set Runtime -> Change runtime type -> T4 GPU first in Colab
python train_intent_classifier.py

# 4. Download the 4 external task datasets (5-10 min, needs internet)
pip install datasets requests
python prepare_task_datasets.py

# 5. Optional diversity pass (needs your own free Groq API key)
pip install groq
python paraphrase_augment.py
```

## Install first (once)
```bash
pip install transformers datasets scikit-learn accelerate torch requests groq
```

## Troubleshooting
- `SyntaxError` pointing at a line starting with `!` → that is a Colab-cell-only
  command. It must NOT live inside a .py file. Run it as its own cell instead.
- KP20k `RuntimeError: Dataset scripts are no longer supported` → already
  handled: `prepare_task_datasets.py` loads KP20k from raw JSONL, not the
  deprecated loading script.
- Colab uploads not overwriting → delete the old file first
  (`!rm -f prepare_task_datasets.py`) or use `%%writefile` to write it directly.

## Results to expect
- Intent classifier: near-100% accuracy on the held-out test set (the data is
  clean and well-separated by construction).
- Slot extractor: ~95% exact slot-match accuracy on the generated dataset.
- RACE: 20k/2k/2k MCQ records. KP20k: 20k/2k/2k keyword records.
  CoEdIT: full text-edit set. CNN/DailyMail: 20k/2k/2k summarization records.