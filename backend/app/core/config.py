import os
from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "POS Computer Vision Core API"
    API_V1_STR: str = "/api/v1"
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Supabase credentials
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    NEXT_PUBLIC_SUPABASE_URL: str = ""
    NEXT_PUBLIC_SUPABASE_ANON_KEY: str = ""

    # Redis (Local Docker)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # CORS
    CORS_ORIGINS: List[str] = ["*"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        return ["*"]

    @property
    def effective_supabase_url(self) -> str:
        return self.SUPABASE_URL or self.NEXT_PUBLIC_SUPABASE_URL

    @property
    def effective_supabase_key(self) -> str:
        return self.SUPABASE_KEY or self.NEXT_PUBLIC_SUPABASE_ANON_KEY

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
