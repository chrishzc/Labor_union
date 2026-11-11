"""
File: pricing_configuration_repository.py
Description: 管理 MySQL 帳務計價政策、個案覆寫與歷史案件重算計畫持久化。
"""

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
from zoneinfo import ZoneInfo

from domains.client_finance.pricing_policy import CasePricingTerms, HourlyRates, IdentityRule, PricingPolicy
from domains.client_finance.subsidy_coverage import normalize_subsidy_policy_identity
from domains.payroll.tiered_rates import TieredPayrollRate
from infrastructure.mysql.case_category_query import BOUND_POLICY_IDENTITY_SQL
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.client_finance.pricing_configuration import (
    CasePricingFacts, PolicyVersion, PricingCatalog, PricingConflict, PricingServiceDay, pricing_impact, pricing_payload,
    HistoricalAmountFacts, build_historical_repricing_plan,
)


# Source-owned read projection replaces the two runtime uses of the old SQL view.
# Its column contract is unchanged; released schema artifacts and stored snapshots remain intact.
CASE_PRICING_FACTS_SQL = f"""SELECT o.case_no,1 AS pricing_active,
 (e.id IS NOT NULL) AS pricing_override_active,
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(e.pricing_json,'$.rule')),i.rule_name) AS pricing_rule,
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(e.pricing_json,'$.subsidy_hours')),i.subsidy_hours) AS pricing_subsidy_hours,
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(e.pricing_json,'$.client.covered')),i.client_covered) AS pricing_client_covered,
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(e.pricing_json,'$.client.excess')),i.client_excess) AS pricing_client_excess,
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(e.pricing_json,'$.payroll.covered')),i.payroll_covered) AS pricing_payroll_covered,
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(e.pricing_json,'$.payroll.excess')),i.payroll_excess) AS pricing_payroll_excess,
 COALESCE(JSON_UNQUOTE(JSON_EXTRACT(e.pricing_json,'$.payroll.covered')),
          JSON_UNQUOTE(JSON_EXTRACT(p.policy_json,'$.twins_payroll.covered'))) AS pricing_twins_payroll_covered
FROM orders o JOIN clients c ON c.id=o.client_id
LEFT JOIN accounting_pricing_policies p ON p.id=o.pricing_policy_id
LEFT JOIN JSON_TABLE(p.policy_json,'$.identities[*]' COLUMNS (
 identity_name VARCHAR(100) PATH '$.identity_name', rule_name VARCHAR(20) PATH '$.rule',
 subsidy_hours VARCHAR(100) PATH '$.subsidy_hours', client_covered VARCHAR(30) PATH '$.client.covered',
 client_excess VARCHAR(30) PATH '$.client.excess', payroll_covered VARCHAR(30) PATH '$.payroll.covered',
 payroll_excess VARCHAR(30) PATH '$.payroll.excess'
)) i ON BINARY i.identity_name=BINARY {BOUND_POLICY_IDENTITY_SQL}
LEFT JOIN case_pricing_events e ON e.id=o.pricing_override_event_id AND e.case_no=o.case_no
WHERE o.pricing_policy_id IS NOT NULL OR o.pricing_override_event_id IS NOT NULL"""


def _object(value):
    return value if isinstance(value, dict) else json.loads(value)


def terms_from_payload(value):
    value = _object(value)
    return CasePricingTerms(value["identity_name"], IdentityRule(value["rule"]), Decimal(str(value["subsidy_hours"])),
        HourlyRates(**value["client"]), HourlyRates(**value["payroll"]), value.get("deposit_service_days"))


def policy_from_payload(value):
    value = _object(value)
    return PricingPolicy(date.fromisoformat(value["effective_on"]), tuple(terms_from_payload(item) for item in value["identities"]),
        HourlyRates(**value["twins_client"]), HourlyRates(**value["twins_payroll"]),
        value.get("indigenous_deposit_service_days"))


def _json(value):
    return json.dumps(pricing_payload(value), ensure_ascii=False, sort_keys=True)


