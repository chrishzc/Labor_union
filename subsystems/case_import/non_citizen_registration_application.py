"""Project a verified registration into the existing Case Import owner command."""

from datetime import date, datetime

from domains.case_import.cooking_requirement import normalize_cooking_requirement
from domains.case_import.provisional_registration import ProvisionalRegistrationCandidate
from shared_kernel.clock import TAIPEI_TIME_ZONE
from subsystems.case_import.hcm_adapter import (
    build_hcm_case_import_intent,
    calculate_hcm_service_end_date,
)


def non_citizen_case_intent(candidate: ProvisionalRegistrationCandidate, case_no: str,
                            approved_at: datetime, registration_id: int, holidays: set[date]):
    # Reuse the existing field-to-owner projection, not the HCM file intake.
    record = {key: value for key, value in candidate.client_payload.items() if key != "line_user_id"}
    record.update(case_no=case_no, created_at=approved_at.astimezone(TAIPEI_TIME_ZONE).replace(tzinfo=None),
                  service_start_date=date.fromisoformat(record["service_start_date"]))
    end = calculate_hcm_service_end_date(record["service_start_date"], record["service_days"],
                                          record["service_type"], holidays)
    return build_hcm_case_import_intent(
        record, end, requires_cooking=normalize_cooking_requirement(candidate.beclass_payload["survey_details"]),
        provisional_registration_id=registration_id, pricing_identity_rule="non_citizen",
    )
