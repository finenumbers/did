from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://did:did@localhost:5432/did"
    backend_cors_origins: str = "http://localhost:3000"
    # Admin user (when both set, /api/v1 requires login session Bearer token)
    admin_username: str = ""
    admin_password: str = ""
    admin_session_secret: str = ""
    # Optional machine token (Bearer) in addition to login sessions
    admin_api_token: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
