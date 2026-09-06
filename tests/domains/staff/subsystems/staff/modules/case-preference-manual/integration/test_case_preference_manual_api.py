from api.schemas.staff_case_preference_manual import ManualApplyBody, RelationsBody


def _payload():
    return {key: [{"value": "北區", "detail": None}] for key in (
        "service_regions", "service_periods", "cooking_skills",
        "holiday_availability", "rest_schedule", "baby_types",
    )}


def test_manual_contract_keeps_six_relation_keys_and_strict_apply_identity():
    body = RelationsBody.model_validate(_payload())
    assert set(body.as_relations()) == set(_payload())
    apply = ManualApplyBody.model_validate({
        **_payload(),
        "expected_snapshot_fingerprint": "a" * 64,
        "preview_fingerprint": "b" * 64,
        "reason": "manual correction",
    })
    assert apply.reason == "manual correction"
