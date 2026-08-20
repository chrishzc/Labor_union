"""
File: test_import_warning_projection_retry.py
Description: 驗證警示投影錯誤去敏、三次上限與一秒重試契約。
"""

from subsystems.anomalies.import_warning_projection_retry import (
    MAX_WARNING_PROJECTION_ATTEMPTS,
    WARNING_PROJECTION_RETRY_DELAY_SECONDS,
    warning_projection_error_code,
)


def test_warning_projection_retry_policy_is_three_attempts_one_second() -> None:
    assert MAX_WARNING_PROJECTION_ATTEMPTS == 3
    assert WARNING_PROJECTION_RETRY_DELAY_SECONDS == 1


def test_warning_projection_error_replaces_raw_text_with_digest() -> None:
    raw = ValueError("完整姓名不得寫入運維錯誤")

    code = warning_projection_error_code(raw, owning_lane="beclass_client")

    assert code.startswith("warning_projection_failed:beclass_client:")
    assert "完整姓名" not in code