def select_initial_pricing(cursor):
    today = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Taipei")).date()
    cursor.execute("SELECT id,policy_json FROM accounting_pricing_policies WHERE effective_on<=%s ORDER BY effective_on DESC,id DESC LIMIT 1", (today,))
    return cursor.fetchone()


def bind_initial_pricing(cursor, case_no, *, policy_id=None):
    """Called only immediately after first Orders insertion, including partial intake."""
    if policy_id is None:
        row = select_initial_pricing(cursor)
    else:
        cursor.execute("SELECT id,policy_json FROM accounting_pricing_policies WHERE id=%s", (policy_id,))
        row = cursor.fetchone()
    if row is not None:
        policy = policy_from_payload(row["policy_json"])
        if policy.uses_legacy_identity_names:
            cursor.execute("SELECT c.identity_status FROM orders o JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s", (case_no,))
            case = cursor.fetchone()
            if case and case["identity_status"] in {
                "一般市民", "補助市民", "社福", "低收入戶", "中低收入戶", "原住民", "原民", "原住民市民",
            }:
                from domains.case_import.case_import import CaseImportDomainError, CaseImportIssue
                raise CaseImportDomainError(CaseImportIssue.BOOTSTRAP_BLOCKED,
                    "pricing_policy_identity_names_outdated: 請先在帳務參數設定儲存一般市民／補助市民的新政策版本。")
        cursor.execute("UPDATE orders SET pricing_policy_id=%s WHERE case_no=%s AND pricing_policy_id IS NULL", (row["id"], case_no))


def initial_identity_rule(cursor, identity, case_no=None):
    """Resolve only declared new identities; a pre-existing binding wins over today."""
    if not identity or identity in {"一般市民", "補助市民", "社福", "低收入戶", "中低收入戶", "非市民"}:
        return None
    normalized_identity = normalize_subsidy_policy_identity(identity)
    if case_no is not None:
        cursor.execute("SELECT pricing_policy_id FROM orders WHERE case_no=%s", (case_no,))
        case = cursor.fetchone()
        if case is not None:
            if case["pricing_policy_id"] is None:
                return None
            cursor.execute("SELECT policy_json FROM accounting_pricing_policies WHERE id=%s", (case["pricing_policy_id"],))
            row = cursor.fetchone()
            if not row:
                return None
            policy = policy_from_payload(row["policy_json"])
            return policy.for_case(normalized_identity).rule.value if any(
                item.identity_name == normalized_identity for item in policy.identities
            ) else None
    today = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Taipei")).date()
    cursor.execute("SELECT policy_json FROM accounting_pricing_policies WHERE effective_on<=%s ORDER BY effective_on DESC,id DESC LIMIT 1", (today,))
    row = cursor.fetchone()
    if row is None:
        return None
    policy = policy_from_payload(row["policy_json"])
    item = next((item for item in policy.identities if item.identity_name == normalized_identity), None)
    return item.rule.value if item else None


def _legacy_rule_and_cap(identity_status: str) -> tuple[IdentityRule, Decimal]:
    canonical = normalize_subsidy_policy_identity(identity_status)
    mapping = {
        "一般市民": (IdentityRule.CITIZEN, Decimal(40)),
        "補助市民": (IdentityRule.SOCIAL, Decimal(120)),
        "原住民": (IdentityRule.CITIZEN, Decimal(80)),
        "非市民": (IdentityRule.NON_CITIZEN, Decimal(0)),
    }
    resolved = mapping.get(canonical)
    if resolved is None:
        raise ValueError("case_pricing_identity_not_confirmed")
    return resolved


