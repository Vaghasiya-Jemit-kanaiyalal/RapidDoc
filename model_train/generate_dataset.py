"""
RapidDoc Intent Dataset Generator
Generates ~8,400 schema-validated records across 24 intents (280 each),
split 80/10/10 into final/train.jsonl, final/val.jsonl, final/test.jsonl.

Key design point (phantom-slot fix): a slot value is only written into the
ground-truth "slots" dict when the generated prompt text actually mentions it.
Templates that do not reference an optional slot leave it out entirely.

Phrasing diversity: every template is wrapped by politeness PREFIXES and
generic FRAMES, producing many natural phrasings per base template.
"""

import itertools
import json
import random
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split

random.seed(42)

OUT_DIR = Path("final")
OUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Shared value pools
# ---------------------------------------------------------------------------
PAGES = list(range(1, 21))
FONTS = [
    "Arial", "Times New Roman", "Calibri", "Verdana", "Georgia",
    "Helvetica", "Cambria", "Tahoma", "Garamond", "Consolas",
]
FONT_SIZES = ["10", "11", "12", "14", "16", "18", "20", "24", "28", "36"]
HEADER_TEXTS = [
    "Quarterly Report", "Annual Summary", "Project Proposal", "Meeting Minutes",
    "Sales Report", "Budget Report", "Research Paper", "Company Confidential",
    "Final Draft", "Internal Memo", "Marketing Plan", "Technical Document",
    "Student Handbook", "Financial Statement", "Performance Review",
]
FOOTER_TEXTS = [
    "Page", "Confidential", "Draft v1", "Company Name", "All rights reserved",
    "Internal use only", "Q3 2025", "Project Team", "Do not distribute", "Approved",
]
LOGO_NAMES = [
    "company_logo.png", "logo.jpg", "header_logo.png", "brand_logo.png",
    "footer_logo.png", "cover_logo.png", "team_logo.png", "signature.png",
]
NEW_LOGOS = [
    "new_logo.png", "updated_brand.png", "v2_logo.jpg", "rebranded.png",
    "fresh_logo.png", "2025_logo.png",
]
IMAGE_NAMES = [
    "chart.png", "graph.jpg", "diagram.png", "photo.jpg", "table.png",
    "banner.png", "figure1.jpg", "cover_image.png",
]
REPLACE_OLD = [
    "old brand name", "previous title", "Version 1", "first revision",
    "outdated term", "former heading", "2024 edition", "superseded note",
    "beta build", "draft copy",
]
REPLACE_NEW = [
    "new brand name", "current title", "Version 2", "second revision",
    "updated term", "revised heading", "2025 edition", "approved note",
    "release build", "clean copy",
]
SECTIONS = [
    "Introduction", "Conclusion", "Executive Summary", "Background", "Literature Review",
    "Methodology", "Results", "Discussion", "References", "Abstract",
]
LANGUAGES = [
    "French", "Spanish", "German", "Hindi", "Japanese", "Chinese",
    "Italian", "Portuguese", "Russian", "Korean",
]
POSITIONS = ["top", "bottom", "left", "right", "center"]
PARAGRAPHS = [
    "the first paragraph", "the last paragraph", "the second paragraph",
    "the third paragraph", "paragraph 2", "paragraph 3", "the opening paragraph",
    "the closing paragraph", "paragraph 5", "the abstract paragraph",
]
DOC_TYPES = ["docx", "docx", "docx", "docx", "docx", "docx", "pdf", "pdf", "txt"]

# Politeness prefixes multiply phrasing diversity across every intent
PREFIXES = [
    "", "", "", "",
    "please ", "please ", "can you ", "could you ",
    "kindly ", "would you please ", "I need you to ", "hey, ",
]

# Generic wrapper frames applied on top of every base template. Combined with
# PREFIXES this multiplies each intent's diversity enough to hit 300+ unique
# prompts even for intents with few core phrasings.
FRAMES = [
    "{instruction}",
    "I would like you to {instruction}",
    "Could you {instruction}",
    "Can you {instruction}",
    "I need you to {instruction}",
    "Help me {instruction}",
    "Do this for me: {instruction}",
    "Please take care of this: {instruction}",
    "Handle this - {instruction}",
    "Your task is to {instruction}",
]


