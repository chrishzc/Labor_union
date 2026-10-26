from datetime import date, timedelta
from dataclasses import replace

import pytest

from domains.bootstrap.case_architecture import (
    BootstrapPresence,
    CaseArchitectureBootstrapFacts,
    CaseArchitectureBootstrapIntent,
    CaseRootFacts,
    ClientPaymentTermsRootFacts,
    PayrollPolicyKind,
    RatePolicyFacts,
    build_case_architecture_bootstrap_candidate,
    payroll_policy_kind_for_case,
)
from infrastructure.mysql.case_architecture_bootstrap_repository import _order_facts
from shared_kernel.money import MoneyNTD


@pytest.mark.parametrize(
    ("identity", "deposit_days"),
    (("補助市民", 5), ("社福", 0), ("非市民", 5)),
)
def test_twins_override_every_identity_policy(identity, deposit_days):
    candidate = _candidate(identity, deposit_days, "雙胞胎", PayrollPolicyKind.TWINS)

    assert candidate.payroll_rate_policy.policy_kind is PayrollPolicyKind.TWINS
    assert candidate.payroll_rate_policy.hourly_rate == MoneyNTD(450)


@pytest.mark.parametrize(
    ("identity", "expected"),
    (("補助市民", PayrollPolicyKind.CITIZEN), ("社福", PayrollPolicyKind.SUBSIDIZED_CITIZEN), ("非市民", PayrollPolicyKind.NON_CITIZEN)),
)
def test_non_twins_keep_identity_policy(identity, expected):
    assert payroll_policy_kind_for_case(identity, None) is expected


def test_twin_fact_changes_bootstrap_fingerprint():
    twins = _candidate("補助市民", 5, "雙胞胎", PayrollPolicyKind.TWINS)
    singleton = _candidate("補助市民", 5, None, PayrollPolicyKind.CITIZEN)

    assert twins.fingerprint != singleton.fingerprint


def test_mysql_bootstrap_uses_case_import_multi_birth_projection():
    facts = _order_facts({
        "case_no": "CASE-1", "lifecycle_version": 0,
        "start_date": date(2026, 1, 1), "service_days": 5,
        "service_hours_per_day": 8, "identity_status": "補助市民",
        "survey_details": {"特殊計費:胎數": "雙胞胎"},
    })

    assert facts.multi_birth_count == "雙胞胎"
    assert payroll_policy_kind_for_case(
        facts.source_identity_status, facts.multi_birth_count
    ) is PayrollPolicyKind.TWINS


@pytest.mark.parametrize("days,identity,deposit,fee,hours,expected", [
    (30, "補助市民", 5, 0, 8, date(2026, 11, 16)),
    (20, "補助市民", 5, 0, 8, None),
    (30, "社福", 0, 0, 8, date(2026, 11, 16)),
    (30, "社福", 0, 0, 1, None),
    (30, "社福", 0, 1000, 1, date(2026, 11, 16)),
])
def test_bootstrap_saves_owner_calculated_second_due_date(days, identity, deposit, fee, hours, expected):
    first = date(2026, 11, 1)
    kind = PayrollPolicyKind.CITIZEN if identity == "補助市民" else PayrollPolicyKind.SUBSIDIZED_CITIZEN
    rate = 300 if kind is PayrollPolicyKind.CITIZEN else 350
    facts = CaseArchitectureBootstrapFacts(
        CaseRootFacts("CASE-DATE", 0, first, days, hours, identity, floor_fee=MoneyNTD(fee)),
        RatePolicyFacts("approved-rates-v1", kind, MoneyNTD(rate), date(1900, 1, 1), None),
        BootstrapPresence(),
    )
    intent = CaseArchitectureBootstrapIntent(
        "CASE-DATE", ClientPaymentTermsRootFacts(
            "client-v1", MoneyNTD(rate), deposit, first - timedelta(days=16), first,
        ), "approved-rates-v1",
    )
    candidate = build_case_architecture_bootstrap_candidate(facts, intent)
    assert candidate.client_payment_terms.second_payment_due_date == expected
    wrong = replace(intent, client_payment_terms=replace(
        intent.client_payment_terms, second_payment_due_date=date(2020, 1, 1),
    ))
    assert build_case_architecture_bootstrap_candidate(facts, wrong).fingerprint == candidate.fingerprint


def _candidate(identity, deposit_days, multi_birth_count, policy_kind):
    rate = 450 if policy_kind is PayrollPolicyKind.TWINS else {
        PayrollPolicyKind.CITIZEN: 300,
        PayrollPolicyKind.SUBSIDIZED_CITIZEN: 350,
        PayrollPolicyKind.NON_CITIZEN: 320,
    }[policy_kind]
    facts = CaseArchitectureBootstrapFacts(
        CaseRootFacts("CASE-1", 0, date(2026, 1, 1), 5, 8, identity, multi_birth_count),
        RatePolicyFacts("approved-rates-v1", policy_kind, MoneyNTD(rate), date(1900, 1, 1), None),
        BootstrapPresence(),
    )
    intent = CaseArchitectureBootstrapIntent(
        "CASE-1",
        ClientPaymentTermsRootFacts("client-v1", MoneyNTD(320), deposit_days, date(2025, 12, 27), date(2026, 1, 1)),
        "approved-rates-v1",
    )
    return build_case_architecture_bootstrap_candidate(facts, intent)


@pytest.mark.parametrize("correction", [{"multi_birth_count": "雙胞胎"}, '{"multi_birth_count":"雙胞胎"}'])
def test_later_bootstrap_uses_saved_birth_correction_instead_of_original_survey(correction):
    facts = _order_facts({
        "case_no": "CASE-1", "lifecycle_version": 0,
        "start_date": date(2026, 1, 1), "service_days": 5,
        "service_hours_per_day": 8, "identity_status": "補助市民",
        "survey_details": {"特殊計費:胎數": "單胞胎"}, "effective_values_json": correction,
    })
    assert facts.multi_birth_count == "雙胞胎"
    assert payroll_policy_kind_for_case(facts.source_identity_status, facts.multi_birth_count) is PayrollPolicyKind.TWINS
