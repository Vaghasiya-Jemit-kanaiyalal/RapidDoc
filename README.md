# 📄 RapidDoc: Architecture & Module Task Distribution 🚀

> **RapidDoc** is an intelligent, NLP-powered document editor and comprehension platform designed to modify, reformat, summarize, and convert documents through natural language instructions.

---

## 🏗️ 1. High-Level System Architecture

```text
                         ┌────────────────────────┐
                         │  🌐 Client / Frontend  │
                         │ (React / Next.js / UI) │
                         └───────────┬────────────┘
                                     │
                        REST API / Multipart Upload
                                     │
                                     ▼
                         ┌────────────────────────┐
                         │ ⚡ FastAPI Backend Core │
                         │  (Session & Pipeline)  │
                         └───────────┬────────────┘
                                     │
             ┌───────────────────────┴───────────────────────┐
             ▼                                               ▼
  📂 [ Document Ingestion ]                       🧠 [ Natural Language NLU ]
  - PyMuPDF / pdfplumber                          - DistilBERT Intent Classifier
  - python-docx                                   - Rule/Regex Slot Extractor
  - LibreOffice Headless                          - Joint Token BIO Extractor
             │                                               │
             └───────────────────────┬───────────────────────┘
                                     ▼
                       ┌───────────────────────────┐
                       │   🔀 Central Dispatcher & │
                       │     Execution Router      │
                       └─────────────┬─────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        ▼                            ▼                            ▼
┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│ ⚙️ Deterministic     │   │ 🤖 Local Fine-Tuned  │   │ 📊 Pretrained &      │
│    DOCX Engine       │   │    Seq2Seq           │   │    Unsupervised ML   │
├──────────────────────┤   ├──────────────────────┤   ├──────────────────────┤
│ - Headers/Footers    │   │ - Text Rewriting     │   │ - Summarization      │
│ - Find & Replace     │   │   (CoEdIT / T5)      │   │   (BART-CNN)         │
│ - Fonts & Styles     │   │ - MCQ Generation     │   │ - Translation        │
│ - Align / Margins    │   │   (RACE / T5)        │   │   (MarianMT)         │
│ - Page Numbers       │   │ - Flashcards & Viva  │   │ - Keywords           │
│ - Image Replace      │   │   Questions          │   │   (YAKE/KeyBERT)     │
└──────────┬───────────┘   └──────────┬───────────┘   └──────────┬───────────┘
           │                          │                          │
           └──────────────────────────┼──────────────────────────┘
                                      │
                                      ▼
                       ┌───────────────────────────┐
                       │ 📦 Document Reconstruction│
                       │     & Export Pipeline     │
                       │    (DOCX / PDF / TXT)     │
                       └───────────────────────────┘
```

---

## 🧩 2. Module-Wise Task Distribution & Roles

### 📂 Module 1: Document Ingestion & Reconstruction Engine
* **Role**: Parses multi-format input documents into an internal canonical tree structure (`python-docx` Document Object) and handles clean serialization on export.
* **Supported Formats**: `.docx`, `.pdf`, `.txt`, `.pptx`.
* **Key Tasks**:
  * 📄 **DOCX Ingestion**: Direct structured parsing with zero formatting loss using `python-docx`.
  * 📑 **PDF Extraction**: Extracts text runs, font sizing, and visual positions via `PyMuPDF` / `pdfplumber`, reconstructing a structured `.docx` representation.
  * 🩹 **Direct PDF Patching**: Performs lightweight text replacements directly on PDF files via `PyMuPDF` without re-layout.
  * 💾 **Export Pipeline**: Native output for DOCX/TXT; headless LibreOffice integration (`soffice --headless --convert-to pdf`) for high-fidelity PDF rendering.

---

