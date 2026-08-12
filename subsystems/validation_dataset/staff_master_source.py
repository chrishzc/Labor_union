"""Test-only adapter for explicitly declared staff-master source facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class StaffMasterSourceFact:
    name: str
    identity_card: str
    phone: str
    birthday: date
    city: str
    care_babies: int


def apply_staff_master_source(cursor, fact: StaffMasterSourceFact) -> int:
    existing_id = _existing_staff_id(cursor, fact.identity_card)
    if existing_id is not None:
        return existing_id
    cursor.execute(_INSERT_STAFF_SQL, _staff_values(fact))
    return int(cursor.lastrowid)


def _existing_staff_id(cursor, identity_card: str) -> int | None:
    cursor.execute("SELECT id FROM staff WHERE identity_card=%s", (identity_card,))
    row = cursor.fetchone()
    return None if row is None else int(row["id"])


def _staff_values(fact: StaffMasterSourceFact) -> tuple[object, ...]:
    return (
        fact.name,
        fact.identity_card,
        fact.phone,
        fact.birthday,
        fact.city,
        "active",
        fact.care_babies,
    )


_INSERT_STAFF_SQL = (
    "INSERT INTO staff "
    "(name,identity_card,phone,birthday,city,status,care_babies) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s)"
)