def _slots(**kw):
    return {k: v for k, v in kw.items() if v is not None}


def build_intents():
    """Return {intent: [(prompt, slots), ...]} with real values substituted."""
    intents = {}

    # -- change_header -----------------------------------------------------
    tpls = []
    for header in HEADER_TEXTS:
        for page in PAGES:
            tpls.append((f"change the header on page {page} to say {header}",
                         _slots(page=page, target_text=header)))
        tpls.append((f"change the header to say {header}", _slots(target_text=header)))
        tpls.append((f"update the header with {header}", _slots(target_text=header)))
        tpls.append((f"make the header say {header} instead", _slots(target_text=header)))
    intents["change_header"] = tpls

    # -- change_footer -----------------------------------------------------
    tpls = []
    for footer in FOOTER_TEXTS:
        for page in PAGES[:12]:
            tpls.append((f"change the footer on page {page} to say {footer}",
                         _slots(page=page, target_text=footer)))
        tpls.append((f"change the footer to say {footer}", _slots(target_text=footer)))
        tpls.append((f"set the footer to {footer}", _slots(target_text=footer)))
        tpls.append((f"update the footer text to {footer}", _slots(target_text=footer)))
    intents["change_footer"] = tpls

    # -- change_title ------------------------------------------------------
    tpls = []
    for header in HEADER_TEXTS:
        tpls.append((f"change the title to {header}", _slots(target_text=header)))
        tpls.append((f"set the title as {header}", _slots(target_text=header)))
        tpls.append((f"rename the document title to {header}", _slots(target_text=header)))
        tpls.append((f"update the title to say {header}", _slots(target_text=header)))
    intents["change_title"] = tpls

    # -- change_font -------------------------------------------------------
    tpls = []
    for font in FONTS:
        for page in PAGES[:10]:
            tpls.append((f"change the font on page {page} to {font}",
                         _slots(page=page, font_name=font)))
        tpls.append((f"change the font to {font}", _slots(font_name=font)))
        tpls.append((f"set the whole document font to {font}", _slots(font_name=font)))
        tpls.append((f"use {font} font", _slots(font_name=font)))
    intents["change_font"] = tpls

    # -- change_font_size --------------------------------------------------
    tpls = []
    for size in FONT_SIZES:
        for font in FONTS[:5]:
            tpls.append((f"change the font size to {size} pt with font {font}",
                         _slots(font_size=size, font_name=font)))
        tpls.append((f"change the font size to {size} pt", _slots(font_size=size)))
        tpls.append((f"make the text {size} point", _slots(font_size=size)))
        tpls.append((f"set font size to {size}", _slots(font_size=size)))
    intents["change_font_size"] = tpls

    # -- replace_text ------------------------------------------------------
    tpls = []
    for old, new in zip(REPLACE_OLD, REPLACE_NEW):
        for page in PAGES[:8]:
            tpls.append((f"replace {old} with {new} on page {page}",
                         _slots(page=page, old_text=old, new_text=new)))
        tpls.append((f"replace {old} with {new}", _slots(old_text=old, new_text=new)))
        tpls.append((f"find {old} and replace it with {new}",
                     _slots(old_text=old, new_text=new)))
        tpls.append((f"swap {old} to {new}", _slots(old_text=old, new_text=new)))
    intents["replace_text"] = tpls

    # -- insert_text -------------------------------------------------------
    tpls = []
    for section in SECTIONS[:8]:
        for pos in POSITIONS[:3]:
            tpls.append((f"insert the text New Paragraph at the {pos} of {section}",
                         _slots(position=pos, section=section, text="New Paragraph")))
        tpls.append((f"insert New Paragraph into {section}",
                     _slots(section=section, text="New Paragraph")))
    for p in PARAGRAPHS[:6]:
        tpls.append((f"add the text New Paragraph after {p}",
                     _slots(position="after", text="New Paragraph")))
    intents["insert_text"] = tpls

    # -- delete_paragraph --------------------------------------------------
    tpls = []
    for p in PARAGRAPHS:
        tpls.append((f"delete {p}", {}))
        tpls.append((f"remove {p}", {}))
        tpls.append((f"delete {p} from the document", {}))
    for page in PAGES[:8]:
        tpls.append((f"delete paragraph on page {page}", _slots(page=page)))
    intents["delete_paragraph"] = tpls

    # -- insert_image ------------------------------------------------------
    tpls = []
    for img in IMAGE_NAMES:
        for pos in POSITIONS[:3]:
            tpls.append((f"insert the image {img} at the {pos} of the page",
                         _slots(position=pos, image_name=img)))
        tpls.append((f"insert image {img}", _slots(image_name=img)))
        tpls.append((f"add the picture {img} to the document", _slots(image_name=img)))
    intents["insert_image"] = tpls

    # -- remove_image ------------------------------------------------------
    tpls = []
    for img in IMAGE_NAMES:
        tpls.append((f"remove the image {img}", _slots(image_name=img)))
        tpls.append((f"delete the picture {img}", _slots(image_name=img)))
        tpls.append((f"remove {img} from the document", _slots(image_name=img)))
    for page in PAGES[:8]:
        tpls.append((f"remove all images on page {page}", _slots(page=page)))
    intents["remove_image"] = tpls

    # -- replace_logo ------------------------------------------------------
    tpls = []
    for old in LOGO_NAMES:
        for new in NEW_LOGOS:
            tpls.append((f"replace the logo {old} with {new}",
                         _slots(logo_name=old, new_logo=new)))
        tpls.append((f"change the logo to {NEW_LOGOS[0]}", _slots(new_logo=NEW_LOGOS[0])))
    intents["replace_logo"] = tpls

    # -- insert_page_number ------------------------------------------------
    tpls = []
    for pos in POSITIONS:
        tpls.append((f"insert page numbers at the {pos} of each page", _slots(position=pos)))
        tpls.append((f"add page number at {pos}", _slots(position=pos)))
        tpls.append((f"put page numbers in the {pos} corner", _slots(position=pos)))
    intents["insert_page_number"] = tpls

    # -- remove_page_number ------------------------------------------------
    tpls = []
    for _ in range(18):
        tpls.append(("remove the page numbers", {}))
    for _ in range(14):
        tpls.append(("delete the page numbers from the document", {}))
    for _ in range(12):
        tpls.append(("take out the page numbers", {}))
    for _ in range(10):
        tpls.append(("remove all page numbers", {}))
    for _ in range(10):
        tpls.append(("hide the page numbers", {}))
    for _ in range(10):
        tpls.append(("delete the page numbering", {}))
    for _ in range(8):
        tpls.append(("remove page numbering", {}))
    for _ in range(8):
        tpls.append(("get rid of the page numbers", {}))
    for _ in range(6):
        tpls.append(("turn off page numbers", {}))
    for _ in range(6):
        tpls.append(("remove the page numbers from every page", {}))
    for _ in range(6):
        tpls.append(("delete page numbers throughout", {}))
    intents["remove_page_number"] = tpls

    # -- summarize_page ----------------------------------------------------
    tpls = []
    for page in PAGES:
        tpls.append((f"summarize page {page}", _slots(page=page)))
    for length in ["short", "brief", "detailed"]:
        tpls.append((f"give a {length} summary of page 2", _slots(length=length, page=2)))
    intents["summarize_page"] = tpls

    # -- summarize_document ------------------------------------------------
    tpls = []
    for length in ["short", "brief", "detailed", "one sentence"]:
        tpls.append((f"summarize the whole document {length}", _slots(length=length)))
    for _ in range(8):
        tpls.append(("summarize the document", {}))
    for _ in range(8):
        tpls.append(("give me a summary of the entire document", {}))
    intents["summarize_document"] = tpls

    # -- generate_mcq ------------------------------------------------------
    tpls = []
    for count in ["5", "10", "15", "20"]:
        tpls.append((f"generate {count} MCQs from the document", _slots(count=count)))
        tpls.append((f"create {count} multiple choice questions", _slots(count=count)))
        tpls.append((f"make {count} MCQs", _slots(count=count)))
    for _ in range(8):
        tpls.append(("generate MCQ questions from the text", {}))
    intents["generate_mcq"] = tpls

    # -- generate_flashcards ----------------------------------------------
    tpls = []
    for count in ["10", "20", "30", "50"]:
        tpls.append((f"generate {count} flashcards", _slots(count=count)))
        tpls.append((f"create {count} flashcards from the document", _slots(count=count)))
    for _ in range(8):
        tpls.append(("make flashcards from this content", {}))
    intents["generate_flashcards"] = tpls

    # -- extract_keywords --------------------------------------------------
    tpls = []
    for count in ["5", "10", "15"]:
        tpls.append((f"extract {count} keywords", _slots(count=count)))
    for _ in range(10):
        tpls.append(("extract keywords from the document", {}))
    for _ in range(8):
        tpls.append(("find the important keywords in this text", {}))
    intents["extract_keywords"] = tpls

    # -- translate_section -------------------------------------------------
    tpls = []
    for lang in LANGUAGES:
        tpls.append((f"translate the document to {lang}", _slots(language=lang)))
        tpls.append((f"translate this document into {lang}", _slots(language=lang)))
        tpls.append((f"translate the whole document to {lang}", _slots(language=lang)))
    for section in SECTIONS[:5]:
        tpls.append((f"translate {section} to French",
                     _slots(section=section, language="French")))
    intents["translate_section"] = tpls

    # -- check_grammar -----------------------------------------------------
    tpls = []
    for _ in range(16):
        tpls.append(("check the grammar of the document", {}))
    for _ in range(14):
        tpls.append(("fix the grammar in this document", {}))
    for _ in range(12):
        tpls.append(("correct grammar mistakes", {}))
    for _ in range(10):
        tpls.append(("proofread the document for grammar", {}))
    for _ in range(10):
        tpls.append(("fix the grammatical errors", {}))
    for _ in range(10):
        tpls.append(("check for spelling and grammar", {}))
    for _ in range(8):
        tpls.append(("correct all the grammar", {}))
    for _ in range(8):
        tpls.append(("improve the grammar", {}))
    for _ in range(8):
        tpls.append(("fix grammar issues in the text", {}))
    for _ in range(6):
        tpls.append(("review the grammar", {}))
    for _ in range(6):
        tpls.append(("fix the English grammar mistakes", {}))
    for _ in range(6):
        tpls.append(("correct the grammar of this document", {}))
    intents["check_grammar"] = tpls

    # -- change_language ---------------------------------------------------
    tpls = []
    for lang in LANGUAGES:
        tpls.append((f"set the document language to {lang}", _slots(language=lang)))
        tpls.append((f"change the language to {lang}", _slots(language=lang)))
    intents["change_language"] = tpls

    # -- justify_text ------------------------------------------------------
    tpls = []
    for _ in range(18):
        tpls.append(("justify the text", {}))
    for _ in range(14):
        tpls.append(("make the text justified", {}))
    for _ in range(12):
        tpls.append(("justify the paragraphs", {}))
    for _ in range(10):
        tpls.append(("justify all the text", {}))
    for _ in range(10):
        tpls.append(("align the text justified", {}))
    for _ in range(10):
        tpls.append(("make the document justified", {}))
    for _ in range(8):
        tpls.append(("justify the alignment", {}))
    for _ in range(8):
        tpls.append(("justify the whole text", {}))
    for _ in range(6):
        tpls.append(("make the text fully justified", {}))
    for _ in range(6):
        tpls.append(("justify the document text", {}))
    for _ in range(6):
        tpls.append(("apply justified alignment", {}))
    intents["justify_text"] = tpls

    # -- add_bullets -------------------------------------------------------
    tpls = []
    for section in SECTIONS[:5]:
        tpls.append((f"convert {section} to bullet points", _slots(section=section)))
    for _ in range(10):
        tpls.append(("convert the text into bullet points", {}))
    for _ in range(8):
        tpls.append(("make this a bullet list", {}))
    intents["add_bullets"] = tpls

    # -- generate_viva_questions ------------------------------------------
    tpls = []
    for count in ["5", "10", "15"]:
        tpls.append((f"generate {count} viva questions", _slots(count=count)))
        tpls.append((f"create {count} viva voce questions", _slots(count=count)))
    for _ in range(8):
        tpls.append(("make viva questions from the document", {}))
    intents["generate_viva_questions"] = tpls

    return intents