def _is_twins(cursor, case_no, lock):
    from infrastructure.mysql.case_architecture_bootstrap_repository import _effective_multi_birth_count
    cursor.execute("SELECT b.survey_details,s.effective_values_json FROM beclass_records b "
        "LEFT JOIN beclass_record_correction_states s ON s.beclass_record_id=b.id "
        "WHERE b.bound_case_no=%s ORDER BY b.id LIMIT 2" + (" FOR UPDATE" if lock else ""), (case_no,))
    rows = tuple(cursor.fetchall())
    if len(rows) > 1:
        raise ValueError("case_pricing_birth_source_ambiguous")
    return bool(rows and _effective_multi_birth_count(rows[0]) == "雙胞胎")


def load_case_pricing(cursor, order_row, *, lock=False):
    """No write or latest-policy lookup: only the case's original immutable binding."""
    event_id = order_row.get("pricing_override_event_id")
    policy_id = order_row.get("pricing_policy_id")
    identity = order_row.get("client_identity_status", order_row.get("identity_status"))
    suffix = " FOR UPDATE" if lock else ""
    if event_id is not None:
        cursor.execute("SELECT pricing_json FROM case_pricing_events WHERE id=%s AND case_no=%s" + suffix,
            (event_id, order_row["case_no"]))
        row = cursor.fetchone()
        if row is None:
            raise ValueError("case_pricing_override_missing")
        override = terms_from_payload(row["pricing_json"])
        if policy_id is None:
            return override
    if policy_id is None:
        return None
    cursor.execute("SELECT policy_json FROM accounting_pricing_policies WHERE id=%s" + suffix, (policy_id,))
    row = cursor.fetchone()
    if row is None:
        raise ValueError("case_pricing_bound_policy_missing")
    policy = policy_from_payload(row["policy_json"])
    if event_id is not None:
        return replace(override, deposit_service_days=policy.for_case(str(identity)).deposit_service_days)
    return policy.for_case(str(identity), twins=_is_twins(cursor, order_row["case_no"], lock))


def payroll_tiers(terms):
    return TieredPayrollRate(terms.payroll.covered, terms.payroll.excess, terms.subsidy_hours, terms.rule is IdentityRule.SOCIAL)


def citizen_reclassification_terms(cursor, order_row, *, lock=False):
    from domains.client_finance.subsidy_coverage import default_subsidy_hour_cap, derive_subsidy_coverage

    citizen = "一般市民"
    terms = load_case_pricing(
        cursor,
        {**order_row, "client_identity_status": citizen, "pricing_override_event_id": None},
        lock=lock,
    )
    if terms is not None:
        return replace(terms, identity_name=citizen)
    coverage = derive_subsidy_coverage(citizen, Decimal(0), Decimal(0))
    hourly = 450 if _is_twins(cursor, order_row["case_no"], lock) else int(coverage.subsidy_claim_hourly_rate)
    rates = HourlyRates(hourly, hourly)
    return CasePricingTerms(citizen, IdentityRule.CITIZEN, default_subsidy_hour_cap(citizen), rates, rates, 5)


