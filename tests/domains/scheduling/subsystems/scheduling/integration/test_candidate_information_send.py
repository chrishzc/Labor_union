"""Preview/send equivalence and stale rejection without a DB or LINE provider."""
from types import SimpleNamespace

from api.schemas.candidate_contact_pool import CandidateInformationPreviewView


def test_preview_schema_exposes_the_same_ordered_sections_used_for_line_delivery():
    preview = SimpleNamespace(
        case_no="CASE-1",
        candidate_id=3,
        info_type=1,
        staff_name="測試月嫂",
        text="訂單資訊－1",
        line_sections=(SimpleNamespace(
            title="契約重點",
            rows=(("預計服務開始日", "2026-10-01"), ("每日服務時數", "8")),
        ),),
        preview_fingerprint="a" * 64,
    )

    view = CandidateInformationPreviewView.model_validate(preview)

    assert view.line_sections[0].title == "契約重點"
    assert view.line_sections[0].rows == [
        ("預計服務開始日", "2026-10-01"),
        ("每日服務時數", "8"),
    ]
