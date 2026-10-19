"""Synthetic Taishin refunds use frozen recipient accounts and need no case column."""

import json
import sqlite3

import pandas as pd
import pytest

from domains.finance_import.planning import (
    CanonicalFinanceImportRow,
    FinanceClassificationType,
    FinanceImportDisposition,
)
from domains.finance_import.transaction_classifier import classify_finance_transaction
from infrastructure.mysql.finance_import_owning_domain_composite import (
    MySqlFinanceImportOwningDomainComposite,
)
from scripts.imports.finance_formats import taishin
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD
from subsystems.finance_import.identity_maps import load_finance_identity_maps


SNAPSHOT_ACCOUNT = "0" * 15 + "1"
CHANGED_PROFILE_ACCOUNT = "0" * 15 + "2"
REFUND_TYPES = ("refund", "subsidy_return")


class _Cursor(sqlite3.Cursor):
    def execute(self, statement, parameters=()):
        return super().execute(statement.replace("%s", "?"), parameters)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class _Connection(sqlite3.Connection):
    def cursor(self):
        return super().cursor(factory=_Cursor)


@pytest.fixture
def database():
    connection = sqlite3.connect(":memory:", factory=_Connection)
    connection.row_factory = lambda cursor, values: {
        column[0]: value for column, value in zip(cursor.description, values)
    }
    connection.executescript("""
        CREATE TABLE orders (case_no TEXT, client_id INTEGER);
        CREATE TABLE clients (id INTEGER, name TEXT);
        CREATE TABLE beclass_records (
            id INTEGER PRIMARY KEY, query_no TEXT, refund_account_no TEXT
        );
        CREATE TABLE client_obligations (
            obligation_identity TEXT, case_no TEXT, direction TEXT,
            obligation_type TEXT, status TEXT, amount_due_ntd INTEGER, due_date TEXT
        );
        CREATE TABLE client_refund_recipient_snapshots (
            refund_obligation_identity TEXT, case_no TEXT, bank_account TEXT
        );
        CREATE TABLE staff_bank_accounts (id INTEGER, staff_id INTEGER, account_no TEXT);
        CREATE TABLE finance_import_rows (id INTEGER, bank_references TEXT);
    """)
    yield connection
    connection.close()


def _add_refund(database, refund_type, *, case_no="synthetic-case-1", client_id=7,
                snapshot=True):
    identity = f"{refund_type}:{case_no}"
    database.execute("INSERT INTO orders VALUES (?, ?)", (case_no, client_id))
    database.execute(
        "INSERT INTO beclass_records (query_no, refund_account_no) VALUES (?, ?)",
        (case_no, SNAPSHOT_ACCOUNT),
    )
    database.execute(
        "INSERT INTO client_obligations VALUES (?, ?, ?, ?, ?, ?, ?)",
        (identity, case_no, "payable_to_client", refund_type, "open", 1000, "2026-10-15"),
    )
    if snapshot:
        database.execute(
            "INSERT INTO client_refund_recipient_snapshots VALUES (?, ?, ?)",
            (identity, case_no, SNAPSHOT_ACCOUNT),
        )
    return identity


def _bank_row(monkeypatch, database, account=SNAPSHOT_ACCOUNT):
    frame = pd.DataFrame([
        list(taishin.TAISHIN_HEADERS),
        ["1", "2026/10/01", "09:00:00", "2026/10/01", "轉帳",
         "1000", "", "9000", account],
    ], dtype=object)
    monkeypatch.setattr(taishin.pd, "read_excel", lambda *_args, **_kwargs: frame)
    [row] = taishin.normalize_taishin_rows("synthetic-only.xlsx", "synthetic", 1)
    database.execute(
        "INSERT INTO finance_import_rows VALUES (?, ?)",
        (1, json.dumps(row["bank_references"])),
    )
    return row


def _classify(database, row):
    with database.cursor() as cursor:
        identities = load_finance_identity_maps(cursor)
    return classify_finance_transaction(row, **identities)


def _resolve(database, row, decision):
    candidate = CanonicalFinanceImportRow(
        "finance-import-row:1",
        0,
        MoneyNTD(int(row["debit"])),
        FinanceClassificationType(decision["classification_type"]),
        FinanceImportDisposition.BUSINESS_PENDING,
        PreviewFingerprint("a" * 64),
        tuple(f"client:{identity}" for identity in decision["matched_identity_ids"]),
    )
    return MySqlFinanceImportOwningDomainComposite(database).resolve(candidate)


@pytest.mark.parametrize("refund_type", REFUND_TYPES)
@pytest.mark.parametrize("profile_changed", (False, True))
def test_snapshot_outflow_resolves_without_bank_case_reference(
    monkeypatch, database, refund_type, profile_changed
):
    identity = _add_refund(database, refund_type)
    if profile_changed:
        database.execute(
            "UPDATE beclass_records SET refund_account_no=?",
            (CHANGED_PROFILE_ACCOUNT,),
        )
    row = _bank_row(monkeypatch, database)
    assert row["counterparty_name"] is None
    assert row["bank_references"] == {"sequence": "1"}

    decision = _classify(database, row)

    assert decision["classification_type"] == (
        "client_refund" if refund_type == "refund" else "client_subsidy_return"
    )
    assert decision["matched_identity_ids"] == [7]
    resolved = _resolve(database, row, decision)
    assert resolved.disposition is FinanceImportDisposition.CREATE
    assert resolved.target_identities == (identity,)
    assert resolved.integrity_violations == ()


@pytest.mark.parametrize("refund_type", REFUND_TYPES)
def test_missing_snapshot_does_not_fall_back_to_profile_account(
    monkeypatch, database, refund_type
):
    _add_refund(database, refund_type, snapshot=False)
    decision = _classify(database, _bank_row(monkeypatch, database))

    assert decision["classification_type"] == "non_business_review"
    assert decision["matched_identity_ids"] == []


@pytest.mark.parametrize("refund_type", REFUND_TYPES)
def test_changed_profile_account_cannot_replace_frozen_recipient(
    monkeypatch, database, refund_type
):
    _add_refund(database, refund_type)
    database.execute(
        "UPDATE beclass_records SET refund_account_no=?", (CHANGED_PROFILE_ACCOUNT,)
    )
    decision = _classify(
        database, _bank_row(monkeypatch, database, CHANGED_PROFILE_ACCOUNT)
    )

    assert decision["classification_type"] == "non_business_review"
    assert decision["matched_identity_ids"] == []


@pytest.mark.parametrize("refund_type", REFUND_TYPES)
def test_shared_snapshot_account_keeps_client_identity_ambiguous(
    monkeypatch, database, refund_type
):
    _add_refund(database, refund_type)
    _add_refund(database, refund_type, case_no="synthetic-case-2", client_id=8)
    decision = _classify(database, _bank_row(monkeypatch, database))

    assert decision["classification_type"] == "non_business_review"
    assert decision["matched_identity_ids"] == []


@pytest.mark.parametrize("refund_type", REFUND_TYPES)
def test_multiple_matching_cases_stay_pending_without_guessing(
    monkeypatch, database, refund_type
):
    _add_refund(database, refund_type)
    _add_refund(database, refund_type, case_no="synthetic-case-2")
    row = _bank_row(monkeypatch, database)
    decision = _classify(database, row)

    assert decision["matched_identity_ids"] == [7]
    resolved = _resolve(database, row, decision)
    assert resolved.disposition is FinanceImportDisposition.BUSINESS_PENDING
    assert resolved.target_identities == ("client:7",)
