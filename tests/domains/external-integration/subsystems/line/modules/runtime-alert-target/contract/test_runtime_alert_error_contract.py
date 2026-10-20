"""Keep target errors intact at the strict global HTTP boundary."""
import pytest

from api.routes.runtime_health import _target_error
from api.schemas.errors import GlobalTypedErrorDetailView
from subsystems.line.runtime_alert_target_contracts import RuntimeAlertTargetError


@pytest.mark.parametrize("category,code,status", [
    ("conflict", "line_alert_preferences_fixed", 409),
    ("not_found", "line_alert_target_not_found", 404),
])
def test_target_error_preserves_specific_code_in_global_contract(category, code, status):
    response = _target_error(RuntimeAlertTargetError(category, code, "公開錯誤"), "fixed-rule-test")
    detail = GlobalTypedErrorDetailView.model_validate(response.detail)
    assert response.status_code == status
    assert detail.error.code == code
    assert detail.error.current_version is None
    assert detail.error.correlation_id == "fixed-rule-test"
