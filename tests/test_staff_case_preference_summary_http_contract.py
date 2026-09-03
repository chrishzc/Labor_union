from pathlib import Path


def test_staff_route_exposes_admin_bounded_case_preference_get():
    source = Path("api/routes/staff.py").read_text(encoding="utf-8")
    assert '"/{staff_id}/case-preference-summary"' in source
    assert "response_model=BaseResponse[StaffCasePreferenceSummaryView]" in source
    assert "principal: AdminPrincipal = Depends(require_admin)" in source
    assert "StaffCasePreferenceSummaryQueryRequest(staff_id=staff_id)" in source
    assert "staff_case_preference_summary_not_found" in source
    assert "@router.post" not in source
    assert "@router.put" not in source
    assert "@router.patch" not in source
