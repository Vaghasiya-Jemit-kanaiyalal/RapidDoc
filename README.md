# 📄 RapidDoc: AI Document Editor & Architecture 🚀

> **RapidDoc** is an intelligent, NLP-powered document editor and comprehension platform designed to modify, reformat, summarize, and convert documents through natural language instructions. It provides fast PDF and DOCX manipulation, real-time preview, intelligent find & replace functionality, and document management with JWT authentication.

---

## 🚀 Features

- **FastAPI Backend**: Asynchronous RESTful API for document processing, user auth, and file storage.
- **Authentication & Security**: Secure user registration and login using OAuth2 password flow, passlib bcrypt password hashing, and JWT tokens.
- **Document Processing**: PDF text and image editing, DOCX manipulation, and preview conversions.
- **AI Integration**: Powered by Google Gemini API and local NLP models for intelligent document analysis and editing command support.
- **MongoDB Storage**: Metadata management for documents, user accounts, and sessions.
- **Local / Cloud Storage**: Abstracted storage service layer supporting local storage and extensible for cloud providers.

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

## 📁 Project Structure

```text
RapidDoc/
├── backend/
│   ├── app/
│   │   ├── routers/        # Auth, Documents, and Preview routes
│   │   ├── services/       # PDF/DOCX editing, storage, and conversion services
│   │   ├── config.py       # Pydantic settings & env validation
│   │   ├── database.py     # MongoDB motor client connection
│   │   ├── main.py         # FastAPI application entrypoint
│   │   └── models.py       # Pydantic data schemas
│   ├── .env.example        # Environment variable template
│   ├── .gitignore          # Backend git ignore rules
│   └── requirements.txt    # Python dependencies
├── frontend/               # React Vite frontend web UI
├── mongodb_data/           # Local MongoDB data directory (Git ignored)
├── storage/                # Local document uploads directory (Git ignored)
├── run_dev.bat             # One-click Windows development launcher
├── README.md               # Project documentation
└── .gitignore              # Global git ignore configuration
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
| **Intent Recognition** | Sequence Classification | `distilbert-base-uncased` | RapidDoc Intent Dataset (7,100 records) |
| **Slot Extraction** | Deterministic / BIO Head | Custom Parser / BERT | Heuristic Rules ➔ Joint Token Head |
| **Header / Footer Edit** | Deterministic DOM | `python-docx` | None (Rule-Based DOM) |
| **Find & Replace / Delete** | Deterministic DOM | `python-docx` (Cross-Run) | None (Rule-Based DOM) |
| **Font & Style Mutation** | Deterministic DOM | `python-docx` | None (Rule-Based DOM) |
| **Page Number Insertion** | Deterministic XML | `python-docx` OXML | None (Rule-Based XML) |
| **Instructional Rewriting** | Fine-Tuned Seq2Seq | `T5-small` / `Flan-T5` | `grammarly/coedit` (69k records) |
| **MCQ & Assessment Gen** | Fine-Tuned Seq2Seq | `T5-small` / `BART-base` | `ehovy/race` (20k records) |
| **Document Summarization** | Pretrained Seq2Seq | `facebook/bart-large-cnn` | Zero-Shot Evaluation on `cnn_dailymail` |
| **Keyword Extraction** | Statistical NLP | `YAKE` / `KeyBERT` | Unsupervised Extraction |
| **Language Translation** | Pretrained Seq2Seq | `Helsinki-NLP/opus-mt` | Self-Hosted Open Weights |

---

## 📅 4. 12-Week Implementation Roadmap

```text
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

---

## 🛠️ Prerequisites

Make sure you have the following installed on your system:

- **Python 3.10+**
- **Node.js 18+** & `npm`
- **MongoDB Community Server** (running locally on port 27017)

---

## ⚙️ Getting Started

### 1. Environment Setup

Copy the template `.env.example` file in the `backend` folder to `.env`:

```bash
cd backend
cp .env.example .env
```

Open `.env` and set your configuration variables, including `JWT_SECRET_KEY` and your `GEMINI_API_KEY`:

```env
PORT=8000
HOST=0.0.0.0
PROJECT_NAME="RapidDoc API"
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=rapiddoc
JWT_SECRET_KEY=your_generated_jwt_secret_key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
STORAGE_TYPE=local
STORAGE_LOCAL_PATH=storage
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.0-flash
```

> **Tip**: Generate a secure JWT secret in Python using:
> `python -c "import secrets; print(secrets.token_urlsafe(48))"`

---

### 2. Install Dependencies

#### Backend:
```bash
cd backend
pip install -r requirements.txt
```

#### Frontend:
```bash
cd frontend
npm install
```

---

### 3. Running the Application

#### Option A: Windows Launcher (Recommended)
Double click `run_dev.bat` or execute it from PowerShell / CMD:
```cmd
.\run_dev.bat
```

#### Option B: Manual Startup

1. **Start MongoDB**:
   ```bash
   mongod --dbpath "./mongodb_data"
   ```

2. **Start FastAPI Backend**:
   ```bash
   cd backend
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. **Start Frontend Dev Server**:
   ```bash
   cd frontend
   npm run dev
   ```

---

## 🔗 API Documentation

Once the backend is running, access the interactive API docs at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🔒 Security & Contribution

- **Never commit `.env` files** containing sensitive secrets or API keys.
- All temporary upload files (`storage/`) and local MongoDB files (`mongodb_data/`) are automatically excluded by `.gitignore`.
