"""MySQL pricing persistence; all mutations borrow the caller's transaction."""

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from zoneinfo import ZoneInfo

from domains.client_finance.pricing_policy import CasePricingTerms, HourlyRates, IdentityRule, PricingPolicy
from domains.payroll.tiered_rates import TieredPayrollRate
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.client_finance.pricing_configuration import (
    CasePricingFacts, PolicyVersion, PricingCatalog, PricingConflict, PricingServiceDay, pricing_impact, pricing_payload,
)


def _object(value):
    return value if isinstance(value, dict) else json.loads(value)


def terms_from_payload(value):
    value = _object(value)
    return CasePricingTerms(value["identity_name"], IdentityRule(value["rule"]), Decimal(str(value["subsidy_hours"])),
        HourlyRates(**value["client"]), HourlyRates(**value["payroll"]))


def policy_from_payload(value):
    value = _object(value)
    return PricingPolicy(date.fromisoformat(value["effective_on"]), tuple(terms_from_payload(item) for item in value["identities"]),
        HourlyRates(**value["twins_client"]), HourlyRates(**value["twins_payroll"]))


def _json(value):
    return json.dumps(pricing_payload(value), ensure_ascii=False, sort_keys=True)


def bind_initial_pricing(cursor, case_no):
    """Called only immediately after first Orders insertion, including partial intake."""
    today = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Taipei")).date()
    cursor.execute("SELECT id FROM accounting_pricing_policies WHERE effective_on<=%s ORDER BY effective_on DESC,id DESC LIMIT 1", (today,))
    row = cursor.fetchone()
    if row is not None:
        cursor.execute("UPDATE orders SET pricing_policy_id=%s WHERE case_no=%s AND pricing_policy_id IS NULL", (row["id"], case_no))


def initial_identity_rule(cursor, identity, case_no=None):
    """Resolve only declared new identities; a pre-existing binding wins over today."""
    if not identity or identity in {"一般市民", "補助市民", "社福", "低收入戶", "中低收入戶", "非市民"}:
        return None
    if case_no is not None:
        cursor.execute("SELECT pricing_policy_id FROM orders WHERE case_no=%s", (case_no,))
        case = cursor.fetchone()
        if case is not None:
            if case["pricing_policy_id"] is None:
                return None
            cursor.execute("SELECT policy_json FROM accounting_pricing_policies WHERE id=%s", (case["pricing_policy_id"],))
            row = cursor.fetchone()
            return policy_from_payload(row["policy_json"]).for_case(identity).rule.value if row else None
    today = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Taipei")).date()
    cursor.execute("SELECT policy_json FROM accounting_pricing_policies WHERE effective_on<=%s ORDER BY effective_on DESC,id DESC LIMIT 1", (today,))
    row = cursor.fetchone()
    if row is None:
        return None
    policy = policy_from_payload(row["policy_json"])
    item = next((item for item in policy.identities if item.identity_name == identity), None)
    return item.rule.value if item else None


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
    suffix = " FOR UPDATE" if lock else ""
    if event_id is not None:
        cursor.execute("SELECT pricing_json FROM case_pricing_events WHERE id=%s AND case_no=%s" + suffix,
            (event_id, order_row["case_no"]))
        row = cursor.fetchone()
        if row is None:
            raise ValueError("case_pricing_override_missing")
        return terms_from_payload(row["pricing_json"])
    if policy_id is None:
        return None
    cursor.execute("SELECT policy_json FROM accounting_pricing_policies WHERE id=%s" + suffix, (policy_id,))
    row = cursor.fetchone()
    if row is None:
        raise ValueError("case_pricing_bound_policy_missing")
    identity = order_row.get("client_identity_status", order_row.get("identity_status"))
    return policy_from_payload(row["policy_json"]).for_case(str(identity), twins=_is_twins(cursor, order_row["case_no"], lock))


def payroll_tiers(terms):
    return TieredPayrollRate(terms.payroll.covered, terms.payroll.excess, terms.subsidy_hours, terms.rule is IdentityRule.SOCIAL)


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
        rule = {"一般市民": IdentityRule.CITIZEN, "補助市民": IdentityRule.CITIZEN,
            "社福": IdentityRule.SOCIAL, "低收入戶": IdentityRule.SOCIAL,
            "中低收入戶": IdentityRule.SOCIAL, "非市民": IdentityRule.NON_CITIZEN}.get(identity)
        if rule is None:
            raise ValueError("case_pricing_identity_not_confirmed")
        cursor.execute("SELECT hourly_rate_ntd FROM case_payroll_rate_policy_snapshots WHERE case_no=%s", (order["case_no"],))
        salary = cursor.fetchone()
        if salary is None:
            raise ValueError("case_pricing_payroll_snapshot_required")
        correction = load_explicit_case_service_rate(cursor, order["case_no"])
        salary_rate = correction.hourly_rate_ntd if correction else int(salary["hourly_rate_ntd"])
        cap = Decimal(120 if rule is IdentityRule.SOCIAL else 40 if rule is IdentityRule.CITIZEN else 0)
        client_rate = finance.payment_terms.client_hourly_rate.amount
        return CasePricingTerms(identity, rule, cap, HourlyRates(client_rate, client_rate), HourlyRates(salary_rate, salary_rate))

    def save_case(self, facts, terms, actor, reason, key):
        from domains.client_finance.obligation_planning import build_client_finance_terms_candidate
        from infrastructure.mysql.client_finance_terms_writer import persist_client_finance_terms_impact
        from infrastructure.mysql.order_terms_read_model import load_calculable_client_finance_facts, select_order
        from subsystems.orders.terms_workflow import ClientFinanceImpactPersistenceCommand
        before, after = pricing_impact(facts.terms, facts), pricing_impact(terms, facts)
        with self.connection.cursor() as cursor:
            if before.subsidy_amount != after.subsidy_amount:
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
            order = select_order(cursor, facts.case_no, lock=True)
            finance, _ = load_calculable_client_finance_facts(cursor, order, lock=True)
            if finance is None:
                raise ValueError("case_pricing_service_facts_required")
            candidate = build_client_finance_terms_candidate(finance, f"case-pricing:{event_id}")
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
