from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PaymentDestinationView(_StrictModel):
    configured: bool
    account_display: str | None = None
    revision: int = Field(ge=0)


class PaymentDestinationPreviewBody(_StrictModel):
    account_display: str = Field(min_length=1, max_length=255)
    expected_revision: int = Field(ge=0)


class PaymentDestinationApplyBody(PaymentDestinationPreviewBody):
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=255)


class PaymentDestinationPreviewView(_StrictModel):
    current: PaymentDestinationView
    candidate_account_display: str
    expected_revision: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class PaymentDestinationReceiptView(_StrictModel):
    account_display: str
    resulting_revision: int = Field(ge=1)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

