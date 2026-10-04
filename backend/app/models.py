from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, description="Password must be at least 6 characters")
    name: str = Field(..., min_length=2, description="Name must be at least 2 characters")

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    email: Optional[str] = None
    user_id: Optional[str] = None

class DocumentMetadata(BaseModel):
    id: str
    name: str
    file_type: str  # "pdf" or "docx"
    storage_path: str
    original_storage_path: Optional[str] = None  # uploaded original when an edited copy exists
    has_edited_version: Optional[bool] = False
    owner_id: str
    upload_date: str  # YYYY-MM-DD format as requested
    edit_history: List[Dict[str, Any]] = []
    pipeline_stage: Optional[int] = 1 # 1: Ingested, 2: Header/Footer, 3: Content Editing, 4: Finalized
    pipeline_status: Optional[str] = "In Progress" # "In Progress", "Paused", "Finalized"
    completion_percent: Optional[int] = 25
    draft_edits: Optional[Dict[str, Any]] = None
    last_edited_date: Optional[str] = None

class StyleUpdateRequest(BaseModel):
    font_name: Optional[str] = None
    font_size: Optional[float] = None
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    image_replacements: Optional[List[Dict[str, Any]]] = None # List of {"target_index": int, "image_name": str} or similar

class TextEditItem(BaseModel):
    # Which addressing space `text` belongs to. "paragraph" is the default so
    # older clients that only send `index` keep working untouched.
    kind: Optional[str] = Field(default="paragraph", description='"paragraph" or "table_cell"')
    index: Optional[int] = None          # DOCX body paragraph index
    page_num: Optional[int] = None       # PDF page
    block_no: Optional[int] = None       # PDF text block on that page
    bbox: Optional[List[float]] = None
    # DOCX table addressing. `table_index` is the position of the w:tbl in the
    # body (the same `table_index` the /content block stream reports), and
    # row/col are 0-based indices into `table.rows` / `row.cells` - i.e. the
    # exact coordinates the editor renders, so reads and writes agree.
    table_index: Optional[int] = None
    row: Optional[int] = None
    col: Optional[int] = None
    text: str

class ContentUpdateRequest(BaseModel):
    edits: List[TextEditItem]

class FindReplaceRequest(BaseModel):
    find_text: str
    replace_text: str
    case_sensitive: Optional[bool] = True

class AICommandRequest(BaseModel):
    command: str
    # True when the client sent this command alongside an attached image. Tells
    # the intent cascade that a picture is available to swap in, so "replace the
    # logo" resolves to replace_image instead of a text replace of "the logo".
    has_image_upload: Optional[bool] = False


class ImageResizeItem(BaseModel):
    # One resize, on the canonical image index space (the integer the editor
    # already shows for the tile the user clicked).
    index: int = Field(..., ge=0)
    # At least one of width/height must be given; the writers reject an empty one
    # with a readable message rather than silently doing nothing.
    width: Optional[float] = Field(None, gt=0)
    height: Optional[float] = Field(None, gt=0)
    unit: str = "px"
    # Default True: distorting a logo is rarely intended and is easy to miss in a
    # thumbnail. False applies both dimensions exactly as given.
    keep_aspect: bool = True
    # Which point stays put when the box changes: "top_left" (a dragged corner)
    # or "center" (a dialog that grows the picture about its middle).
    anchor: str = "top_left"


class ImageResizeRequest(BaseModel):
    items: List[ImageResizeItem]

class RewriteRequest(BaseModel):
    # Instruction like "Fix grammar", "Make it formal", "Simplify this text"
    instruction: Optional[str] = None
    # Raw text to rewrite (takes precedence when provided)
    text: Optional[str] = None
    # DOCX paragraph index (used when text is not provided)
    index: Optional[int] = None
    # PDF page/block reference (used when text is not provided)
    page_num: Optional[int] = None
    block_no: Optional[int] = None

class SummarizeRequest(BaseModel):
    # "document" (whole file) or "page" (PDF page / DOCX paragraph)
    scope: str = "document"
    # Required when scope == "page".
    #   PDF  -> 1-based page number
    #   DOCX -> 0-based paragraph index
    page: Optional[int] = None
    # Explicit text to summarize; skips document parsing when provided.
    text: Optional[str] = None
    # Length hint: "brief" | "short" | "medium" | "detailed" | "one-paragraph"
    length: Optional[str] = None

class SummaryExportRequest(BaseModel):
    """Export a summary the client is already displaying.

    The text comes back from the client rather than being regenerated: a summary
    is a model output, so asking for it twice would produce two different
    documents, and the user asked to save *this* one.
    """
    summary: str
    key_points: List[str] = Field(default_factory=list)
    # "txt" | "docx" | "pdf"
    format: str = "txt"
    source: Optional[str] = None
    engine: Optional[str] = None
    characters: Optional[int] = None
    # Defaults to the document filename when omitted.
    title: Optional[str] = None

class GenerateMCQRequest(BaseModel):
    # How many questions to produce. Capped server-side by MCQ_MAX_QUESTIONS.
    num_questions: int = 5
    # Explicit passage to build questions from; skips document parsing.
    text: Optional[str] = None

class FindVariantsRequest(BaseModel):
    find_text: str
    case_sensitive: Optional[bool] = True

class SelectiveReplaceRequest(BaseModel):
    find_text: str
    replace_text: str
    selected_variants: List[str]
    case_sensitive: Optional[bool] = True

class HeaderFooterRequest(BaseModel):
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    target_header_text: Optional[str] = None
    target_footer_text: Optional[str] = None
    font_name: Optional[str] = None
    font_size: Optional[float] = None
    alignment: Optional[str] = "center" # "left", "center", "right"
    # Left/right page variants. Odd pages are the right-hand (1st, 3rd, ...) pages.
    header_text_odd: Optional[str] = None
    header_text_even: Optional[str] = None
    footer_text_odd: Optional[str] = None
    footer_text_even: Optional[str] = None
    # A separate first page, for a cover sheet or a title page with no furniture.
    header_text_first: Optional[str] = None
    footer_text_first: Optional[str] = None
    # Headers and footers are frequently aligned differently (title left, page
    # number right), so each zone takes its own alignment.
    header_alignment: Optional[str] = None
    footer_alignment: Optional[str] = None

class PipelineUpdateRequest(BaseModel):
    pipeline_stage: Optional[int] = None
    pipeline_status: Optional[str] = None
    completion_percent: Optional[int] = None
    draft_edits: Optional[Dict[str, Any]] = None



