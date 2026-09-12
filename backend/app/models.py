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
    index: Optional[int] = None
    page_num: Optional[int] = None
    block_no: Optional[int] = None
    bbox: Optional[List[float]] = None
    text: str

class ContentUpdateRequest(BaseModel):
    edits: List[TextEditItem]

class FindReplaceRequest(BaseModel):
    find_text: str
    replace_text: str
    case_sensitive: Optional[bool] = True

class AICommandRequest(BaseModel):
    command: str

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

class PipelineUpdateRequest(BaseModel):
    pipeline_stage: Optional[int] = None
    pipeline_status: Optional[str] = None
    completion_percent: Optional[int] = None
    draft_edits: Optional[Dict[str, Any]] = None


