import os
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
