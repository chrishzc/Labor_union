"""Verify workbook memo case scoping through classification and owner resolution."""

from datetime import date
import json

import pandas as pd
import pytest

from domains.client_finance.client_refund_reversal import ClientRefundPurpose
from domains.finance_import.ingestion import InitialClassificationFacts, build_initial_classification
from domains.finance_import.planning import CanonicalFinanceImportRow, FinanceImportDisposition
from domains.finance_import.transaction_classifier import classify_finance_transaction
from infrastructure.mysql.client_refund_reversal_repository import _refund_bank_facts
from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
from scripts.imports.finance_formats.sinopac import SINOPAC_HEADERS
from scripts.imports.finance_statement_normalizer import normalize_workbook
from shared_kernel.money import MoneyNTD


class _CaseCursor:
    def __init__(self, bank, obligations, mappings=(), cases=("115000001",)):
        self.bank = bank
        self.obligations = obligations
        self.mappings = mappings
        self.cases = cases
        self.executions = []
        self.current = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        sql = " ".join(sql.split())
        self.executions.append((sql, params))
        if "FROM finance_import_rows WHERE id=" in sql:
            self.current = self.bank
        elif "FROM client_legacy_virtual_accounts" in sql:
            self.current = tuple({"case_no": value} for value in self.mappings)
        elif "FROM orders WHERE case_no" in sql:
            self.current = tuple({"case_no": value} for value in self.cases if value == params[0])
        elif "FROM client_obligations obligation" in sql or "FROM staff_obligations obligation" in sql:
            self.current = tuple(
                row for row in self.obligations
                if row["owner_id"] == params[0]
                and ("AND obligation.case_no=%s" not in sql or row["case_no"] == params[1])
            )
        else:
            raise AssertionError("Unexpected SQL in memo resolution")

    def fetchone(self):
        return self.current

    def fetchall(self):
        return self.current


class _CaseConnection:
    def __init__(self, *args, **kwargs):
        self.cursor_instance = _CaseCursor(*args, **kwargs)

    def cursor(self):
        return self.cursor_instance


def _workbook_row(tmp_path, memo):
    values = dict.fromkeys(SINOPAC_HEADERS)
    values.update({
        "帳號": "10000001", "交易日": "2026-10-20", "計息日": "2026-10-20",
        "入帳日": "2026-10-20", "幣別": "TWD", "摘要": "轉帳",
        "支出": 12000, "存入": 0, "餘額": 1000, "備註": memo,
        "交易參考編號": "10001", "存摺備註": "HC115999其他案件",
        "更正註記": "Y",
    })
    path = tmp_path / "memo-case.xlsx"
    pd.DataFrame([values], columns=SINOPAC_HEADERS).to_excel(path, index=False)
    return normalize_workbook(path)["normalized_rows"][0]


def _pending(row, kind):
    decision = classify_finance_transaction(
        row, {"10001": [7]} if kind == "refund" else {},
        {"10001": [7]} if kind == "staff" else {}, {},
    )
    assert decision["classification_type"] == ("client_refund" if kind == "refund" else "staff_salary")
    initial = build_initial_classification(InitialClassificationFacts(
        97, decision["classification_type"], tuple(decision["matched_identity_ids"]), decision["reason"],
    ))
    return CanonicalFinanceImportRow(
        "finance-import-row:97", 0, MoneyNTD(12000), initial.classification_type,
        initial.disposition, initial.decision_facts_fingerprint,
        initial.target_identities, initial.evidence, initial.available_actions,
    )


def _obligation(case_no, identity, owner_id=7):
    return {"case_no": case_no, "obligation_identity": identity, "owner_id": owner_id,
            "amount_due_ntd": 12000, "balance_ntd": 12000}


@pytest.mark.parametrize("memo", ["HC115001服務人員", "A115001服務人員", "HC115001退款"])
@pytest.mark.parametrize("kind", ["refund", "staff"])
def test_workbook_memo_selects_only_that_case_for_refunds_and_staff_payouts(tmp_path, memo, kind):
    row = _workbook_row(tmp_path, memo)
    candidate = _pending(row, kind)
    connection = _CaseConnection(row, (
        _obligation("115000001", kind + ":selected"),
        _obligation("115000002", kind + ":other-case"),
    ))

    result = MySqlFinanceImportOwningDomainComposite(connection).resolve(candidate)

    assert result.disposition is FinanceImportDisposition.CREATE
    assert result.target_identities == (kind + ":selected",)
    target_sql, params = connection.cursor_instance.executions[-1]
    assert "AND obligation.case_no=%s" in target_sql
    assert params == (7, "115000001")
    assert row["memo"] == memo
    assert row["raw_payload"]["備註"] == memo
    if kind == "refund":
        facts = _refund_bank_facts(({
            **row, "id": 97, "transaction_date": date(2026, 10, 20),
            "effective_classification_type": "client_refund", "reconciliation_status": "pending",
            "resolved_counterparty_account": None, "ledger_entry_id": None,
        },), "115000001", ClientRefundPurpose.CUSTOMER_REFUND, "10001")
        assert len(facts) == 1 and facts[0].eligible is True


