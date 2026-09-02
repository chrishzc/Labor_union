"""
File: test_staff_beclass_profile_mapping.py
Description: Regression coverage for Staff BeClass profile fields that were previously dropped.
"""

from __future__ import annotations

from subsystems.case_import.staff_historical_workbook import _record, _relations


def test_staff_beclass_profile_fields_are_preserved_by_business_topic():
    raw = {
        "姓名": "測試月嫂",
        "學歷": "高職",
        "緊急聯絡人": "王小明",
        "緊急聯絡人電話": "0912-345-678",
        "行政註記": "僅供內部使用",
        "警察刑事紀錄證明": "Y",
        "CPR急救證書": "Y",
        "體檢證明": "Y",
        "有嬰幼兒按摩證書嗎?": "有",
        "北區": "Y",
        "[其它].1": "竹北",
        "4小時(上午8:30-12:30)": "Y",
        "[其它].2": "可提早半小時",
        "葷食": "Y",
        "[其它]": "低油料理",
        "連續服務": "Y",
        "[其它].3": "每兩週休一天",
        "單胞胎": "Y",
        "[其它].4": "三胞胎需家屬協助",
        "機車": "Y",
        "端午節": "Y",
        "[其它].5": "清明節不接案",
    }

    record = _record(raw, {})
    relations = _relations(raw)

    assert record["education"] == "高職"
    assert record["emergency_contact_name"] == "王小明"
    assert record["emergency_contact_phone"] == "0912345678"
    assert record["admin_notes"] == "僅供內部使用"
    assert record["has_massage_cert"] is True
    assert record["care_babies"] == 3

    assert relations["staff_certifications"] == (
        ("警察刑事紀錄證明",),
        ("CPR急救證書",),
        ("體檢證明",),
    )
    assert ("其他", "竹北") in relations["staff_regions"]
    assert ("其他", "可提早半小時") in relations["staff_time_slots"]
    assert ("其他", "低油料理") in relations["staff_cooking_skills"]
    assert ("其他", "每兩週休一天") in relations["staff_weekly_rest"]
    assert ("其他", "三胞胎需家屬協助") in relations["staff_baby_types"]
    assert ("其他", "清明節不接案") in relations["staff_holiday_availability"]


def test_staff_education_header_aliases_are_preserved():
    for header in ("教育程度", "最高學歷", "學歷"):
        record = _record({"姓名": "測試月嫂", header: "高職"}, {})
        assert record["education"] == "高職"


def test_staff_certification_detection_is_bounded_to_qualification_headers():
    raw = {
        "北區": "Y",
        "8小時": "Y",
        "機車": "Y",
        "國定假日必休": "Y",
        "有嬰幼兒按摩證書嗎?": "有",
        "托育人員證照": "Y",
    }

    relations = _relations(raw)

    assert relations["staff_certifications"] == (("托育人員證照",),)
