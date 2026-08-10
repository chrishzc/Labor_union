import pytest
from fastapi import HTTPException

from line import line_bot


def test_internal_key_only_line_role_writer_is_retired():
    with pytest.raises(HTTPException) as error:
        line_bot.set_line_user_role("U-legacy", "staff")

    assert error.value.status_code == 410
    assert error.value.detail["code"] == "line_role_api_retired"
