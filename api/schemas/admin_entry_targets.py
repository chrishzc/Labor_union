"""
File: admin_entry_targets.py
Description: 定義管理端 entry target Query、Preview、Apply 與 receipt 的 closed API schema。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Digest = str
Target = Literal["streamlit", "react"]


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class ArtifactBindingInput(ClosedModel):
    version: str = Field(min_length=1, max_length=191, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$")
    digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    api_compatibility_revision: str = Field(
        min_length=1, max_length=191, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$"
    )


class EntryTargetCommandInput(ClosedModel):
    entry_id: str = Field(min_length=12, max_length=191, pattern=r"^ui-react:#[a-z0-9-]+$")
    expected_state_revision: int = Field(ge=1)
    expected_entry_revision: int = Field(ge=1)
    expected_current_target: Target
    desired_target: Target
    required_react_artifact: ArtifactBindingInput | None = None
    reason_code: Literal["activate_react", "rollback", "rehearsal", "incident_recovery"]


class ArtifactBindingView(ClosedModel):
    version: str
    digest: Digest
    api_compatibility_revision: str


class EntryTargetView(ClosedModel):
    entry_id: str
    replacement_group: str
    current_target: Target
    streamlit_target: str
    react_target: str
    required_react_artifact: ArtifactBindingView | None
    entry_revision: int


class EntryTargetStateView(ClosedModel):
    schema_version: int
    registry_revision: str
    registry_digest: Digest
    revision: int
    entries: list[EntryTargetView]
    receipt_count: int
    state_digest: Digest


class EntryTargetPreviewView(ClosedModel):
    entry_id: str
    current_target: Target
    desired_target: Target
    state_revision: int
    entry_revision: int
    command_fingerprint: Digest
    would_replay: bool


class EntryTargetReceiptView(ClosedModel):
    receipt_id: str
    idempotency_key: str
    entry_id: str
    before_target: Target
    resulting_target: Target
    before_state_revision: int
    resulting_state_revision: int
    before_entry_revision: int
    resulting_entry_revision: int
    artifact_version: str | None
    artifact_digest: Digest | None
    api_compatibility_revision: str | None
    actor_id: str
    reason_code: str
    correlation_id: str
    occurred_at: str
    previous_receipt_digest: Digest | None
    receipt_digest: Digest
    replayed: bool
