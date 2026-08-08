# RapidDoc — AI-Powered Document Intelligence & Editing Platform

**RapidDoc** is a full-stack web application that unifies a traditional document editor with an AI-powered document-understanding layer. Upload a **PDF** or **DOCX**, edit content and styling, issue **natural-language commands**, and export the final editable document — all from a single interface. No more switching between Word, Acrobat, translators, and summarizers.

---

## ✨ Key Features

### 👤 Authentication & User Accounts
- **Register** with full-name, email and password — client-side validation with a live **password-strength meter** (Weak / Medium / Strong / Very Strong)
- **Login** with JWT-based session handling (token persisted in `localStorage`)
- **Logout** and protected routes — documents are always scoped to the logged-in user
- Session restore on page refresh via `/api/auth/me`
- Smart view routing: logged-in users land on their Dashboard; guest-only screens (Login/Register) are never shown to authenticated users

### 📤 Document Upload
- **Drag-and-drop** or click-to-browse upload zone
- Supported formats: **`.pdf`** and **`.docx`** (max **10 MB**)
- Upload-time validation, animated progress state, and clear error messages
- Automatic image-count detection per document

### 📖 Document Dashboard (Document Hub)
- Personal document library filtered to the current user
- Per-document **Edit** and **Download** actions with upload dates
- Refresh / loading / empty-state handling

### ✍️ Document Editor & Content Editing
- View the extracted text content of PDF and DOCX files
- **Edit paragraph content** in place (paragraph-index based for DOCX, page + text-block based for PDF)
- **Save edits** straight back into the file

### 🔍 Find & Replace
- Replace text across the whole document with **case-sensitive** toggle
- Applies to body paragraphs **and table cells** (DOCX)
- Reports the number of matches replaced

### 🎨 Styling Panel
- **Font family** (Arial, Times New Roman, Calibri, Courier New)
- **Font size** (6–72 pt)
- **Header text** and **Footer text** for every section
- **Image replacement** — pick an image index and upload a new image to swap it (works for both PDF and DOCX)

### 🤖 RapidDoc AI — Natural Language Command Interface
- Type a plain-English command into the AI prompt bar, e.g. `replace "sales" with "revenue"`
- AI understands intent and **executes the edit automatically** (e.g. find-and-replace across the document)
- Gemini-style **AI processing overlay** with cycling status messages:
  *Initializing → Scanning → Finding text blocks → Analyzing content → Applying changes*
- Response feedback confirming exactly what was changed

### 🗂️ Document Info
- File name, type (PDF/DOCX), image count
- **Edit history** timeline tracking every upload, style update, content edit, and find-and-replace action

### 🏠 Landing Page & Navigation
- Marketing landing page with hero, features, and "How It Works" sections
- Context-aware CTAs: guests see *Login / Get Started*, signed-in users see *Go to Dashboard*
- Home / Dashboard navigation available from the editor and every screen

---

## 🧱 Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 19, Vite 8, Tailwind CSS 3, Lucide Icons, Oxlint |
| **Backend** | FastAPI (Python) + Uvicorn |
| **Document Processing** | `python-docx` (DOCX), PyMuPDF `fitz` (PDF) |
| **Database** | MongoDB (via PyMongo) |
| **Authentication** | JWT (python-jose), Bcrypt password hashing |
| **Storage** | Local filesystem (`backend/storage`), path-traversal-safe |

---

## 📁 Project Structure