### 🧠 Module 2: NLU & Intent Classification Router
* **Role**: Maps free-form natural language instructions to an unambiguous structured execution payload.
* **Components**:
  * 🎯 **Intent Classifier**: Fine-tuned `distilbert-base-uncased` sequence classifier handling 22 distinct intent classes (e.g., `change_header`, `replace_text`, `summarize_page`, `generate_mcq`).
  * 🔍 **Slot Extractor**: Deterministic entity parser extracting parameters (`page`, `target_text`, `old_text`, `new_text`, `font_name`, `color`, `alignment`).
* **Standard JSON Output Schema**:
```json
  {
    "intent": "replace_text",
    "confidence": 0.99,
    "slots": {
      "old_text": "Draft v2",
      "new_text": "Final Submission",
      "page": null
    }
  }

```

---

### ⚙️ Module 3: Deterministic Document Execution Engine

* **Role**: Manipulates document XML and object trees directly to guarantee deterministic results and avoid hallucinations.


* **Key Tasks**:
* 🏷️ **Header & Footer Management**: Updates target section headers/footers with isolated linkage.


* 🔄 **Cross-Run Text Replacement**: Coalesces adjacent text runs so find-and-replace operates accurately even across fragmented XML boundaries.


* 🎨 **Font & Style Mutation**: Modifies font families, point sizes, colors, and styling (`bold`, `italic`, `underline`).


* 📐 **Layout Alignment**: Configures paragraph alignment (`left`, `center`, `right`, `justify`), background highlighting, and dynamic XML page numbering fields.


* 🖼️ **Image & Logo Replacement**: Updates inline drawings and blip fill image relationships in the package archive.





---

### 🤖 Module 4: Local Neural Generation Engine (Seq2Seq Tasks)

* **Role**: Handles natural language transformation and educational content generation using locally hosted transformer models.


* **Key Tasks**:
* ✍️ **Targeted Text Rewriter**: Fine-tuned `T5-small` / `Flan-T5` on the `grammarly/coedit` dataset for instruction-guided grammar fixing, tone shifts, and simplification.


* 🎓 **Assessment Generator**: Fine-tuned `T5-small` / `BART-base` on the `ehovy/race` dataset to output structured MCQs with distractors, flashcards, and viva examination questions.





---

### 📊 Module 5: Pretrained & Unsupervised Document Analytics Engine

* **Role**: Provides fast, offline document summarization, keyword extraction, and translation without per-token API overhead.


* **Key Tasks**:
* 📝 **Abstractive Summarizer**: Self-hosted `facebook/bart-large-cnn` for multi-paragraph or section-level document summarization.


* 🔑 **Keyword Extraction**: Statistical, hallucination-free keyphrase extraction using `YAKE` / `KeyBERT`.


* 🌐 **Offline Translation**: Local neural machine translation using self-hosted `Helsinki-NLP/opus-mt-*` models.





---

### ⚡ Module 6: Backend Orchestration & Session Store (FastAPI)

* **Role**: Handles asynchronous request dispatching, session document persistence across multi-turn prompts, and file streaming.


* **Core API Endpoints**:
* `POST /api/v1/document/upload` ➔ Upload document, initialize in-memory state, return `doc_id`.


* `POST /api/v1/document/command` ➔ Receive `{doc_id, prompt}`, run NLU, dispatch execution handler, stack changes, return status.


* `GET /api/v1/document/preview/{doc_id}` ➔ Return real-time rendered HTML/PDF preview.


* `GET /api/v1/document/export/{doc_id}?format=...` ➔ Export document in requested format (`.docx`, `.pdf`, `.txt`).





---

## 📊 3. Implementation Matrix: ML Models vs. Deterministic Handlers

