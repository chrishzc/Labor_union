"""
File: jobs.py
Description: 定義背景工作狀態與安全觀察的公開傳輸契約。
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

_JobCommandType = Literal[
    "assignment_plan_apply",
    "finance_import_historical_reprocess_apply",
    "finance_import_batch_apply",
    "finance_import_correction_apply",
    "orders_auto_completion_apply",
    "government_subsidy_apply",
    "payroll_rebuild_apply",
    "staff_payout_apply",
]
_JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class JobSuccessOutcomeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["success"]
    schema_version: Literal[1]
    result_reference: str = Field(min_length=1, max_length=191)


class JobFailureErrorView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal[
        "validation",
        "conflict",
        "domain_blocked",
        "idempotency_mismatch",
        "unavailable",
        "internal",
    ]
    code: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=512)
    retryable: bool
    correlation_id: str | None = Field(default=None, min_length=1, max_length=255)
    domain_blockers: tuple[str, ...] = ()


class JobFailureOutcomeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["failure"]
    schema_version: Literal[1]
    error: JobFailureErrorView


JobTerminalOutcomeView = Annotated[
    JobSuccessOutcomeView | JobFailureOutcomeView,
    Field(discriminator="kind"),
]


class JobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: _JobStatus
    command_type: _JobCommandType
    attempt_count: int = Field(ge=0)
    max_attempts: int = Field(ge=0)
    outcome: JobTerminalOutcomeView | None = None

class JobAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status_url: str

class JobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: _JobStatus


class JobObservationView(BaseModel):
    """人工查詢用的最小背景工作狀態投影，不含 receipt/error payload。"""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1, max_length=191)
    command_type: _JobCommandType
    status: _JobStatus
    attempt_count: int = Field(ge=0)
    max_attempts: int = Field(ge=0)
