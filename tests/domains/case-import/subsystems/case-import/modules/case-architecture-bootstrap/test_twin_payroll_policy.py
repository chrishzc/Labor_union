from datetime import date

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
    (("一般市民", 5), ("補助市民", 0), ("非市民", 5)),
)
def test_twins_override_every_identity_policy(identity, deposit_days):
    candidate = _candidate(identity, deposit_days, "雙胞胎", PayrollPolicyKind.TWINS)

    assert candidate.payroll_rate_policy.policy_kind is PayrollPolicyKind.TWINS
    assert candidate.payroll_rate_policy.hourly_rate == MoneyNTD(450)


@pytest.mark.parametrize(
    ("identity", "expected"),
    (("一般市民", PayrollPolicyKind.CITIZEN), ("補助市民", PayrollPolicyKind.SUBSIDIZED_CITIZEN), ("非市民", PayrollPolicyKind.NON_CITIZEN)),
)
def test_non_twins_keep_identity_policy(identity, expected):
    assert payroll_policy_kind_for_case(identity, None) is expected


def test_twin_fact_changes_bootstrap_fingerprint():
    twins = _candidate("一般市民", 5, "雙胞胎", PayrollPolicyKind.TWINS)
    singleton = _candidate("一般市民", 5, None, PayrollPolicyKind.CITIZEN)

    assert twins.fingerprint != singleton.fingerprint


def test_mysql_bootstrap_uses_case_import_multi_birth_projection():
    facts = _order_facts({
        "case_no": "CASE-1", "lifecycle_version": 0,
        "start_date": date(2026, 1, 1), "service_days": 5,
        "service_hours_per_day": 8, "identity_status": "一般市民",
        "survey_details": {"特殊計費:胎數": "雙胞胎"},
    })

    assert facts.multi_birth_count == "雙胞胎"
    assert payroll_policy_kind_for_case(
        facts.source_identity_status, facts.multi_birth_count
    ) is PayrollPolicyKind.TWINS


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
