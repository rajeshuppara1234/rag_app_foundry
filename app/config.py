"""Runtime configuration. Secrets never enter the browser configuration."""

from typing import Literal
from urllib.parse import urlsplit
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    foundry_openai_endpoint: str = ""
    foundry_chat_model: str = ""
    foundry_api_key: SecretStr | None = None
    azure_openai_endpoint: str = ""
    azure_openai_embedding_deployment: str = ""
    azure_openai_api_version: str = "2024-02-01"
    azure_openai_api_key: SecretStr | None = None
    azure_client_id: str | None = None
    chroma_url: str = ""
    chroma_collection: str = "pdf_documents"
    chroma_tenant: str = "default_tenant"
    chroma_database: str = "default_database"
    chroma_auth_header: str = "Authorization"
    chroma_auth_token: SecretStr | None = None
    chroma_timeout_seconds: float = Field(default=10, gt=0, le=30)
    model_timeout_seconds: float = Field(default=45, gt=0, le=60)
    model_max_retries: int = Field(default=1, ge=0, le=2)
    max_answer_tokens: int = Field(default=1024, ge=64, le=4096)
    max_context_chars: int = Field(default=24000, ge=1000, le=60000)
    max_distance: float | None = Field(default=None, ge=0)


class Settings(BackendSettings):
    app_env: Literal["development", "production"] = "production"
    public_origin: str
    auth_authority: str
    auth_issuer: str
    auth_jwks_url: str
    auth_audience: str = Field(min_length=1)
    auth_spa_client_id: str = Field(min_length=1)
    auth_scope: str = Field(min_length=1)
    auth_required_scope: str = "access_as_user"
    requests_per_minute: int = Field(default=10, ge=1, le=120)
    total_requests_per_minute: int = Field(default=60, ge=1, le=1000)
    max_concurrent_requests: int = Field(default=4, ge=1, le=32)
    request_timeout_seconds: float = Field(default=120, gt=0, le=180)

    @model_validator(mode="after")
    def validate_deployment(self):
        for name in ("auth_authority", "auth_issuer", "auth_jwks_url"):
            value = urlsplit(getattr(self, name))
            if (
                value.scheme != "https"
                or not value.hostname
                or value.username
                or value.fragment
            ):
                raise ValueError(f"{name} must be an HTTPS URL")
        origin = urlsplit(self.public_origin)
        if (
            not origin.hostname
            or origin.path not in ("", "/")
            or origin.query
            or origin.fragment
            or origin.username
        ):
            raise ValueError("PUBLIC_ORIGIN must be an origin without a path")
        if origin.scheme != "https" and not (
            self.app_env == "development"
            and origin.scheme == "http"
            and origin.hostname in ("localhost", "127.0.0.1")
        ):
            raise ValueError(
                "PUBLIC_ORIGIN must use HTTPS (except localhost development)"
            )
        self.public_origin = self.public_origin.rstrip("/")
        if self.auth_audience == self.auth_spa_client_id:
            raise ValueError("Register separate API and SPA applications")
        if not self.auth_scope.endswith("/" + self.auth_required_scope):
            raise ValueError("AUTH_SCOPE must end with /AUTH_REQUIRED_SCOPE")
        for name in ("foundry_openai_endpoint", "azure_openai_endpoint", "chroma_url"):
            parsed = urlsplit(getattr(self, name))
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or parsed.username
            ):
                raise ValueError(f"{name} must be a configured HTTP(S) URL")
            if (
                name != "chroma_url"
                and self.app_env == "production"
                and parsed.scheme != "https"
            ):
                raise ValueError(f"{name} must use HTTPS in production")
        if not self.foundry_chat_model or not self.azure_openai_embedding_deployment:
            raise ValueError(
                "Both Foundry chat and embedding deployment names are required"
            )
        if (
            not urlsplit(self.foundry_openai_endpoint)
            .path.rstrip("/")
            .endswith("/openai/v1")
        ):
            raise ValueError("FOUNDRY_OPENAI_ENDPOINT must end in /openai/v1/")
        return self

    def browser_config(self) -> dict:
        return {
            "clientId": self.auth_spa_client_id,
            "authority": self.auth_authority,
            "redirectUri": self.public_origin + "/",
            "scope": self.auth_scope,
        }