@pytest.mark.parametrize("kind", ["refund", "staff"])
def test_memo_case_uses_imported_mapping_instead_of_a_formula_guess(tmp_path, kind):
    row = _workbook_row(tmp_path, "HC115001退款")
    connection = _CaseConnection(row, (
        _obligation("114000018", "selected"), _obligation("115000001", "wrong-formula"),
    ), mappings=("114000018",))
    result = MySqlFinanceImportOwningDomainComposite(connection).resolve(_pending(row, kind))
    assert result.target_identities == ("selected",)
    assert not any("FROM orders" in sql for sql, _ in connection.cursor_instance.executions)


@pytest.mark.parametrize("kind", ["refund", "staff"])
@pytest.mark.parametrize("memo", [None, "", "HC11500", "HC1150010", "HC115001 HC115002"])
def test_missing_or_ambiguous_memo_never_falls_back_to_passbook_or_all_cases(tmp_path, kind, memo):
    row = _workbook_row(tmp_path, memo)
    candidate = _pending(row, kind)
    connection = _CaseConnection(row, (_obligation("115000001", "must-not-select"),))
    assert MySqlFinanceImportOwningDomainComposite(connection).resolve(candidate) == candidate
    assert len(connection.cursor_instance.executions) == 1


@pytest.mark.parametrize("kind", ["refund", "staff"])
@pytest.mark.parametrize("mappings,cases", [((), ()), (("115000001", "115000002"), ("115000001",))])
def test_unknown_or_nonunique_case_remains_pending(tmp_path, kind, mappings, cases):
    row = _workbook_row(tmp_path, "A115001服務人員")
    candidate = _pending(row, kind)
    connection = _CaseConnection(row, (_obligation("115000001", "must-not-select"),), mappings, cases)
    assert MySqlFinanceImportOwningDomainComposite(connection).resolve(candidate) == candidate


@pytest.mark.parametrize("kind", ["refund", "staff"])
def test_memo_case_without_an_obligation_for_the_counterparty_stays_pending(tmp_path, kind):
    row = _workbook_row(tmp_path, "HC115001退款")
    candidate = _pending(row, kind)
    connection = _CaseConnection(row, (
        _obligation("115000001", "different-person", owner_id=8),
        _obligation("115000002", "same-person-wrong-case"),
    ))
    assert MySqlFinanceImportOwningDomainComposite(connection).resolve(candidate) == candidate


@pytest.mark.parametrize("json_references", [False, True])
def test_refund_does_not_use_cached_or_memo_account_when_bank_reference_conflicts(tmp_path, json_references):
    row = _workbook_row(tmp_path, "HC115001退款")
    if json_references:
        row["bank_references"] = json.dumps(row["bank_references"])
    facts = _refund_bank_facts(({
        **row, "id": 97, "transaction_date": date(2026, 10, 20),
        "effective_classification_type": "client_refund", "reconciliation_status": "pending",
        "resolved_counterparty_account": "different-account", "ledger_entry_id": None,
    },), "115000001", ClientRefundPurpose.CUSTOMER_REFUND, "different-account")
    assert facts[0].eligible is False


@pytest.mark.parametrize(("kind", "format_id"), [("refund", "taishin"), ("staff", "legacy")])
def test_other_bank_formats_keep_existing_resolution_without_a_memo_case(tmp_path, kind, format_id):
    row = _workbook_row(tmp_path, "HC115001退款")
    candidate = _pending(row, kind)
    source = {**row, "format_id": format_id, "memo": None}
    connection = _CaseConnection(source, (_obligation("115000001", "existing-target"),))
    result = MySqlFinanceImportOwningDomainComposite(connection).resolve(candidate)
    assert result.target_identities == ("existing-target",)
    target_sql, parameters = connection.cursor_instance.executions[-1]
    assert "AND obligation.case_no=%s" not in target_sql
    assert parameters == (7,)


def test_shared_refund_and_staff_account_is_not_resolved_by_memo_label(tmp_path):
    row = _workbook_row(tmp_path, "HC115001退款")
    decision = classify_finance_transaction(row, {"10001": [7]}, {"10001": [8]}, {})
    assert decision["classification_type"] == "non_business_review"
    assert decision["reason"] == "counterparty_identity_type_conflict"
