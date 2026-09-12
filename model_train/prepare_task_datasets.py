"""
RapidDoc External Task Dataset Downloader
Pulls the 4 public datasets used for the generation AI features:

  - RACE      (ehovy/race)        -> MCQ generation            (task_datasets/mcq_*.jsonl)
  - KP20k     (midas/kp20k)       -> keyword extraction        (task_datasets/keywords_*.jsonl)
  - CoEdIT    (grammarly/coedit)  -> text editing              (task_datasets/textedit_*.jsonl)
  - CNN/DailyMail (abisee/cnn_dailymail) -> summarization      (task_datasets/summary_*.jsonl)

IMPORTANT: this needs internet access to Hugging Face and a Colab/terminal with:
    pip install datasets

Run:  python prepare_task_datasets.py
"""

import json
from pathlib import Path

import requests

Path("task_datasets").mkdir(exist_ok=True)


def save_jsonl(records, path):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"  -> saved {len(records)} records to {path}")


def prepare_race(train_limit=20000, val_limit=2000, test_limit=2000):
    from datasets import load_dataset, concatenate_datasets, DatasetDict
    print("\n=== RACE (MCQ generation) ===")
    high = load_dataset("ehovy/race", "high")
    middle = load_dataset("ehovy/race", "middle")
    race = DatasetDict({
        split: concatenate_datasets([high[split], middle[split]])
        for split in ["train", "validation", "test"]
    })
    print("First raw row (verify column names):")
    print(race["train"][0])

    def convert(split, limit):
        data = race[split]
        n = min(limit, len(data)) if limit else len(data)
        data = data.select(range(n))
        records = []
        for i, row in enumerate(data):
            records.append({
                "id": f"race_{split}_{i:06d}",
                "context": row["article"],
                "question": row["question"],
                "options": row["options"],
                "answer": row["answer"],
                "task": "mcq_generation",
                "source": "RACE",
            })
        return records

    save_jsonl(convert("train", train_limit), "task_datasets/mcq_train.jsonl")
    save_jsonl(convert("validation", val_limit), "task_datasets/mcq_val.jsonl")
    save_jsonl(convert("test", test_limit), "task_datasets/mcq_test.jsonl")


def prepare_kp20k(train_limit=20000, val_limit=2000, test_limit=2000):
    """KP20k via raw JSONL files.

    The old 'taln-ls2n/kp20k' loading script was deprecated by Hugging Face
    ('Dataset scripts are no longer supported'), and 'midas/kp20k' still ships
    the script too - so we download the raw JSONL directly and build a HF
    Dataset from JSON. Column names: document (token list),
    extractive_keyphrases, abstractive_keyphrases.
    """
    print("\n=== KP20k (keyword extraction) ===")
    base = "https://huggingface.co/datasets/midas/kp20k/resolve/main"
    files = {"train": "train.jsonl", "validation": "valid.jsonl", "test": "test.jsonl"}
    from datasets import load_dataset
    kp = {}
    for split, fn in files.items():
        print(f"  downloading {fn} ...")
        kp[split] = load_dataset(
            "json",
            data_files=f"{base}/{fn}",
            split="train",
        )
        print(f"    -> {len(kp[split])} rows; columns: {kp[split].column_names}")

    def convert(split, limit):
        data = kp[split]
        n = min(limit, len(data)) if limit else len(data)
        data = data.select(range(n))
        records = []
        for i, row in enumerate(data):
            doc_tokens = row.get("document") or []
            text = " ".join(doc_tokens)
            keyphrases = list(row.get("abstractive_keyphrases") or [])
            if not keyphrases:
                keyphrases = list(row.get("extractive_keyphrases") or [])
            records.append({
                "id": f"kp20k_{split}_{i:06d}",
                "text": text,
                "keyphrases": keyphrases,
                "task": "keyword_extraction",
                "source": "KP20k",
            })
        return records

    save_jsonl(convert("train", train_limit), "task_datasets/keywords_train.jsonl")
    save_jsonl(convert("validation", val_limit), "task_datasets/keywords_val.jsonl")
    save_jsonl(convert("test", test_limit), "task_datasets/keywords_test.jsonl")


def prepare_coedit():
    from datasets import load_dataset
    print("\n=== CoEdIT (text editing) ===")
    coedit = load_dataset("grammarly/coedit")
    print("First raw row (verify column names):")
    print(coedit["train"][0])

    def convert(split):
        data = coedit[split]
        records = []
        for i, row in enumerate(data):
            src = row.get("src", "")
            tgt = row.get("tgt", "")
            if not src or not tgt:
                continue
            records.append({
                "id": f"coedit_{split}_{i:06d}",
                "input_text": src,
                "target_text": tgt,
                "task": "text_editing",
                "source": "CoEdIT",
            })
        return records

    save_jsonl(convert("train"), "task_datasets/textedit_train.jsonl")
    save_jsonl(convert("validation"), "task_datasets/textedit_val.jsonl")


def prepare_cnn_dailymail(train_limit=20000, val_limit=2000, test_limit=2000):
    from datasets import load_dataset
    print("\n=== CNN/DailyMail (summarization) ===")
    cnn = load_dataset("abisee/cnn_dailymail", "3.0.0")
    print("First raw row (verify column names):")
    print(cnn["train"][0])

    def convert(split, limit):
        data = cnn[split]
        n = min(limit, len(data)) if limit else len(data)
        data = data.select(range(n))
        records = []
        for i, row in enumerate(data):
            records.append({
                "id": f"cnn_{split}_{i:06d}",
                "document": row["article"],
                "summary": row["highlights"],
                "task": "summarization",
                "source": "CNN/DailyMail",
            })
        return records

    save_jsonl(convert("train", train_limit), "task_datasets/summary_train.jsonl")
    save_jsonl(convert("validation", val_limit), "task_datasets/summary_val.jsonl")
    save_jsonl(convert("test", test_limit), "task_datasets/summary_test.jsonl")


if __name__ == "__main__":
    prepare_race()
    prepare_kp20k()
    prepare_coedit()
    prepare_cnn_dailymail()
    print("\nAll done. Check task_datasets/ folder.")