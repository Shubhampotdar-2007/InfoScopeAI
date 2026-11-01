"""
Application Configuration Module using Pydantic Settings.
Reads configuration from environment variables or .env file.
"""

from typing import List, Union, Optional, Any
from pathlib import Path
from urllib.parse import urlparse
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"


class Settings(BaseSettings):
    # Application Info
    PROJECT_NAME: str = "InfoScope AI"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS Allowed Origins
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, str) and v.startswith("["):
            try:
                return json.loads(v)
            except Exception:
                return [v]
        elif isinstance(v, list):
            return v
        return ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Supabase Configuration
    SUPABASE_URL: str = Field(default="", description="Supabase project URL")
    SUPABASE_KEY: str = Field(default="", description="Supabase legacy key setting")
    SUPABASE_ANON_KEY: str = Field(default="", description="Supabase anon/publishable key for PostgREST")
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = Field(default=None, description="Supabase service role key (strictly admin)")
    SUPABASE_JWT_AUDIENCE: str = "authenticated"
    SUPABASE_JWT_ALGORITHM: str = "ES256"
    SUPABASE_JWKS_URL: Optional[str] = Field(default=None, description="Supabase JWKS URL override")
    SUPABASE_JWT_ISSUER: Optional[str] = Field(default=None, description="Expected Supabase JWT issuer URL override")
    SUPABASE_JWKS_TIMEOUT_SECONDS: float = Field(default=5.0, description="HTTP timeout for fetching JWKS in seconds")
    SUPABASE_JWKS_CACHE_SECONDS: int = Field(default=300, description="Cache lifespan for JWKS keys in seconds")
    DATABASE_TIMEOUT_SECONDS: float = Field(default=10.0, description="Default timeout for database PostgREST requests in seconds")

    @property
    def supabase_base_url(self) -> str:
        """Extracts clean scheme://netloc from SUPABASE_URL without trailing /rest/v1 paths."""
        if not self.SUPABASE_URL:
            return ""
        parsed = urlparse(self.SUPABASE_URL.strip().strip("'\""))
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return self.SUPABASE_URL.rstrip("/")

    @property
    def postgrest_url(self) -> str:
        """Derives the Supabase PostgREST v1 base endpoint URL."""
        base = self.supabase_base_url
        return f"{base}/rest/v1" if base else ""

    @staticmethod
    def _is_service_role_token(token: str) -> bool:
        """Inspects token payload without cryptographic verification to detect service_role claim."""
        if not token or not isinstance(token, str):
            return False
        try:
            import jwt
            payload = jwt.decode(token.strip(), options={"verify_signature": False})
            return payload.get("role") == "service_role"
        except Exception:
            return False

    @property
    def supabase_anon_key(self) -> str:
        """
        Returns the configured Supabase anon/publishable key.
        Checks SUPABASE_ANON_KEY first.
        Falls back to SUPABASE_KEY only if it is not a service-role key.
        """
        anon = (self.SUPABASE_ANON_KEY or "").strip().strip("'\"")
        if anon:
            if self._is_service_role_token(anon):
                return ""
            return anon

        fallback = (self.SUPABASE_KEY or "").strip().strip("'\"")
        if fallback:
            if not self._is_service_role_token(fallback):
                return fallback
        return ""

    @property
    def jwks_url(self) -> str:
        """Derives the public JWKS endpoint URL from SUPABASE_URL unless explicitly overridden."""
        if self.SUPABASE_JWKS_URL and self.SUPABASE_JWKS_URL.strip():
            return self.SUPABASE_JWKS_URL.strip().strip("'\"")
        base = self.supabase_base_url
        return f"{base}/auth/v1/.well-known/jwks.json" if base else ""

    @property
    def jwt_issuer(self) -> str:
        """Derives the expected Supabase Auth issuer URL from SUPABASE_URL unless explicitly overridden."""
        if self.SUPABASE_JWT_ISSUER and self.SUPABASE_JWT_ISSUER.strip():
            return self.SUPABASE_JWT_ISSUER.strip().strip("'\"")
        base = self.supabase_base_url
        return f"{base}/auth/v1" if base else ""

    # Search Provider Configuration (Tavily Sole Provider)
    TAVILY_API_KEY: str = Field(default="", description="Tavily Search API Key")
    SEARCH_TIMEOUT_SECONDS: float = Field(default=30.0, description="Default timeout for external search requests in seconds")
    TAVILY_TIMEOUT_SECONDS: float = Field(default=15.0, description="Timeout for Tavily search requests in seconds")
    SEARCH_MAX_RESULTS_PER_PROVIDER: int = Field(default=5, description="Max results per search provider")
    SEARCH_MAX_TOTAL_RESULTS: int = Field(default=15, description="Max combined search results")

    model_config = SettingsConfigDict(
        env_file=[str(ENV_PATH), ".env"],
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