| Feature / Task | Implementation Strategy | Model / Framework | Dataset / Pipeline |
| --- | --- | --- | --- |
| **Intent Recognition** | Sequence Classification | `distilbert-base-uncased` | RapidDoc Intent Dataset (7,100 records)
| **Slot Extraction** | Deterministic / BIO Head | Custom Parser / BERT | Heuristic Rules ➔ Joint Token Head
| **Header / Footer Edit** | Deterministic DOM | `python-docx` | None (Rule-Based DOM)
| **Find & Replace / Delete** | Deterministic DOM | `python-docx` (Cross-Run) | None (Rule-Based DOM)
| **Font & Style Mutation** | Deterministic DOM | `python-docx` | None (Rule-Based DOM)
| **Page Number Insertion** | Deterministic XML | `python-docx` OXML | None (Rule-Based XML)
| **Instructional Rewriting** | Fine-Tuned Seq2Seq | `T5-small` / `Flan-T5` | `grammarly/coedit` (69k records)
| **MCQ & Assessment Gen** | Fine-Tuned Seq2Seq | `T5-small` / `BART-base` | `ehovy/race` (20k records)
| **Document Summarization** | Pretrained Seq2Seq | `facebook/bart-large-cnn` | Zero-Shot Evaluation on `cnn_dailymail`<br> |
| **Keyword Extraction** | Statistical NLP | `YAKE` / `KeyBERT` | Unsupervised Extraction
| **Language Translation** | Pretrained Seq2Seq | `Helsinki-NLP/opus-mt` | Self-Hosted Open Weights

---

## 📅 4. 12-Week Implementation Roadmap

```
Week  1: 🎯 Scope Definition, Taxonomy Locking & Architecture Design
Week  2: 📝 Intent Dataset Generation, Validation & Class Balancing
Week  3: 🧠 Intent Classifier Training (DistilBERT) & Slot Extractor Engine
Week  4: ⚙️ Core Deterministic DOCX Execution Engine (Formatting, Headers, Text)
Week  5: 🔍 Advanced Document Manipulation (Multi-Run Replacement & Images)
Week  6: 📥 Task Dataset Ingestion (RACE, CoEdIT, CNN/DailyMail) & Baseline Pipeline
Week  7: 🤖 Fine-Tuning Seq2Seq Models (MCQ & Text Editing)
Week  8: 📊 Summarization, Keyword Extraction & Translation Integration
Week  9: 🔄 Document Conversion Subsystem (PDF/TXT Ingestion & LibreOffice Export)
Week 10: ⚡ FastAPI Backend Development & Session State Manager
Week 11: 🌐 Next.js/React Frontend Integration & Real-Time Document Preview Pane
Week 12: 🚀 End-to-End Stress Testing, Evaluation Benchmarking & Final Deployment

```

### 🗓️ Phase-Wise Breakdown

* **Phase 1: NLU Foundations & Dataset Engineering (Weeks 1–3)**
* Finalize 22-intent classification taxonomy and explicit slot schemas.


* Generate, validate, and balance the 7,100 JSONL records across 80/10/10 train/val/test splits.


* Fine-tune DistilBERT; evaluate accuracy on held-out test splits.




* **Phase 2: Deterministic Document Engine (Weeks 4–5)**
* Implement header, footer, style, font, size, and margin executors.


* Implement cross-run text replacement algorithm to search and update fragmented XML strings.


* Add image/logo injection and dynamic XML page numbering fields.




* **Phase 3: Task Model Fine-Tuning & NLP Engine (Weeks 6–8)**
* Download and preprocess `CoEdIT` and `RACE` datasets.


* Fine-tune `T5-small` for instruction-guided text rewriting and MCQ generation.


* Integrate `BART-large-cnn` summarization and `YAKE` unsupervised keyword extraction pipelines.




* **Phase 4: Pipeline Ingestion, Backend & UI (Weeks 9–11)**
* Implement `PyMuPDF` PDF parsing and headless LibreOffice conversion pipelines.


* Build asynchronous FastAPI endpoints with session persistence for sequential edit stacking.


* Connect Next.js/React frontend with file dropzones, prompt inputs, and side-by-side live previews.




* **Phase 5: Evaluation, Dockerization & Release (Week 12)**
* Measure end-to-end latency, exact-match slot accuracy, ROUGE summarization scores, and formatting preservation.
* Containerize the unified backend and model-serving runtime with Docker.


* Finalize repository documentation and user release guides.



```
