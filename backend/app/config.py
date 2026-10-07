import os
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MODELS_DIR = os.path.join(BACKEND_DIR, "models")

class Settings(BaseSettings):
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    PROJECT_NAME: str = "RapidDoc API"
    MONGODB_URL: str = "mongodb://localhost:27017/rapiddoc"
    MONGODB_DB_NAME: str = "rapiddoc"
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    STORAGE_TYPE: str = "local"
    STORAGE_LOCAL_PATH: str = "storage"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.8-flash"

    # --- Local brain models (all 4) --------------------------------------
    # Turning this off disables every local brain; requests then fall back to
    # Gemini and finally to the deterministic regex rule engine.
    AI_USE_LOCAL_MODELS: bool = True
    INTENT_MODEL_PATH: str = os.path.join(DEFAULT_MODELS_DIR, "rapiddoc_intent_model")
    TEXT_REWRITER_MODEL_PATH: str = os.path.join(DEFAULT_MODELS_DIR, "rapiddoc_text_rewriter")
    MCQ_GENERATOR_MODEL_PATH: str = os.path.join(DEFAULT_MODELS_DIR, "rapiddoc_mcq_generator")
    SUMMARIZER_MODEL_PATH: str = os.path.join(DEFAULT_MODELS_DIR, "rapiddoc_summarizer")

    # Below this classification confidence, the intent model is considered "unsure"
    # and the request falls back to Gemini, then to the regex rule engine.
    # Measured on this checkpoint, confident intents sit around 0.28-0.78, so the
    # bar has to stay low. A wrong-but-confident intent is harmless: any intent
    # without extractable slots is rejected and falls through anyway.
    INTENT_CONFIDENCE_THRESHOLD: float = 0.15
    INTENT_CONFIDENCE_THRESHOLD_ZERO_SHOT: float = 0.15

    # --- T5 text rewriter (CoEdIT) ---------------------------------------
    # Beam search with num_beams=2 is ~2x faster on CPU than 4 while staying
    # close in quality; no_repeat_ngram=3 prevents repetitive loops.
    T5_NUM_BEAMS: int = 2
    T5_MAX_GEN_LENGTH: int = 256
    T5_NO_REPEAT_NGRAM_SIZE: int = 3
    # jbochi/coedit-small expects "<instruction>: <text>". Override only if the
    # rewriter brain is ever swapped for a model fine-tuned on another template.
    TEXT_REWRITER_TEMPLATE: str = "{instruction}: {text}"

    # --- BART summarizer --------------------------------------------------
    SUMMARIZER_MAX_INPUT_TOKENS: int = 1024
    SUMMARIZER_MAX_GEN_TOKENS: int = 128
    SUMMARIZER_NUM_BEAMS: int = 4
    SUMMARIZER_LENGTH_PENALTY: float = 2.0
    SUMMARIZER_NO_REPEAT_NGRAM_SIZE: int = 3
    # Hard character ceiling applied before tokenising, so a 200-page PDF can
    # never blow past the model's 1024-token window in a confusing way.
    SUMMARIZER_MAX_INPUT_CHARS: int = 12000

    # --- BART MCQ generator ----------------------------------------------
    MCQ_MAX_INPUT_TOKENS: int = 512
    MCQ_MAX_GEN_TOKENS: int = 128
    MCQ_NUM_BEAMS: int = 4
    MCQ_NO_REPEAT_NGRAM_SIZE: int = 3
    # The model is trained on RACE-style 4-option questions and occasionally
    # emits a malformed record. Sampling several beams from ONE beam search
    # (they share the search tree, so this is nearly free) lets us keep the
    # best fully-valid question instead of returning a broken one.
    MCQ_NUM_CANDIDATES: int = 4
    # Guard rails against a user asking for 500 questions on CPU.
    MCQ_MAX_QUESTIONS: int = 10
    MCQ_MIN_PASSAGE_CHARS: int = 120
    # Characters of document text handed to the model per generated question.
    MCQ_PASSAGE_CHARS: int = 1200

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def _secret_must_be_set(cls, value: str) -> str:
        if not value or value == "CHANGE_ME_GENERATE_A_RANDOM_SECRET":
            raise ValueError(
                "JWT_SECRET_KEY is not configured. Copy .env.example to .env and set "
                "a strong random value: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        return value

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
