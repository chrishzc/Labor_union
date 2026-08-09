"""HTTP schemas for human Contract Integration evidence operations."""

from pydantic import BaseModel, ConfigDict, Field


class ContractMappingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=50)
    provider_contract_id: str = Field(min_length=1, max_length=191)
    internal_contract_identity: str = Field(min_length=1, max_length=191)
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)


__all__ = ["ContractMappingBody"]

