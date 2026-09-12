"""
RapidDoc Paraphrase Augmenter (optional diversity pass)
Uses the Groq free-tier LLM API to paraphrase sampled intent prompts into
more natural, varied phrasings - then marks every output as UNREVIEWED.

IMPORTANT:
  - You MUST manually review the output before merging into train.jsonl.
    Delete rows where meaning drifted or quoted values changed.
  - This uses an API only as a one-time DATA-GENERATION tool, not in the
    deployed product. State that clearly in your report.
  - Requires a free Groq API key and the groq package:
        pip install groq

Run:  python paraphrase_augment.py
"""

import json
import random
import time

from groq import Groq

API_KEY = "YOUR_GROQ_API_KEY_HERE"
INPUT_PATH = "final/train.jsonl"
OUTPUT_PATH = "final/train_augmented_UNREVIEWED.jsonl"
SAMPLE_SIZE = 800
VARIATIONS_PER_PROMPT = 3
MODEL = "llama-3.1-8b-instant"
TEMPERATURE = 0.8


def load_records(path):
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main():
    if API_KEY == "YOUR_GROQ_API_KEY_HERE":
        raise SystemExit("Set your Groq API key in API_KEY first!")

    client = Groq(api_key=API_KEY)
    records = load_records(INPUT_PATH)
    print(f"Loaded {len(records)} train records.")

    # Sample across all intents
    random.seed(42)
    by_intent = {}
    for r in records:
        by_intent.setdefault(r["intent"], []).append(r)
    sampled = []
    for intent, rs in by_intent.items():
        n = max(1, SAMPLE_SIZE // len(by_intent))
        sampled.extend(random.sample(rs, min(n, len(rs))))
    print(f"Sampled {len(sampled)} prompts for paraphrasing.")

    prompt_template = (
        "Rewrite the following document-editing command in {n} different "
        "natural ways a real user might type it. Return ONLY the rewrites, "
        "one per line, numbered. Do not change the meaning, and keep any "
        "quoted text, page numbers, and values exactly the same.\n\n"
        "Original: {prompt}"
    )

    new_records = []
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for i, r in enumerate(sampled):
            try:
                resp = client.chat.completions.create(
                    model=MODEL,
                    temperature=TEMPERATURE,
                    messages=[{
                        "role": "user",
                        "content": prompt_template.format(
                            n=VARIATIONS_PER_PROMPT, prompt=r["prompt"]),
                    }],
                )
                text = resp.choices[0].message.content.strip()
                for j, line in enumerate(text.splitlines()):
                    line = line.strip()
                    if not line:
                        continue
                    # strip leading "1. " numbering
                    if line[0].isdigit() and ". " in line[:4]:
                        line = line.split(". ", 1)[1]
                    if len(line) < 5 or len(line) > 200:
                        continue
                    new = dict(r)
                    new["id"] = f"{r['id']}_paraphrase{j:02d}"
                    new["prompt"] = line
                    new["source"] = "llm_paraphrase_unreviewed"
                    f.write(json.dumps(new, ensure_ascii=False) + "\n")
                    new_records.append(new)
            except Exception as e:
                print(f"  [{i}] failed: {e}")
            time.sleep(0.4)  # respect rate limits

    print(f"\nWrote {len(new_records)} paraphrased records to {OUTPUT_PATH}")
    print("DO NOT MERGE without manual review! Check at least 100-150 lines "
          "and delete any row where meaning drifted.")


if __name__ == "__main__":
    main()