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


def test_manual_options_are_authenticated_and_are_not_shadowed_by_staff_id_route():
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from api.routes.staff_case_preference_manual import router
    from api.dependencies.admin_auth import require_admin
    from domains.staff.case_preference_manual import RELATION_OPTIONS
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: (_ for _ in ()).throw(HTTPException(401, "required"))
    client = TestClient(app)
    assert client.get('/api/v1/staff/case-preference-manual/options').status_code == 401
    app.dependency_overrides[require_admin] = lambda: object()
    response = client.get('/api/v1/staff/case-preference-manual/options')
    assert response.status_code == 200
    assert response.json()['data']['options'] == {key: list(values) for key, values in RELATION_OPTIONS.items()}


def test_service_window_transport_preserves_typed_clocks_without_extra_fields_on_other_topics():
    from domains.staff.case_preference_manual import normalize_relations
    from api.routes.staff_case_preference_manual import _relations_payload
    from api.schemas.staff_case_preference_manual import ManualSnapshotView
    body=RelationsBody.model_validate({**_payload(),'service_periods':[{'value':'8小時','detail':None,'service_hours':8,'start_time':'08:30','end_time':'17:00','end_day_offset':0}]})
    relations=normalize_relations(body.as_relations())
    rows=_relations_payload(relations)
    snapshot=ManualSnapshotView.model_validate({'staff_id':7,'before':rows,'after':rows,'snapshot_fingerprint':'a'*64,'preview_fingerprint':None}).model_dump()
    assert set(snapshot['after']['service_regions'][0])=={'value','detail'}
    period=snapshot['after']['service_periods'][0]
    assert period['value']=='8小時(08:30-17:00)' and period['detail'] is None
    assert period['service_hours']==8 and period['start_time']=='08:30' and period['end_day_offset']==0
