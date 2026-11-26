"""Versioned LINE FAQ card definitions and their published-answer projection."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from unicodedata import normalize
from uuid import uuid4


FAQ_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}"


@dataclass(frozen=True, slots=True)
class FaqQuestionLink:
    qa_id: str
    label: str


@dataclass(frozen=True, slots=True)
class FaqCategory:
    category_id: str
    name: str
    title: str
    description: str
    footer_label: str
    questions: tuple[FaqQuestionLink, ...]


@dataclass(frozen=True, slots=True)
class FaqLayout:
    categories: tuple[FaqCategory, ...] = ()

    def find(self, category_id: str) -> FaqCategory | None:
        return next((card for card in self.categories if card.category_id == category_id), None)


@dataclass(frozen=True, slots=True)
class FaqIssue:
    code: str
    field: str
    qa_id: str | None = None


class FaqLayoutInvalid(ValueError):
    def __init__(self, *issues: FaqIssue) -> None:
        self.issues = issues
        super().__init__("faq_layout_invalid")


class PublishedFaqAnswer(Protocol):
    @property
    def question(self) -> str: ...

    @property
    def answer(self) -> str: ...


@dataclass(frozen=True, slots=True)
class FaqButton:
    qa_id: str
    label: str
    question: str
    answer: str


@dataclass(frozen=True, slots=True)
class FaqCardView:
    category_id: str
    title: str
    description: str
    footer_label: str
    buttons: tuple[FaqButton, ...]


@dataclass(frozen=True, slots=True)
class FaqPreview:
    view: FaqCardView
    issues: tuple[FaqIssue, ...]


def _invalid(code: str, field: str) -> FaqLayoutInvalid:
    return FaqLayoutInvalid(FaqIssue(code, field))


def _object(value: object, keys: set[str], path: str) -> dict[str, object]:
    if not isinstance(value, dict) or value.keys() != keys:
        raise _invalid("invalid_fields", path)
    return value


def _array(value: object, path: str) -> list[object] | tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise _invalid("invalid_array", path)
    return value


def _text(value: object, maximum: int, path: str, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise _invalid("invalid_text", path)
    value = value.strip()
    if (required and not value) or len(value) > maximum:
        raise _invalid("invalid_length", path)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise _invalid("invalid_text", path) from error
    return value


def _id(value: object, path: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(FAQ_ID_PATTERN, value):
        raise _invalid("invalid_id", path)
    return value


def _name_key(name: str) -> str:
    return normalize("NFKC", name).casefold()


def decode_layout(payload: object) -> FaqLayout:
    """Decode storage or transport data through the same card constraints."""
    root = _object(payload, {"categories"}, "layout")
    categories = []
    seen_ids = set()
    seen_names = set()
    for index, raw in enumerate(_array(root["categories"], "categories")):
        path = f"categories[{index}]"
        card = _object(
            raw, {"category_id", "name", "title", "description", "footer_label", "questions"}, path,
        )
        category_id = _id(card["category_id"], f"{path}.category_id")
        name = _text(card["name"], 24, f"{path}.name", required=True)
        name_key = _name_key(name)
        if category_id in seen_ids:
            raise _invalid("duplicate_category_id", f"{path}.category_id")
        if name_key in seen_names:
            raise _invalid("duplicate_category_name", f"{path}.name")
        seen_ids.add(category_id)
        seen_names.add(name_key)
        categories.append(FaqCategory(
            category_id,
            name,
            _text(card["title"], 36, f"{path}.title"),
            _text(card["description"], 150, f"{path}.description"),
            _text(card["footer_label"], 28, f"{path}.footer_label"),
            _decode_links(card["questions"], f"{path}.questions"),
        ))
    return FaqLayout(tuple(categories))


def _decode_links(value: object, path: str) -> tuple[FaqQuestionLink, ...]:
    questions = _array(value, path)
    if len(questions) > 4:
        raise _invalid("too_many_questions", path)
    links = []
    seen_ids = set()
    for index, raw in enumerate(questions):
        link_path = f"{path}[{index}]"
        item = _object(raw, {"qa_id", "label"}, link_path)
        qa_id = _id(item["qa_id"], f"{link_path}.qa_id")
        if qa_id in seen_ids:
            raise _invalid("duplicate_qa_id", f"{link_path}.qa_id")
        seen_ids.add(qa_id)
        links.append(FaqQuestionLink(qa_id, _text(item["label"], 24, f"{link_path}.label")))
    return tuple(links)


def add_category(layout: FaqLayout, name: str) -> FaqCategory:
    name = _text(name, 24, "name", required=True)
    if any(_name_key(card.name) == _name_key(name) for card in layout.categories):
        raise _invalid("duplicate_category_name", "name")
    return FaqCategory(f"fc-{uuid4().hex}", name, name, "", "", ())


def validate_card_edits(current: FaqLayout, edited: FaqLayout) -> None:
    current_categories = tuple((card.category_id, card.name) for card in current.categories)
    edited_categories = tuple((card.category_id, card.name) for card in edited.categories)
    if current_categories != edited_categories:
        raise _invalid("category_identity_changed", "categories")


def faq_short_label(text: str, max_length: int = 24) -> str:
    if len(text) <= max_length:
        return text
    return f"{text[:max_length - 1]}…"


def project_category(
    layout: FaqLayout,
    category_id: str,
    get_published_faq: Callable[[str], PublishedFaqAnswer | None],
) -> FaqPreview | None:
    for index, card in enumerate(layout.categories):
        if card.category_id == category_id:
            return _project_card(card, index, get_published_faq)
    return None


def _project_card(
    card: FaqCategory,
    index: int,
    get_published_faq: Callable[[str], PublishedFaqAnswer | None],
) -> FaqPreview:
    buttons, issues = [], []
    for position, link in enumerate(card.questions):
        item = get_published_faq(link.qa_id)
        if item is None:
            issues.append(FaqIssue(
                "faq_question_not_published", f"categories[{index}].questions[{position}].qa_id", link.qa_id,
            ))
            continue
        buttons.append(FaqButton(link.qa_id, link.label or faq_short_label(item.question), item.question, item.answer))
    return FaqPreview(
        FaqCardView(card.category_id, card.title, card.description, card.footer_label, tuple(buttons)),
        tuple(issues),
    )


def validate_publication(layout: FaqLayout, get_published_faq: Callable[[str], PublishedFaqAnswer | None]) -> None:
    if not layout.categories:
        raise _invalid("empty_layout", "categories")
    issues = []
    for index, card in enumerate(layout.categories):
        if not card.title:
            issues.append(FaqIssue("title_required", f"categories[{index}].title"))
        projection = _project_card(card, index, get_published_faq)
        issues.extend(projection.issues)
        if not projection.view.buttons:
            issues.append(FaqIssue("published_question_required", f"categories[{index}].questions"))
    if issues:
        raise FaqLayoutInvalid(*issues)
