"""
File: test_cooking_requirement.py
Description: 驗證 BeClass 單選與核取欄位的下廚需求正規化及 fail-closed。
"""

import pytest

from domains.case_import.cooking_requirement import (
    CookingRequirementDomainError,
    CookingRequirementIssue,
    normalize_cooking_requirement,
)


@pytest.mark.parametrize("answer", ("葷食", "素食"))
def test_food_preference_requires_cooking(answer):
    survey = {"月子餐點調理喜好/飲食習慣：": answer}

    assert normalize_cooking_requirement(survey) is True


def test_monthly_meal_service_does_not_require_cooking():
    survey = {"月子餐點調理喜好/飲食習慣：": "不用料理/訂月餐"}

    assert normalize_cooking_requirement(survey) is False


@pytest.mark.parametrize(
    ("answer", "expected"),
    (("需要下廚", True), ("不需要下廚", False)),
)
def test_explicit_line_cooking_answer_is_a_controlled_source(answer, expected):
    assert normalize_cooking_requirement({"是否需要下廚：": answer}) is expected


def test_explicit_line_cooking_answer_conflicting_with_legacy_answer_is_rejected():
    with pytest.raises(CookingRequirementDomainError) as captured:
        normalize_cooking_requirement(
            {"是否需要下廚：": "不需要下廚", "月子餐點調理喜好/飲食習慣：": "葷食"}
        )

    assert captured.value.issue is CookingRequirementIssue.AMBIGUOUS


@pytest.mark.parametrize(
    "question",
    (
        "月子餐點調理喜好/飲食習慣：",
        "月子餐點調理喜好/飲食習慣:",
        "月子餐點調理喜好/飲食習慣",
    ),
)
def test_controlled_question_aliases_are_supported(question):
    assert normalize_cooking_requirement({question: "葷食"}) is True


@pytest.mark.parametrize(
    "survey",
    (
        {},
        {"餐點喜忌備註：": "葷食"},
        {"月子餐點調理喜好/飲食習慣：": ""},
        {"月子餐點調理喜好/飲食習慣：": "自行討論"},
        {"月子餐點調理喜好/飲食習慣：": ["葷食"]},
    ),
)
def test_missing_or_unsupported_answer_has_typed_issue(survey):
    with pytest.raises(CookingRequirementDomainError) as captured:
        normalize_cooking_requirement(survey)

    assert captured.value.issue is CookingRequirementIssue.MISSING


def test_conflicting_alias_answers_have_typed_issue():
    survey = {
        "月子餐點調理喜好/飲食習慣：": "葷食",
        "月子餐點調理喜好/飲食習慣:": "不用料理/訂月餐",
    }

    with pytest.raises(CookingRequirementDomainError) as captured:
        normalize_cooking_requirement(survey)

    assert captured.value.issue is CookingRequirementIssue.AMBIGUOUS


def test_recognized_and_unknown_alias_answers_are_ambiguous():
    survey = {
        "月子餐點調理喜好/飲食習慣：": "素食",
        "月子餐點調理喜好/飲食習慣": "自行討論",
    }

    with pytest.raises(CookingRequirementDomainError) as captured:
        normalize_cooking_requirement(survey)

    assert captured.value.issue is CookingRequirementIssue.AMBIGUOUS


def test_free_text_is_not_scanned_for_keywords():
    survey = {
        "餐點喜忌備註：": "希望月嫂準備葷食",
        "烹煮工具": "炒菜鍋",
    }

    with pytest.raises(CookingRequirementDomainError) as captured:
        normalize_cooking_requirement(survey)

    assert captured.value.issue is CookingRequirementIssue.MISSING


def test_controlled_checkbox_wins_over_periodic_composite_question_text():
    survey = {
        "月子餐點調理喜好/飲食習慣：": "葷食、可以接受中藥補品",
        "葷食": "Y",
        "素食": None,
    }

    assert normalize_cooking_requirement(survey) is True


def test_multiple_controlled_checkboxes_are_ambiguous():
    with pytest.raises(CookingRequirementDomainError) as captured:
        normalize_cooking_requirement({"葷食": "Y", "不用料理/訂月餐": "Y"})

    assert captured.value.issue is CookingRequirementIssue.AMBIGUOUS


def test_unselected_controlled_checkboxes_remain_missing():
    with pytest.raises(CookingRequirementDomainError) as captured:
        normalize_cooking_requirement({"葷食": "", "素食": None})

    assert captured.value.issue is CookingRequirementIssue.MISSING
