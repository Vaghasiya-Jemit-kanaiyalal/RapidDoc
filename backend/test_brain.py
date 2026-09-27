import sys
import os

# Set UTF-8 encoding for stdout on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Insert workspace root to sys.path
sys.path.insert(0, r"c:\Users\umran\Desktop\RapidDoc_SGP")

from RapidDoc.backend.app.services.local_models import (
    brain_status,
    chunk_text_for_mcq,
    classify_intent,
    generate_mcq,
    parse_mcq,
    rewrite_text_locally,
    summarize,
    warm_start_brains,
)
from RapidDoc.backend.app.services.slot_extractor import extract_slots
from RapidDoc.backend.app.services.gemini_service import (
    generate_mcqs,
    summarize_document,
    understand_command,
    rewrite_text,
)

print("==================================================")
print("0. Loading all four brains (this takes ~30s once)")
print("==================================================")
warm_start_brains()
import time
for _ in range(240):
    time.sleep(1)
    if all(b["loaded"] for b in brain_status()["brains"].values()):
        break
print(brain_status())
print()

print("==================================================")
print("1. Testing Brain 1: DistilBERT Intent Classifier")
print("==================================================")
test_prompts = [
    "Change the header to RapidDoc Report",
    "Replace the text Draft with Final",
    "Change the footer to Confidential 2026",
    "Summarize page 2 briefly",
    "Generate 5 MCQs from the document"
]
for p in test_prompts:
    res = classify_intent(p)
    print(f"Prompt: '{p}'\n  -> Output: {res}\n")

print("==================================================")
print("2. Testing Slot Extractor with Predicted Intent")
print("==================================================")
for p in test_prompts:
    intent_res = classify_intent(p)
    intent = intent_res["intent"] if intent_res else "replace_text"
    slots = extract_slots(p, intent)
    print(f"Prompt: '{p}' (Intent: {intent})\n  -> Slots: {slots}\n")

print("==================================================")
print("3. Testing Brain 2: T5-small Text Rewriter")
print("==================================================")
rewrite_inputs = [
    ("Make this more formal", "hey bro whats up we gotta finish this report ASAP"),
    ("Remove all grammatical errors from this text", "she do not knows what he are doing yesterday"),
    ("Simplify this text", "The utilization of multifaceted operational paradigms necessitates comprehensive evaluation.")
]
for instruction, sample_text in rewrite_inputs:
    out = rewrite_text_locally(instruction, sample_text)
    print(f"Instruction: {instruction}")
    print(f"Original:    {sample_text}")
    print(f"Rewritten:   {out}\n")

print("==================================================")
print("4. Testing Brain 3: BART MCQ Generator")
print("==================================================")
passage = (
    "Photosynthesis is the process by which green plants use sunlight to convert carbon "
    "dioxide and water into glucose. Chlorophyll, the green pigment in leaves, absorbs "
    "light energy to drive this reaction. Oxygen is released as a byproduct of this process."
)
print("Single question:")
print(" ", generate_mcq(passage), "\n")
print("Parser edge cases:")
for raw in [
    "question: What is X? options: A) a B) b C) c D) d answer: B",
    "question: What is X? options: A) a B) b",
    "no structure at all",
    "",
]:
    print(f"  {raw[:52]!r:<56} -> {parse_mcq(raw)}")
print("\nChunking a long document:")
doc = ("Background. " + "RapidDoc serves four local transformer models. " * 15
       + "Results. " + "The MCQ brain beat the older baseline on held-out questions. " * 15)
for i, c in enumerate(chunk_text_for_mcq(doc, 3)):
    print(f"  chunk {i}: {len(c)} chars -> {c[:60]!r}...")
print("\nService layer (1 question):")
print(" ", generate_mcqs(passage, 1), "\n")

print("==================================================")
print("5. Testing Brain 4: BART Summarizer")
print("==================================================")
long_doc = (
    "The Federal Reserve held interest rates steady on Wednesday, signaling that it is in "
    "no hurry to adjust borrowing costs as the economy navigates a period of uncertainty "
    "driven by trade tensions and slowing global growth. Fed Chair Jerome Powell said the "
    "central bank is monitoring incoming data and will act as appropriate to sustain the "
    "expansion. Markets are now pricing in at least one rate cut by the end of the year."
)
print("Direct:", summarize(long_doc), "\n")
print("brief :", summarize(long_doc, max_new_tokens=48), "\n")
print("Service layer:")
print(" ", summarize_document(long_doc))
print(" ", summarize_document(long_doc, "brief"), "\n")

print("==================================================")
print("6. Testing Integrated Command Understanding Cascade")
print("==================================================")
commands = [
    "Change the header to RapidDoc SGP Project",
    "Replace 'old text' with 'new text'",
    "Change footer to CHARUSAT University",
    "Summarize this document",
    "Summarize page 2",
    "Generate 5 MCQs from this document",
    "qwerty zxcvbn nonsense",
]
for cmd in commands:
    res = understand_command(cmd)
    print(f"Command: '{cmd}'\n  -> Result: {res}\n")

print("==================================================")
print("7. Testing Integrated rewrite_text() Service")
print("==================================================")
print("Result:", rewrite_text("formal", "hey whats up let's get this done"))

print("\nAll four brain models tested.")