def generate_all_records():
    intents = build_intents()
    records = []
    rid = 0
    for intent, templates in intents.items():
        seen = set()
        # cartesian product of templates x prefixes x wrapper frames
        for (tmpl, slots), prefix, frame in itertools.product(templates, PREFIXES, FRAMES):
            prompt = (prefix + frame).format(instruction=tmpl)
            key = (prompt, json.dumps(slots, sort_keys=True))
            if key in seen:
                continue
            seen.add(key)
            records.append({
                "id": f"{intent}_{rid:05d}",
                "prompt": prompt,
                "intent": intent,
                "slots": slots,
                "doc_type": random.choice(DOC_TYPES),
                "source": "template",
            })
            rid += 1

    # Balance: enforce 250-350 per class deterministically
    counter = Counter(r["intent"] for r in records)
    target = min(350, max(250, min(counter.values())))
    balanced = []
    counts = Counter()
    random.shuffle(records)
    for r in records:
        if counts[r["intent"]] < target:
            balanced.append(r)
            counts[r["intent"]] += 1
    return balanced, dict(counter)


def main():
    print("=== Generating RapidDoc intent dataset ===")
    records, raw_counts = generate_all_records()
    print(f"Generated {len(records)} unique, balanced records across "
          f"{len(raw_counts)} intents.")

    # Schema validation
    required = {"id", "prompt", "intent", "slots", "doc_type", "source"}
    problems = 0
    for r in records:
        missing = required - set(r.keys())
        if missing:
            problems += 1
        if not r["prompt"] or not r["intent"]:
            problems += 1
        # Phantom-slot check: every slot value must appear in the prompt
        for k, v in r["slots"].items():
            if str(v) and str(v).lower() not in r["prompt"].lower():
                problems += 1
    if problems:
        raise SystemExit(f"Schema validation failed for {problems} records!")
    print("Schema validation passed (all records have required fields, "
          "no phantom slots).")

    # Stratified 80/10/10 split
    intents = [r["intent"] for r in records]
    tr, temp = train_test_split(records, test_size=0.2, stratify=intents, random_state=42)
    temp_intents = [r["intent"] for r in temp]
    va, te = train_test_split(temp, test_size=0.5, stratify=temp_intents, random_state=42)

    def write(split_records, name):
        path = OUT_DIR / name
        with open(path, "w", encoding="utf-8") as f:
            for r in split_records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  -> {path} : {len(split_records)} records")

    write(tr, "train.jsonl")
    write(va, "val.jsonl")
    write(te, "test.jsonl")

    # Summary + class balance chart
    summary = {"total": len(records), "intents": len(raw_counts),
               "train": len(tr), "val": len(va), "test": len(te)}
    counts = Counter(r["intent"] for r in tr)
    summary["per_intent"] = dict(sorted(counts.items()))

    with open(OUT_DIR / "dataset_summary.txt", "w", encoding="utf-8") as f:
        f.write(f"Total records: {summary['total']}\n")
        f.write(f"Intent classes: {summary['intents']}\n")
        f.write(f"Train: {summary['train']} | Val: {summary['val']} | Test: {summary['test']}\n\n")
        f.write("Per-intent counts (train split):\n")
        for k, v in summary["per_intent"].items():
            f.write(f"  {k}: {v}\n")
    print(f"  -> {OUT_DIR / 'dataset_summary.txt'}")

    # Class balance chart
    names = list(counts.keys())
    values = [counts[n] for n in names]
    plt.figure(figsize=(14, 6))
    plt.bar(names, values)
    plt.xticks(rotation=90)
    plt.ylabel("Examples (train)")
    plt.title("RapidDoc Intent Class Balance (train split)")
    plt.tight_layout()
    plt.savefig(OUT_DIR / "class_balance.png", dpi=120)
    print(f"  -> {OUT_DIR / 'class_balance.png'}")

    print(f"\nDone. Dataset saved to '{OUT_DIR}/'")


if __name__ == "__main__":
    main()