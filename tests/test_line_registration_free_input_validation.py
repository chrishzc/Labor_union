from pathlib import Path
import re


REGISTER_HTML = Path("line/static/register.html")


def _source() -> str:
    return REGISTER_HTML.read_text(encoding="utf-8")


def _input_tag(source: str, field_id: str) -> str:
    match = re.search(rf'<input\b[^>]*\bid="{re.escape(field_id)}"[^>]*>', source)
    assert match is not None, f"missing input #{field_id}"
    return match.group(0)


def test_free_input_fields_keep_required_and_maxlength_boundaries():
    source = _source()

    name = _input_tag(source, "name")
    assert "required" in name
    assert 'maxlength="30"' in name

    city = _input_tag(source, "city")
    assert "required" not in city
    assert 'maxlength="20"' in city

    address = _input_tag(source, "address")
    assert "required" in address
    assert 'maxlength="120"' in address


def test_free_input_fields_do_not_apply_unapproved_content_or_minimum_length_rules():
    source = _source()

    assert "nameValue.length < 2" not in source
    assert "產婦姓名至少需 2 個字。" not in source
    assert r"/\d/.test(nameValue)" not in source
    assert "產婦姓名不可包含數字。" not in source

    assert "const cityValue = city.value.trim();" not in source
    assert r"^[\u4e00-\u9fa5A-Za-z]{2,20}$" not in source
    assert "縣市請填中文或英文地名，例如新竹市。" not in source

    assert "addressValue.length < 6" not in source
    assert "服務地址請填寫完整地址，至少 6 個字。" not in source

    assert "if (!nameValue) addError(errors, name, '請填寫產婦姓名。');" in source
    assert "if (!addressValue) addError(errors, address, '請填寫服務地址。');" in source
