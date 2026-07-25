"""Request and response models for the internal administration session."""

from datetime import datetime

from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class AdminPublic(BaseModel):
    id: int | None
    username: str
    display_name: str
    role: str
    linked_line_user_id: str | None = None


class AdminSessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    admin: AdminPublic


class AdminRefreshResponse(BaseModel):
    expires_at: datetime
