"""Applicant-facing profile LIFF routing contract."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[8]


def test_service_location_fields_are_routed_to_order_change_liff() -> None:
    page = (PROJECT_ROOT / "line/static/profile_update.html").read_text(encoding="utf-8")
    field_definition = page.split("const fields = [", 1)[1].split("].map", 1)[0]

    assert '"name", "姓名"' in field_definition
    assert '"phone", "聯絡電話"' in field_definition
    assert '"city", "縣市"' not in field_definition
    assert '"address", "地址"' not in field_definition
    assert '"residence_type", "居住型態"' not in field_definition
    assert "服務縣市、服務地址及居住型態請由「修改訂單資訊」提出申請" in page