def load_historical_pricing_facts(connection, case_no, *, lock=False, order=None):
    """Borrow confirmed historical volume, without manufacturing calendar days."""
    from infrastructure.mysql.order_terms_read_model import select_order
    from infrastructure.mysql.historical_service_accounting_repository import MySqlHistoricalServiceAccountingRepository
    with connection.cursor() as cursor:
        order = order if order is not None else select_order(cursor, case_no, lock=lock)
        if str(order['status']) not in ('歷史訂單－服務完成', '歷史訂單－帳務完成'):
            return None
        source = MySqlHistoricalServiceAccountingRepository(connection).load(case_no, for_update=lock)
        if len(source.assignments) != 1:
            raise PricingConflict('historical_pricing_unique_assignment_required')
        cursor.execute('SELECT actual_service_days FROM historical_service_day_items WHERE event_id='
            '(SELECT MAX(id) FROM historical_service_day_events WHERE case_no=%s)', (case_no,))
        items = cursor.fetchall()
        days = sum(int(item['actual_service_days']) for item in items) if items else source.contracted_service_days
        hours = Decimal(days) * Decimal(source.service_hours_per_day)
        floor = int((Decimal(source.contractual_floor_fee.amount) * days / source.contracted_service_days).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        terms = load_case_pricing(cursor, order, lock=lock)
        if terms is None:
            rule, cap = _legacy_rule_and_cap(source.client_identity_status)
            staff_rate = source.assignments[0].rate_snapshot.hourly_rate.amount
            terms = CasePricingTerms(source.client_identity_status, rule, cap,
                HourlyRates(source.client_hourly_rate.amount, source.client_hourly_rate.amount), HourlyRates(staff_rate, staff_rate))
        cursor.execute('SELECT aggregate_version FROM scheduling_aggregates WHERE case_no=%s' + (' FOR UPDATE' if lock else ''), (case_no,))
        scheduling = cursor.fetchone()
    return CasePricingFacts(case_no, int(order.get('pricing_revision', 0)),
        (source.lifecycle_version, source.client_finance_version, source.payroll_version,
         int(scheduling['aggregate_version']) if scheduling else -1, source.historical_day_revision, source.adoption_receipt_id),
        terms, 'manual' if order.get('pricing_override_event_id') else 'policy' if order.get('pricing_policy_id') else 'legacy',
        (), floor, source.assignments[0].effective_adjustment.amount, None, hours)


def historical_repricing_plan(connection, facts, terms, *, floor_fee=None, lock=True):
    """Apply a price delta to evidenced original installments, never regenerate them."""
    suffix = ' FOR UPDATE' if lock else ''
    with connection.cursor() as cursor:
        cursor.execute('SELECT o.obligation_identity,o.obligation_type,e.after_amount_ntd nominal,c.amount_mode,c.computed_ntd,c.effective_ntd '
            'FROM client_obligations o JOIN client_obligation_events e ON e.id=o.current_event_id '
            'LEFT JOIN client_finance_amount_controls c ON c.obligation_identity=o.obligation_identity '
            "WHERE o.case_no=%s AND o.status<>'cancelled' AND o.source_obligation_identity IS NULL "
            "AND o.obligation_type IN ('deposit','first','second') ORDER BY FIELD(o.obligation_type,'deposit','first','second')" + suffix, (facts.case_no,))
        client_rows = cursor.fetchall()
        if not client_rows or len({r['obligation_type'] for r in client_rows}) != len(client_rows):
            raise PricingConflict('historical_pricing_original_installments_required')
        cursor.execute('SELECT o.obligation_identity,e.after_amount_ntd nominal,c.amount_mode,c.computed_ntd,c.effective_ntd '
            'FROM staff_obligations o JOIN staff_obligation_events e ON e.id=o.current_event_id '
            'LEFT JOIN payroll_amount_controls c ON c.obligation_identity=o.obligation_identity '
            "WHERE o.case_no=%s AND o.status<>'cancelled' AND o.obligation_kind='service_pay' AND o.direction='payable_to_staff'" + suffix, (facts.case_no,))
        staff_rows = cursor.fetchall()
        if len(staff_rows) != 1:
            raise PricingConflict('historical_pricing_original_payable_required')
        cursor.execute('SELECT o.obligation_identity,e.after_amount_ntd nominal,c.amount_mode,c.computed_ntd,c.effective_ntd '
            'FROM client_obligations o JOIN client_obligation_events e ON e.id=o.current_event_id '
            'LEFT JOIN client_finance_amount_controls c ON c.obligation_identity=o.obligation_identity '
            "WHERE o.case_no=%s AND o.status<>'cancelled' AND o.obligation_type='subsidy_return' AND o.source_obligation_identity IS NULL" + suffix, (facts.case_no,))
        subsidy_rows = cursor.fetchall()
        if len(subsidy_rows) > 1:
            raise PricingConflict('historical_pricing_original_subsidy_return_required')
    def amounts(row):
        computed = int(row['computed_ntd'] if row['computed_ntd'] is not None else row['nominal'])
        effective = int(row['effective_ntd'] if row['effective_ntd'] is not None else row['nominal'])
        mode = row['amount_mode'] or 'automatic'
        return HistoricalAmountFacts(row['obligation_identity'],computed,effective,mode)
    return build_historical_repricing_plan(facts, terms, tuple(amounts(r) for r in client_rows), amounts(staff_rows[0]),
        floor_fee=floor_fee, subsidy_source=amounts(subsidy_rows[0]) if subsidy_rows else None)


def persist_historical_repricing(connection, plan, actor, reason, key):
    from infrastructure.mysql.client_difference_repository import persist_historical_source_amounts as client_apply
    from infrastructure.mysql.payroll_amount_correction_repository import persist_historical_source_amounts as staff_apply
    client_apply(connection, plan, actor, reason, key)
    staff_apply(connection, plan, actor, reason, key)


class MySqlPricingConfigurationRepository:
    def __init__(self, connection):
        self.connection = connection

    def catalog(self, *, lock=False):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT revision FROM accounting_pricing_state WHERE singleton_id=1" + (" FOR UPDATE" if lock else ""))
            state = cursor.fetchone()
            if state is None:
                raise ValueError("pricing_schema_not_initialized")
            cursor.execute("SELECT id,policy_json,actor,reason FROM accounting_pricing_policies ORDER BY id DESC")
            versions = tuple(PolicyVersion(int(row["id"]), policy_from_payload(row["policy_json"]), row["actor"], row["reason"]) for row in cursor.fetchall())
        return PricingCatalog(int(state["revision"]), versions)

    def receipt(self, key, actor, command_hash):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT actor,command_hash,result_json FROM accounting_pricing_receipts WHERE idempotency_key=%s", (key,))
            row = cursor.fetchone()
        if row is None:
            return None
        if row["actor"] != actor or row["command_hash"] != command_hash:
            raise PricingConflict("pricing_idempotency_conflict")
        return int(_object(row["result_json"])["revision"])

    def save_receipt(self, key, actor, command_hash, revision):
        with self.connection.cursor() as cursor:
            cursor.execute("INSERT INTO accounting_pricing_receipts(idempotency_key,command_hash,actor,result_json,created_at_utc) VALUES(%s,%s,%s,%s,UTC_TIMESTAMP(6))",
                (key, command_hash, actor, json.dumps({"revision": revision})))

    def save_policy(self, policy, revision, actor, reason):
        with self.connection.cursor() as cursor:
            cursor.execute("INSERT INTO accounting_pricing_policies(id,effective_on,policy_json,actor,reason,created_at_utc) VALUES(%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))",
                (revision, policy.effective_on, _json(policy), actor, reason))
            cursor.execute("UPDATE accounting_pricing_state SET revision=%s WHERE singleton_id=1 AND revision=%s", (revision, revision-1))
            if cursor.rowcount != 1:
                raise PricingConflict("pricing_policy_stale")

    def case(self, case_no, *, lock=False):
        from infrastructure.mysql.order_terms_read_model import load_calculable_client_finance_facts, select_order
        with self.connection.cursor() as cursor:
            order = select_order(cursor, case_no, lock=lock)
            historical = load_historical_pricing_facts(self.connection, case_no, lock=lock, order=order)
            if historical is not None:
                return historical
            from infrastructure.mysql.order_terms_read_model import load_locked_facts, load_preview_facts, preflight_staff_ids
            staff_ids = preflight_staff_ids(cursor, case_no)
            payroll_source = (load_locked_facts(cursor, case_no, staff_ids) if lock else load_preview_facts(cursor, case_no)) if staff_ids else None
            finance, _ = load_calculable_client_finance_facts(cursor, order, lock=lock)
            if finance is None:
                raise ValueError("case_pricing_service_facts_required")
            terms = load_case_pricing(cursor, order, lock=lock)
            legacy_amount = None
            if terms is None:
                terms = self._legacy_terms(cursor, order, finance)
                from domains.client_finance.obligation_planning import build_client_finance_terms_candidate
                legacy_amount = sum(stage.amount.amount for stage in build_client_finance_terms_candidate(finance, 'pricing-read').stage_plans)
            cursor.execute("SELECT aggregate_version FROM payroll_case_accounts WHERE case_no=%s" + (" FOR UPDATE" if lock else ""), (case_no,))
            payroll = cursor.fetchone()
            cursor.execute("SELECT aggregate_version FROM scheduling_aggregates WHERE case_no=%s" + (" FOR UPDATE" if lock else ""), (case_no,))
            scheduling = cursor.fetchone()
        return CasePricingFacts(case_no, int(order.get("pricing_revision", 0)),
            (int(order["lifecycle_version"]), finance.account_version, int(payroll["aggregate_version"]) if payroll else -1,
                int(scheduling["aggregate_version"]) if scheduling else -1), terms,
            "manual" if order.get("pricing_override_event_id") else "policy" if order.get("pricing_policy_id") else "legacy",
            tuple(PricingServiceDay(day.service_date, Decimal(str(finance.service_hours_per_day)), day.is_double_pay) for day in finance.charge_days),
            finance.floor_fee.amount,
            sum(item.adjustment_total.amount for item in payroll_source.payroll.source_terms) if payroll_source else 0,
            legacy_amount)

    def _legacy_terms(self, cursor, order, finance):
        from infrastructure.mysql.effective_case_service_rate import load_explicit_case_service_rate
        identity = str(order["client_identity_status"])
        rule, cap = _legacy_rule_and_cap(identity)
        cursor.execute("SELECT hourly_rate_ntd FROM case_payroll_rate_policy_snapshots WHERE case_no=%s", (order["case_no"],))
        salary = cursor.fetchone()
        if salary is None:
            raise ValueError("case_pricing_payroll_snapshot_required")
        correction = load_explicit_case_service_rate(cursor, order["case_no"])
        salary_rate = correction.hourly_rate_ntd if correction else int(salary["hourly_rate_ntd"])
        client_rate = finance.payment_terms.client_hourly_rate.amount
        return CasePricingTerms(identity, rule, cap, HourlyRates(client_rate, client_rate), HourlyRates(salary_rate, salary_rate))

    def save_case(self, facts, terms, actor, reason, key, *, identity_reclassification=False):
        from domains.client_finance.obligation_planning import build_client_finance_terms_candidate
        from infrastructure.mysql.client_finance_terms_writer import persist_client_finance_terms_impact
        from infrastructure.mysql.order_terms_read_model import load_calculable_client_finance_facts, select_order
        from subsystems.orders.terms_workflow import ClientFinanceImpactPersistenceCommand
        before, after = pricing_impact(facts.terms, facts), pricing_impact(terms, facts)
        with self.connection.cursor() as cursor:
            if not identity_reclassification and before.subsidy_amount != after.subsidy_amount:
                cursor.execute("SELECT m.receipt_id FROM government_subsidy_period_members m "
                    "JOIN government_subsidy_period_entries e ON e.id=m.receipt_id "
                    "WHERE m.case_no=%s AND e.reversal_of_id IS NULL AND NOT EXISTS "
                    "(SELECT 1 FROM government_subsidy_period_entries r WHERE r.reversal_of_id=e.id) LIMIT 1 FOR UPDATE", (facts.case_no,))
                if cursor.fetchone() is not None:
                    raise PricingConflict("case_pricing_settled_subsidy_correction_required")
                cursor.execute("SELECT i.id FROM subsidy_claim_batch_items i WHERE i.case_no=%s AND ("
                    "COALESCE((SELECT SUM(CASE WHEN a.allocation_type='receipt' THEN a.allocated_amount "
                    "WHEN a.allocation_type='reversal' THEN -a.allocated_amount ELSE 0 END) "
                    "FROM government_subsidy_allocations a WHERE a.claim_item_id=i.id),0)>0 "
                    "OR EXISTS(SELECT 1 FROM government_subsidy_overpayment_offsets x WHERE x.claim_item_id=i.id)) LIMIT 1 FOR UPDATE", (facts.case_no,))
                if cursor.fetchone() is not None:
                    raise PricingConflict("case_pricing_settled_subsidy_correction_required")
            cursor.execute("INSERT INTO case_pricing_events(case_no,resulting_revision,pricing_json,actor,reason,created_at_utc) VALUES(%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))",
                (facts.case_no, facts.revision+1, _json(terms), actor, reason))
            event_id = int(cursor.lastrowid)
            cursor.execute("UPDATE orders SET pricing_override_event_id=%s,pricing_revision=pricing_revision+1,lifecycle_version=lifecycle_version+1 WHERE case_no=%s AND pricing_revision=%s",
                (event_id, facts.case_no, facts.revision))
            if cursor.rowcount != 1:
                raise PricingConflict("case_pricing_stale")
            if facts.historical_service_hours is not None:
                plan = historical_repricing_plan(self.connection, facts, terms)
                persist_historical_repricing(self.connection, plan, actor, reason, key)
                return
            order = select_order(cursor, facts.case_no, lock=True)
            if identity_reclassification and order["status"] == "訂單取消":
                return
            finance, _ = load_calculable_client_finance_facts(cursor, order, lock=True)
            if finance is None:
                raise ValueError("case_pricing_service_facts_required")
            if identity_reclassification:
                deposit_days = terms.deposit_service_days if terms.deposit_service_days is not None else 5
                finance = replace(finance, payment_terms=replace(
                    finance.payment_terms, deposit_service_days=min(deposit_days, len(finance.charge_days)),
                ))
            candidate = build_client_finance_terms_candidate(finance, f"case-pricing:{event_id}")
            if candidate.blockers:
                raise PricingConflict('full_subsidy_existing_financial_history_conflict')
            if identity_reclassification:
                second = next(stage for stage in candidate.stage_plans if stage.payment_stage.value == "second")
                candidate = replace(candidate, payment_terms=replace(
                    finance.payment_terms, second_payment_due_date=second.due_date,
                ))
            persist_client_finance_terms_impact(cursor, ClientFinanceImpactPersistenceCommand(candidate,
                IdempotencyKey(key), ActorContext(actor), reason, CorrelationId(key), "case-pricing", event_id))
        self._synchronize_payroll(facts.case_no, event_id, actor, reason, key)

    def _synchronize_payroll(self, case_no, event_id, actor, reason, key):
        from domains.scheduling.generation import AssignmentIdentityResolution, build_generation_candidate
        from infrastructure.mysql.order_terms_read_model import load_locked_facts, preflight_staff_ids
        from infrastructure.mysql.payroll_terms_writer import persist_payroll_terms_impact
        from subsystems.orders.terms_workflow import PayrollImpactPersistenceCommand
        from subsystems.payroll.terms_impact import build_payroll_handover_impact
        with self.connection.cursor() as cursor:
            staff_ids = preflight_staff_ids(cursor, case_no)
            if not staff_ids:
                return  # No assignment or salary root is invented by repricing.
            source = load_locked_facts(cursor, case_no, staff_ids)
            scheduling = build_generation_candidate(source.scheduling, source.order.terms, source.planned_service_dates)
            candidate = build_payroll_handover_impact(source.payroll, scheduling, source.order.terms, f"case-pricing:{event_id}")
            resolution = AssignmentIdentityResolution({item.candidate_key: int(item.source_assignment_id)
                for item in scheduling.assignments if item.source_assignment_id is not None})
            persist_payroll_terms_impact(cursor, PayrollImpactPersistenceCommand(
                candidate=replace(candidate, carried_rate_snapshots=(), special_pay_events=()),
                assignment_resolution=resolution, idempotency_key=IdempotencyKey(f"pricing-payroll:{event_id}"),
                actor=ActorContext(actor), reason=reason, correlation_id=CorrelationId(key),
                source_event_id=event_id, reuse_existing_assignments=True))