```
RapidDoc/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, CORS, global error handlers
│   │   ├── config.py               # Settings from .env (pydantic-settings)
│   │   ├── database.py             # MongoDB connection manager
│   │   ├── models.py               # Pydantic request/response models
│   │   ├── routers/
│   │   │   ├── auth.py             # Register / Login / Me
│   │   │   └── documents.py        # Upload / List / Download / Style / Content / Find-Replace
│   │   └── services/
│   │       ├── storage.py          # File storage with traversal protection
│   │       ├── docx_editor.py      # DOCX styling, content, find-replace
│   │       └── pdf_editor.py       # PDF styling, content, find-replace
│   ├── requirements.txt
│   ├── .env.example
│   └── storage/                    # Uploaded documents
├── frontend/
│   └── src/
│       ├── App.jsx                 # Landing, Dashboard, routing & main layout
│       ├── components/
│       │   ├── Auth/Login.jsx      # Login screen
│       │   ├── Auth/Register.jsx   # Register + password strength
│       │   ├── Dashboard/UploadZone.jsx    # Drag-and-drop upload
│       │   ├── Dashboard/DocumentList.jsx  # Document library
│       │   ├── Editor/DocumentWorkspace.jsx# Editor + AI prompt bar
│       │   └── Editor/StylingPanel.jsx     # Fonts / header / footer / images
│       ├── context/AuthContext.jsx # Auth state, login/register/logout
│       └── utils/download.js       # File download helper
├── run_dev.bat                     # One-click dev launcher
└── README.md
```

---

## 🔄 How It Works

```
Upload Document → Enter Natural-Language Command → AI Understands Intent
      → Document Processing Engine Executes the Operation
      → Preview Updated Document → Download Final Document
```

### Backend API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Create a new account |
| `POST` | `/api/auth/login` | Login, returns a JWT token |
| `GET` | `/api/auth/me` | Current authenticated user |
| `POST` | `/api/documents/upload` | Upload PDF/DOCX (max 10 MB) |
| `GET` | `/api/documents` | List user's documents |
| `GET` | `/api/documents/{id}/download` | Download the file |
| `POST` | `/api/documents/{id}/style` | Apply font/header/footer/image changes |
| `GET` | `/api/documents/{id}/content` | Get extracted text content |
| `POST` | `/api/documents/{id}/content` | Save content edits |
| `POST` | `/api/documents/{id}/find-replace` | Find & replace text |

Interactive docs are available at `http://localhost:8000/docs` (Swagger UI).

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.10+**
- **Node.js 18+**
- **MongoDB Community Server** — [download](https://www.mongodb.com/try/download/community)

### Option 1 — One-Click Launcher (Windows)
Double-click **`run_dev.bat`**. It:
1. Creates `backend/storage` and `mongodb_data` folders if missing
2. Starts MongoDB on `mongodb_data`
3. Launches the FastAPI backend on `http://localhost:8000`
4. Launches the React frontend on `http://localhost:5173`

### Option 2 — Manual Setup

**Backend:**
```bash
cd backend
python -m venv venv
venv\Scripts\activate              # Windows
pip install -r requirements.txt
copy .env.example .env            # Windows
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Then open **http://localhost:5173** and register an account.

---

## 📚 Useful Commands

| Command | Purpose |
|---|---|
| `npm run dev` | Start Vite dev server (frontend) |
| `npm run build` | Production build |
| `npm run lint` | Lint with Oxlint |
| `python -m uvicorn app.main:app --reload` | Start backend |

---

## 🗺️ Roadmap (Planned)

Per the project proposal, the following AI capabilities are planned for the AI pipeline:

- 📝 **Summarization** — generate document summaries
- 🌐 **Translation** — multilingual translation
- 🧠 **Study Notes** — automatic note generation
- ❓ **MCQ Generation** — quiz questions from content
- 🃏 **Flashcards** — flashcard creation
- 🎤 **Viva Question Generation**
- 🔑 **Keyword Extraction**
- 📊 **PPTX / TXT export** (secondary formats)

---

## 🏛️ Academic Project Details

From the project proposal (Semester 5, DEPSTAR — CHARUSAT):

- **Project ID:** `PRJ_CSE_5_2026_28`
- **Domain:** Artificial Intelligence (AI), Natural Language Processing (NLP), Document Engineering, Web Application Development
- **Team:** 24DCS145 (Team Lead), 24DCS135, 24DCS140
- **Target Users:** Students, faculty, businesses, and researchers

---

© 2026 RapidDoc. All rights reserved.
