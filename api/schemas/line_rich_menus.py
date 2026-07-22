"""Requests used by the authenticated Rich Menu operations API."""

from pydantic import BaseModel, Field


class RichMenuPublishRequest(BaseModel):
    reason: str = Field(default="", max_length=500)


class RichMenuPublicationRetryRequest(BaseModel):
    reason: str = Field(default="", max_length=500)
