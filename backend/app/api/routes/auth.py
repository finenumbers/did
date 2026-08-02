from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.security import auth_enabled, issue_session_token, verify_password
from app.providers.errors import ProviderError

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class AuthStatusResponse(BaseModel):
    auth_required: bool


@router.get("/status", response_model=AuthStatusResponse, summary="Whether login is required")
def auth_status() -> AuthStatusResponse:
    return AuthStatusResponse(auth_required=auth_enabled())


@router.post("/login", response_model=LoginResponse, summary="Admin login")
def login(body: LoginRequest) -> LoginResponse:
    if not auth_enabled():
        raise ProviderError(
            "Авторизация не настроена (задайте ADMIN_USERNAME и ADMIN_PASSWORD)",
            code="AUTH_DISABLED",
        )
    if not verify_password(body.username, body.password):
        raise ProviderError("Неверный логин или пароль", code="INVALID_CREDENTIALS")
    token = issue_session_token(body.username)
    return LoginResponse(access_token=token, username=body.username.strip())
