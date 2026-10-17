"""Closed transport contract for manually registered Staff qualification facts."""
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from typing import Annotated

Text191 = Annotated[str, Field(min_length=1, max_length=191)]
Text50 = Annotated[str, Field(min_length=1, max_length=50)]


class QualificationFactsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    special_skills: list[Text191] = Field(max_length=100)
    has_massage_cert: StrictBool | None
    certifications: list[Text191] = Field(max_length=100)
    care_babies: Annotated[StrictInt, Field(gt=0, le=2147483647)] | None
    transportation: list[Text50] = Field(max_length=100)

    def facts(self):
        return {key: getattr(self, key) for key in QualificationFactsBody.model_fields}


class QualificationApplyBody(QualificationFactsBody):
    expected_snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(default="", max_length=500)


class QualificationSnapshotView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    staff_id: int = Field(gt=0)
    before: QualificationFactsBody
    after: QualificationFactsBody
    snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    preview_fingerprint: str | None


class QualificationReceiptView(QualificationSnapshotView):
    idempotency_key: str
    replayed: bool
    correlation_id: str
