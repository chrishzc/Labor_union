"""
File: cooking_requirement.py
Description: 將 BeClass 受控單選或核取欄位正規化為案件下廚需求。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Mapping


class CookingRequirementIssue(StrEnum):
    MISSING = "case_import_cooking_requirement_missing"
    AMBIGUOUS = "case_import_cooking_requirement_ambiguous"


class CookingRequirementDomainError(ValueError):
    def __init__(self, issue: CookingRequirementIssue, message: str) -> None:
        super().__init__(message)
        self.issue = issue


_QUESTION_ALIASES = (
    "月子餐點調理喜好/飲食習慣：",
    "月子餐點調理喜好/飲食習慣:",
    "月子餐點調理喜好/飲食習慣",
)
_ANSWER_VALUES = {
    "葷食": True,
    "素食": True,
    "不用料理/訂月餐": False,
}
_SELECTED_MARKERS = frozenset({"1", "TRUE", "V", "Y", "YES", "✓", "✔", "是"})


def normalize_cooking_requirement(survey_details: Mapping[str, object]) -> bool:
    """Return the canonical requirement from controlled BeClass fields only."""
    if not isinstance(survey_details, Mapping):
        raise _missing()
    answers = _controlled_answers(survey_details)
    resolved_values = {_ANSWER_VALUES[answer] for answer in answers if answer in _ANSWER_VALUES}
    unrecognized_answers = answers - _ANSWER_VALUES.keys()
    if len(resolved_values) > 1 or (resolved_values and unrecognized_answers):
        raise _ambiguous()
    if not resolved_values:
        raise _missing()
    return resolved_values.pop()


def _controlled_answers(survey_details: Mapping[str, object]) -> set[str]:
    scalar_answers: set[str] = set()
    for question in _QUESTION_ALIASES:
        if question not in survey_details:
            continue
        answer = survey_details[question]
        if isinstance(answer, str) and answer.strip():
            scalar_answers.add(answer.strip())
            continue
        scalar_answers.add("")
    checkbox_answers = {
        answer
        for answer in _ANSWER_VALUES
        if _is_selected_marker(survey_details.get(answer))
    }
    if not checkbox_answers:
        return scalar_answers
    return checkbox_answers | {
        answer for answer in scalar_answers if answer in _ANSWER_VALUES
    }


def _is_selected_marker(value: object) -> bool:
    if value is True:
        return True
    if not isinstance(value, str):
        return False
    return value.strip().upper() in _SELECTED_MARKERS


def _missing() -> CookingRequirementDomainError:
    return CookingRequirementDomainError(
        CookingRequirementIssue.MISSING,
        "The BeClass cooking requirement answer is missing or unsupported.",
    )


def _ambiguous() -> CookingRequirementDomainError:
    return CookingRequirementDomainError(
        CookingRequirementIssue.AMBIGUOUS,
        "The BeClass cooking requirement answers conflict.",
    )


__all__ = [
    "CookingRequirementDomainError",
    "CookingRequirementIssue",
    "normalize_cooking_requirement",
]
