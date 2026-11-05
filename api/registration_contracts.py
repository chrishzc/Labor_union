"""Pure public questionnaire-to-owner mapping, shared without SQL imports."""
from domains.case_import.provisional_registration import ProvisionalRegistrationIntent

# Kept as one mapping so every public registration field has one auditable owner input.
def registration_intent(payload, line_user_id):
    return ProvisionalRegistrationIntent(
        line_user_id=line_user_id.value,
        name=payload.name,
        phone=payload.phone,
        expected_date=payload.expected_date,
        service_days=payload.service_days,
        address=payload.address,
        gender=payload.gender,
        email=payload.email,
        birth_date=payload.birth_date,
        tel=payload.tel,
        ext=payload.ext,
        city=payload.city,
        zip_code=payload.zip_code,
        id_number=payload.id_number,
        liff_config_revision=payload.liff_config_revision,
        survey_details=payload.survey_details,
        registration_kind=payload.registration_kind,
        service_start_date=payload.service_start_date,
        service_time=payload.service_time,
        residence_type=payload.residence_type,
        delivery_type=payload.delivery_type,
        service_type=payload.service_type,
        baby_info=payload.baby_info,
        notes=payload.notes,
        line_id=payload.line_id,
    )

