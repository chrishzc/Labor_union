"""
File: pricing_configuration_repository.py
Description: 管理 MySQL 帳務計價政策、個案覆寫與歷史案件重算計畫持久化。
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
from typing import Literal, TypedDict
from zoneinfo import ZoneInfo

from pymysql.cursors import DictCursor

from domains.client_finance.pricing_policy import CasePricingTerms, HourlyRates, IdentityRule, PricingPolicy
from domains.client_finance.subsidy_coverage import normalize_subsidy_policy_identity
from domains.orders.floor_fee import prorate_historical_floor_fee
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.payroll.calculation import PayrollPolicyKind, standard_hourly_rate
from domains.payroll.historical_calculation import historical_service_salary
from domains.payroll.tiered_rates import TieredPayrollRate
from infrastructure.mysql.case_category_query import BOUND_POLICY_IDENTITY_SQL
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.money import MoneyNTD
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from subsystems.client_finance.pricing_configuration import (
    CasePricingFacts, CasePricingKnownTerms, PolicyVersion, PricingCatalog, PricingConflict, PricingServiceDay, pricing_impact, pricing_payload,
    HistoricalAmountFacts, build_historical_deposit_floor_fee_plan, build_historical_repricing_plan,
    HistoricalPricingPerson, HistoricalPersonPricing, HistoricalAmountUpdate, HistoricalRepricingPlan,
    HistoricalBirthCorrectionPreview, HistoricalAccountingCarry, HistoricalRateAuthority,
    legacy_historical_service_salary,
)

_LEGACY_BIRTH_POLICY_BLOCKER = 'historical_pricing_birth_bound_policy_required'


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
 AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(e.pricing_json,'$.historical_accounting.rate_authority')),'manual')<>'legacy'
WHERE o.pricing_policy_id IS NOT NULL OR e.id IS NOT NULL"""


def _object(value):
    return value if isinstance(value, dict) else json.loads(value)


def _event_rate_authority(payload: object) -> HistoricalRateAuthority:
    if not isinstance(payload, dict):
        raise ValueError('case_pricing_rate_authority_invalid')
    accounting = payload.get('historical_accounting', {})
    if not isinstance(accounting, dict):
        raise ValueError('case_pricing_rate_authority_invalid')
    authority = accounting.get('rate_authority')
    if authority is None or authority == 'manual':
        return 'manual'
    if authority == 'policy':
        return 'policy'
    if authority == 'legacy':
        return 'legacy'
    raise ValueError('case_pricing_rate_authority_invalid')


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
        payload = _object(row['pricing_json'])
        if _event_rate_authority(payload) == 'legacy':
            event_id = None
        else:
            override = terms_from_payload(payload)
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


@dataclass(frozen=True, slots=True)
class ServiceShorteningPricingBasis:
    receipt_id: int
    scheduling_version: int


def find_service_shortening_pricing_basis(
    cursor: DictCursor, order: Mapping[str, object], *, lock: bool = False,
) -> ServiceShorteningPricingBasis | None:
    service_days = order.get('service_days')
    if not isinstance(service_days, int) or order['status'] not in (
        OrderLifecycleStatus.IN_SERVICE, OrderLifecycleStatus.COMPLETED,
    ):
        return None
    cursor.execute(
        "SELECT receipt.id,receipt.lifecycle_status,receipt.scheduling_version,"
        "CAST(JSON_UNQUOTE(JSON_EXTRACT(event.before_terms,'$.service_days')) AS UNSIGNED) AS before_days,"
        "CAST(JSON_UNQUOTE(JSON_EXTRACT(event.after_terms,'$.service_days')) AS UNSIGNED) AS after_days "
        "FROM order_terms_apply_receipts receipt JOIN order_terms_change_events event "
        "ON event.id=receipt.order_terms_event_id AND event.case_no=receipt.case_no "
        "WHERE receipt.case_no=%s HAVING before_days<>after_days ORDER BY receipt.order_version DESC LIMIT 1"
        + (' FOR UPDATE' if lock else ''),
        (order['case_no'],),
    )
    receipt = cursor.fetchone()
    if (receipt is None or receipt['after_days'] != service_days or receipt['before_days'] <= service_days
            or receipt['lifecycle_status'] not in (OrderLifecycleStatus.IN_SERVICE, OrderLifecycleStatus.COMPLETED)):
        return None
    return ServiceShorteningPricingBasis(int(receipt['id']), int(receipt['scheduling_version']))


def query_case_pricing_total(connection, case_no: str, *, for_update: bool = False) -> int | None:
    """Case total from formal pricing and service facts, independent of payment terms."""
    from domains.client_finance.pricing_policy import (
        calculate_case_total_amount, calculate_holiday_premium,
    )
    from infrastructure.mysql.holiday_repricing import load_frozen_holiday_case_total
    from infrastructure.mysql.order_terms_read_model import load_client_pricing_charge_days, select_order

    lock = " FOR UPDATE" if for_update else ""
    try:
        with connection.cursor() as cursor:
            order = select_order(cursor, case_no, lock=for_update)
            pricing = load_case_pricing(cursor, order, lock=for_update)
            if pricing is None:
                cursor.execute("SELECT client_hourly_rate_ntd FROM client_payment_terms WHERE case_no=%s" + lock,
                               (case_no,))
                original = cursor.fetchone()
                if not original or not original['client_hourly_rate_ntd']:
                    return None
                identity = str(order['client_identity_status'])
                rule, cap = _legacy_rule_and_cap(identity)
                rate = int(original['client_hourly_rate_ntd'])
                rates = HourlyRates(rate, rate)
                pricing = CasePricingTerms(identity, rule, cap, rates, rates)
            if str(order["status"]).startswith('歷史'):
                cursor.execute(
                    "SELECT p.total_actual_service_hours,e.historical_floor_fee_ntd "
                    "FROM historical_service_day_projections p JOIN historical_service_day_events e "
                    "ON e.id=p.current_event_id AND e.case_no=p.case_no WHERE p.case_no=%s" + lock,
                    (case_no,),
                )
                volume = cursor.fetchone()
                if volume is not None:
                    if volume['total_actual_service_hours'] is None or volume['historical_floor_fee_ntd'] is None:
                        return None
                    hours, floor = Decimal(str(volume['total_actual_service_hours'])), int(volume['historical_floor_fee_ntd'])
                    return calculate_case_total_amount(pricing, ((hours, False),), floor)
                cursor.execute("SELECT id FROM historical_order_adoption_receipts "
                               "WHERE case_no=%s AND outcome='adopted' LIMIT 1" + lock, (case_no,))
                if cursor.fetchone() is None:
                    return None
                if any(order.get(key) is None for key in ('floor_fee', 'service_hours_per_day', 'service_days')):
                    return None
                hours = Decimal(str(order['service_hours_per_day'])) * int(order['service_days'])
                return calculate_case_total_amount(pricing, ((hours, False),), int(order['floor_fee']))
            service_days = order.get('service_days')
            shortening = find_service_shortening_pricing_basis(cursor, order, lock=for_update)
            frozen = load_frozen_holiday_case_total(cursor, case_no, shortening=shortening)
            if frozen is not None:
                return frozen
            if any(order.get(key) is None for key in ('floor_fee', 'service_hours_per_day', 'service_days')):
                return None
            daily_hours = Decimal(str(order['service_hours_per_day']))
            floor = int(order['floor_fee'])
            days = load_client_pricing_charge_days(cursor, order, lock=for_update, allow_planned=shortening is None)
            if not days:
                return None
            if shortening is not None:
                start, end = order.get('actual_start_date'), order.get('actual_end_date')
                if start is None or end is None or len(days) != service_days:
                    return None
                if any(not start <= day.service_date <= end for day in days):
                    return None
            gross = calculate_case_total_amount(pricing, tuple((daily_hours, day.is_double_pay) for day in days), floor)
            return gross + calculate_holiday_premium(pricing, tuple(
                (daily_hours, day.holiday_hour_segments or ((Decimal(0), day.holiday_hours),)) for day in days
            ))
    except ValueError:
        return None


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


def load_historical_pricing_facts(connection, case_no, *, lock=False, order=None, readback=False):
    """Borrow confirmed historical volume, without manufacturing calendar days."""
    from infrastructure.mysql.order_terms_read_model import select_order
    from infrastructure.mysql.historical_service_accounting_repository import (
        MySqlHistoricalServiceAccountingRepository, _select_historical_default_payroll_policy,
    )
    with connection.cursor() as cursor:
        order = order if order is not None else select_order(cursor, case_no, lock=lock)
        if str(order['status']) not in ('歷史訂單－服務完成', '歷史訂單－帳務完成'):
            return None
        source = MySqlHistoricalServiceAccountingRepository(connection).load(case_no, for_update=lock)
        suffix = ' FOR UPDATE' if lock else ''
        cursor.execute('SELECT i.assignment_id,i.staff_id,i.actual_service_days,i.actual_service_hours '
            'FROM historical_service_day_projections p JOIN historical_service_day_items i '
            'ON i.event_id=p.current_event_id WHERE p.case_no=%s ORDER BY i.item_ordinal' + suffix, (case_no,))
        items = tuple(cursor.fetchall())
        days = sum(int(item['actual_service_days']) for item in items) if items else source.contracted_service_days
        hours = (sum((Decimal(str(item['actual_service_hours'])) for item in items), Decimal(0))
                 if items and all(item['actual_service_hours'] is not None for item in items)
                 else Decimal(days) * Decimal(source.service_hours_per_day))
        indexed = {f"assignment:{item['assignment_id']}": item for item in items}
        cursor.execute('SELECT a.id,COALESCE(r.hourly_rate_ntd,c.hourly_rate_ntd) original_hourly_rate '
            'FROM case_staff_assignments a '
            'LEFT JOIN assignment_payroll_rate_snapshots r ON r.assignment_id=a.id '
            'LEFT JOIN case_payroll_rate_policy_snapshots c ON c.case_no=a.case_no '
            'WHERE a.case_no=%s' + suffix, (case_no,))
        original_rates = {f"assignment:{row['id']}": int(row['original_hourly_rate'])
            for row in cursor.fetchall() if row['original_hourly_rate'] is not None}
        people = tuple(HistoricalPricingPerson(
            assignment.assignment_identity, assignment.staff_id, assignment.staff_name,
            Decimal(str(indexed[assignment.assignment_identity]['actual_service_hours']))
            if assignment.assignment_identity in indexed and indexed[assignment.assignment_identity]['actual_service_hours'] is not None
            else Decimal(int(indexed[assignment.assignment_identity]['actual_service_days'])) * source.service_hours_per_day
            if assignment.assignment_identity in indexed else hours if len(source.assignments) == 1 else None,
            int(indexed[assignment.assignment_identity]['actual_service_days']) if assignment.assignment_identity in indexed
            else days if len(source.assignments) == 1 else None, assignment.effective_adjustment.amount,
            assignment.rate_snapshot, original_rates.get(assignment.assignment_identity))
            for assignment in source.assignments)
        if any(person.hours is None for person in people):
            hours = None
        floor = int((Decimal(source.contractual_floor_fee.amount) * days / source.contracted_service_days).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        terms = load_case_pricing(cursor, order, lock=lock)
        if terms is None:
            rule, cap = _legacy_rule_and_cap(source.client_identity_status)
            cursor.execute('SELECT hourly_rate_ntd FROM case_payroll_rate_policy_snapshots WHERE case_no=%s' + suffix, (case_no,))
            payroll_policy = cursor.fetchone()
            staff_rate = int(payroll_policy['hourly_rate_ntd']) if payroll_policy else (
                source.assignments[0].rate_snapshot.hourly_rate.amount if len(source.assignments) == 1
                else _select_historical_default_payroll_policy(cursor, case_no, lock).hourly_rate.amount)
            if staff_rate <= 0:
                raise PricingConflict('case_pricing_payroll_snapshot_required')
            terms = CasePricingTerms(source.client_identity_status, rule, cap,
                HourlyRates(source.client_hourly_rate.amount, source.client_hourly_rate.amount), HourlyRates(staff_rate, staff_rate))
        cursor.execute('SELECT aggregate_version FROM scheduling_aggregates WHERE case_no=%s' + (' FOR UPDATE' if lock else ''), (case_no,))
        scheduling = cursor.fetchone()
        accounting = {}
        rate_authority: HistoricalRateAuthority = 'policy' if order.get('pricing_policy_id') else 'legacy'
        if order.get('pricing_override_event_id'):
            cursor.execute('SELECT pricing_json FROM case_pricing_events WHERE id=%s' + suffix, (order['pricing_override_event_id'],))
            event = cursor.fetchone()
            if event:
                payload = _object(event['pricing_json'])
                rate_authority = _event_rate_authority(payload)
                accounting = payload.get('historical_accounting', {})
        pricing_accounting = accounting
        cursor.execute('SELECT e.resulting_day_revision,e.result_snapshot FROM historical_service_day_events e '
            "WHERE e.case_no=%s AND JSON_TYPE(JSON_EXTRACT(e.result_snapshot,'$.financial_correction'))='OBJECT' "
            'ORDER BY e.resulting_day_revision DESC LIMIT 1' + suffix, (case_no,))
        service_event = cursor.fetchone()
        if service_event:
            service_plan = _object(service_event['result_snapshot']).get('financial_correction')
            pricing_versions = accounting.get('source_versions', ())
            if service_plan and (not pricing_versions or int(service_event['resulting_day_revision']) > int(pricing_versions[4])):
                accounting = service_plan
        standard_rate = (standard_hourly_rate(PayrollPolicyKind.TWINS)
            if rate_authority == 'legacy' and _is_twins(cursor, case_no, lock) else None)
        carry = tuple(HistoricalAccountingCarry(
            item['component'], item['identity'], item['basis_amount'], tuple(item['pending']),
            item['financial_sources_digest'], item.get('subsidy_claim_basis'))
            for item in accounting.get('carry', ()))
        facts = CasePricingFacts(case_no, int(order.get('pricing_revision', 0)),
            (source.lifecycle_version, source.client_finance_version, source.payroll_version,
             int(scheduling['aggregate_version']) if scheduling else -1, source.historical_day_revision, source.adoption_receipt_id),
            terms, rate_authority,
            (), floor, sum(person.adjustment for person in people), historical_service_hours=hours,
            historical_people=people, historical=str(order['status']) == '歷史訂單－服務完成',
            accounting_pending=tuple(accounting.get('pending', ())), accounting_carry=carry,
            historical_payroll_rate=standard_rate)
        if readback and standard_rate is not None:
            facts = _historical_twins_payroll_readback(cursor, facts, pricing_accounting, standard_rate)
        return facts


def historical_deposit_floor_fee_plan(cursor, order, proposed_fee, *, lock):
    """Use recorded service days to plan the customer-side floor-fee delta."""
    case_no = str(order['case_no'])
    suffix = ' FOR UPDATE' if lock else ''
    cursor.execute('SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s' + suffix, (case_no,))
    account = cursor.fetchone()
    if account is None:
        raise PricingConflict('client_finance_bootstrap_required')
    version = int(account['aggregate_version'])
    cursor.execute('SELECT day_revision,total_actual_service_days FROM historical_service_day_projections '
                   'WHERE case_no=%s' + suffix, (case_no,))
    volume = cursor.fetchone()
    contracted_days = int(order['service_days'])
    adopted_days = int(volume['total_actual_service_days']) if volume else contracted_days
    revision = int(volume['day_revision']) if volume else 0
    before = prorate_historical_floor_fee(MoneyNTD(int(order['floor_fee'])), contracted_days, adopted_days)
    after = prorate_historical_floor_fee(proposed_fee, contracted_days, adopted_days)
    delta = after.amount - before.amount
    rows = _historical_client_amount_rows(cursor, case_no, ('deposit',), suffix)
    if len(rows) > 1:
        raise PricingConflict('historical_pricing_original_installments_required')
    new_deposit = None
    if not rows and delta > 0:
        cursor.execute('SELECT deposit_due_date FROM client_payment_terms WHERE case_no=%s' + suffix, (case_no,))
        payment_terms = cursor.fetchone()
        due_date = payment_terms['deposit_due_date'] if payment_terms else None
        new_deposit = (f'historical-floor-fee-deposit:{case_no}:{version + 1}', due_date.isoformat() if due_date else None)
    return build_historical_deposit_floor_fee_plan(
        case_no, version, (contracted_days, adopted_days, revision),
        _historical_amount_facts(rows[0]) if rows else None, new_deposit, delta,
    )


def _historical_client_amount_rows(cursor, case_no, stages, suffix):
    placeholders = ','.join('%s' for _ in stages)
    cursor.execute('SELECT o.obligation_identity,o.obligation_type,o.current_event_id,o.status,o.due_date,o.amount_due_ntd,e.after_amount_ntd nominal,c.amount_mode,c.computed_ntd,c.effective_ntd '
        'FROM client_obligations o JOIN client_obligation_events e ON e.id=o.current_event_id '
        'LEFT JOIN client_finance_amount_controls c ON c.obligation_identity=o.obligation_identity '
        "WHERE o.case_no=%s AND o.status<>'cancelled' AND o.source_obligation_identity IS NULL "
        "AND o.direction='receivable_from_client' AND o.obligation_type IN (" + placeholders +
        ") ORDER BY FIELD(o.obligation_type,'deposit','first','second')" + suffix, (case_no, *stages))
    return cursor.fetchall()


class HistoricalAmountRow(TypedDict):
    obligation_identity: str
    nominal: int
    computed_ntd: int | None
    effective_ntd: int | None
    amount_mode: str | None


class HistoricalClientAmountRow(HistoricalAmountRow):
    obligation_type: str


class HistoricalStaffAmountRow(HistoricalAmountRow):
    assignment_id: int | None
    staff_id: int


def _historical_amount_facts(row: HistoricalAmountRow) -> HistoricalAmountFacts:
    computed = int(row['computed_ntd'] if row['computed_ntd'] is not None else row['nominal'])
    effective = int(row['effective_ntd'] if row['effective_ntd'] is not None else row['nominal'])
    return HistoricalAmountFacts(row['obligation_identity'], computed, effective, row['amount_mode'] or 'automatic')


def _amount_update(source: HistoricalAmountFacts, delta: int) -> HistoricalAmountUpdate:
    computed = source.computed + delta
    effective = source.effective if source.mode == 'manual' else computed
    if min(computed, effective) < 0:
        raise PricingConflict('historical_pricing_amount_conflict')
    return HistoricalAmountUpdate(source.identity, computed, effective, source.computed, source.effective, source.mode)


def _historical_staff_rows(cursor, case_no: str, suffix: str) -> tuple[HistoricalStaffAmountRow, ...]:
    cursor.execute('SELECT o.obligation_identity,o.assignment_id,o.staff_id,o.current_event_id,o.status,o.amount_due_ntd,o.due_date,e.after_amount_ntd nominal,c.amount_mode,c.computed_ntd,c.effective_ntd '
        'FROM staff_obligations o JOIN staff_obligation_events e ON e.id=o.current_event_id '
        'LEFT JOIN payroll_amount_controls c ON c.obligation_identity=o.obligation_identity '
        "WHERE o.case_no=%s AND o.status<>'cancelled' AND o.obligation_kind='service_pay' AND o.direction='payable_to_staff' AND o.source_obligation_identity IS NULL" + suffix, (case_no,))
    return tuple(cursor.fetchall())


def _original_payables(person: HistoricalPricingPerson, staff_rows: tuple[HistoricalStaffAmountRow, ...]
        ) -> tuple[HistoricalStaffAmountRow, ...]:
    return tuple(row for row in staff_rows if row['assignment_id'] is not None and
        int(row['assignment_id']) == int(person.assignment_identity.removeprefix('assignment:'))
        and int(row['staff_id']) == person.staff_id)


def _historical_twins_payroll_readback(cursor, facts: CasePricingFacts, accounting: Mapping[str, object],
        rate: MoneyNTD) -> CasePricingFacts:
    staff_rows = _historical_staff_rows(cursor, facts.case_no, '')
    amounts = _person_amounts(facts.terms, facts, use_legacy_person_rates=True)
    saved = accounting.get('persons')
    recorded = {person['assignment_identity']: person for person in saved
        if isinstance(person, dict) and person.get('effective_hourly_rate') == rate.amount} if isinstance(saved, list) else {}
    pending = [code for code in facts.accounting_pending if code != _LEGACY_BIRTH_POLICY_BLOCKER]
    people = []
    for person in facts.historical_people:
        identity = person.assignment_identity
        originals = _original_payables(person, staff_rows)
        source = _historical_amount_facts(originals[0]) if len(originals) == 1 else None
        calculated = amounts.get(identity)
        previous = recorded.get(identity)
        matches = source is not None and calculated == source.computed
        confirmed = previous if source and matches and previous and previous['after_amount'] == source.effective else None
        if source is None:
            code = 'historical_pricing_original_payable_ambiguous:' if originals else 'historical_pricing_original_payable_required:'
            pending.append(code + identity)
        elif calculated is None:
            pending.append('historical_pricing_person_service_hours_required:' + identity)
        elif not matches:
            pending.append('historical_pricing_standard_twins_difference_pending:' + identity)
        people.append(HistoricalPersonPricing(identity, person.staff_id, person.staff_name, person.hours,
            confirmed['before_amount'] if confirmed else None, source.effective if source else None,
            confirmed['delta'] if confirmed else 0 if matches else None,
            snapshot_hourly_rate=person.original_hourly_rate,
            effective_hourly_rate=rate.amount, calculated_amount=calculated))
    formal = (sum(person.after_amount for person in people if person.after_amount is not None)
        if people and all(person.after_amount is not None for person in people) else None)
    return replace(facts, historical_payroll=tuple(people), formal_staff_amount=formal,
        accounting_pending=tuple(dict.fromkeys(pending)))


def historical_repricing_plan(connection, facts: CasePricingFacts, terms: CasePricingTerms, *, lock: bool = True,
                              after_facts: CasePricingFacts | None = None,
                              include_payroll: bool = True,
                              use_legacy_person_rates: bool = False) -> HistoricalRepricingPlan:
    """Apply a price delta to evidenced original installments, never regenerate them."""
    suffix = ' FOR UPDATE' if lock else ''
    with connection.cursor() as cursor:
        client_rows = _historical_client_amount_rows(cursor, facts.case_no, ('deposit', 'first', 'second'), suffix)
        if not facts.historical and (not client_rows or len({r['obligation_type'] for r in client_rows}) != len(client_rows)):
            raise PricingConflict('historical_pricing_original_installments_required')
        staff_rows = _historical_staff_rows(cursor, facts.case_no, suffix)
        if not facts.historical and len(staff_rows) != 1:
            raise PricingConflict('historical_pricing_original_payable_required')
        cursor.execute('SELECT o.obligation_identity,e.after_amount_ntd nominal,c.amount_mode,c.computed_ntd,c.effective_ntd '
            'FROM client_obligations o JOIN client_obligation_events e ON e.id=o.current_event_id '
            'LEFT JOIN client_finance_amount_controls c ON c.obligation_identity=o.obligation_identity '
            "WHERE o.case_no=%s AND o.status<>'cancelled' AND o.obligation_type='subsidy_return' AND o.source_obligation_identity IS NULL" + suffix, (facts.case_no,))
        subsidy_rows = cursor.fetchall()
        if not facts.historical and len(subsidy_rows) > 1:
            raise PricingConflict('historical_pricing_original_subsidy_return_required')
        if facts.historical:
            cursor.execute("SELECT m.receipt_id,m.amount_ntd AS member_amount_ntd,e.amount_ntd,e.paid_on FROM government_subsidy_period_members m "
                "JOIN government_subsidy_period_entries e ON e.id=m.receipt_id "
                "WHERE m.case_no=%s AND e.reversal_of_id IS NULL AND NOT EXISTS "
                "(SELECT 1 FROM government_subsidy_period_entries r WHERE r.reversal_of_id=e.id)" + suffix, (facts.case_no,))
            period_sources = tuple(cursor.fetchall())
            cursor.execute("SELECT i.id FROM subsidy_claim_batch_items i WHERE i.case_no=%s AND ("
                "COALESCE((SELECT SUM(CASE WHEN a.allocation_type='receipt' THEN a.allocated_amount "
                "WHEN a.allocation_type='reversal' THEN -a.allocated_amount ELSE 0 END) "
                "FROM government_subsidy_allocations a WHERE a.claim_item_id=i.id),0)>0 "
                "OR EXISTS(SELECT 1 FROM government_subsidy_overpayment_offsets x WHERE x.claim_item_id=i.id))" + suffix, (facts.case_no,))
            claim_sources = tuple(cursor.fetchall())
            cursor.execute('SELECT l.id,l.entry_type,l.amount_ntd,l.occurred_on,l.reversal_of_entry_id,'
                'a.obligation_identity,a.amount_ntd AS allocated_ntd FROM client_ledger_entries l '
                'LEFT JOIN client_ledger_obligation_allocations a ON a.ledger_entry_id=l.id '
                'WHERE l.case_no=%s ORDER BY l.id,a.allocation_ordinal' + suffix, (facts.case_no,))
            client_cash = tuple(cursor.fetchall())
            cursor.execute('SELECT o.obligation_identity,p.id,p.event_type,p.amount_ntd,p.occurred_on,'
                'p.reversal_of_event_id,l.allocated_amount_ntd FROM staff_obligations o '
                'JOIN staff_payout_obligation_links l ON l.obligation_identity=o.obligation_identity '
                'JOIN staff_payout_events p ON p.id=l.payout_event_id '
                'WHERE o.case_no=%s ORDER BY p.id,l.allocation_ordinal' + suffix, (facts.case_no,))
            payroll_cash = tuple(cursor.fetchall())
            cursor.execute('SELECT obligation_identity,obligation_type,status,current_event_id '
                "FROM client_obligations WHERE case_no=%s AND status<>'cancelled' "
                "AND direction='receivable_from_client' AND source_obligation_identity IS NULL "
                "AND obligation_type NOT IN ('deposit','first','second') ORDER BY obligation_identity" + suffix, (facts.case_no,))
            unknown_client_sources = tuple(cursor.fetchall())
            from infrastructure.mysql.client_payments_query_repository import _historical_payment_terms
            from infrastructure.mysql.order_terms_read_model import select_order
            payment_evidence = _historical_payment_terms(cursor, select_order(cursor, facts.case_no, lock=lock), None)
            client_source_pending = tuple(payment_evidence.pending_reasons)
            client_exempt = (not client_rows and not unknown_client_sources and not client_cash
                and not client_source_pending and payment_evidence.full_subsidy_eligibility is True)
            digest = fingerprint_payload(pricing_payload({'client': client_rows, 'payroll': staff_rows,
                'subsidy': subsidy_rows, 'period': period_sources, 'claims': claim_sources,
                'client_cash': client_cash, 'payroll_cash': payroll_cash, 'unknown_client': unknown_client_sources,
                'client_pending': client_source_pending,
                'bank_candidates': payment_evidence.pending_bank_row_identities})).value
            return _partial_historical_repricing_plan(facts, terms, after_facts or facts,
                tuple(client_rows), tuple(staff_rows), tuple(subsidy_rows),
                bool(period_sources or claim_sources), digest, include_payroll,
                client_exempt=client_exempt, unknown_client_sources=bool(unknown_client_sources),
                client_source_pending=client_source_pending, use_legacy_person_rates=use_legacy_person_rates)
    return build_historical_repricing_plan(facts, terms, tuple(_historical_amount_facts(r) for r in client_rows),
        _historical_amount_facts(staff_rows[0]),
        subsidy_source=_historical_amount_facts(subsidy_rows[0]) if subsidy_rows else None)


def _person_amounts(terms: CasePricingTerms, facts: CasePricingFacts, *,
        use_legacy_person_rates: bool = False) -> dict[str, int]:
    from domains.orders.floor_fee import allocate_largest_remainder
    from domains.payroll.tiered_rates import price_hours
    people = facts.historical_people
    if not people:
        return {}
    if facts.floor_fee and any(person.actual_service_days is None or person.actual_service_days <= 0 for person in people):
        return {}
    floor = (allocate_largest_remainder(MoneyNTD(facts.floor_fee),
        {person.assignment_identity: person.actual_service_days for person in people if person.actual_service_days is not None})
        if facts.floor_fee else {})
    amounts: dict[str, int] = {}
    consumed: Decimal | None = Decimal(0)
    for person in people:
        if person.hours is None:
            if consumed is not None and consumed < terms.subsidy_hours:
                consumed = None
            continue
        own_rate = use_legacy_person_rates and facts.source == 'legacy'
        if not own_rate and consumed is None and terms.payroll.covered != terms.payroll.excess:
            continue
        if own_rate and facts.historical_payroll_rate is not None:
            salary = historical_service_salary(person.hours, facts.historical_payroll_rate).amount
        elif own_rate:
            salary = legacy_historical_service_salary(person, person.hours)
        else:
            covered, excess = price_hours(((person.hours, False),), payroll_tiers(terms), consumed or Decimal(0))
            salary = covered + excess
        if consumed is not None:
            consumed += person.hours
        amounts[person.assignment_identity] = (salary
            + (floor[person.assignment_identity].amount if floor else 0) + person.adjustment)
    return amounts


def _partial_historical_repricing_plan(facts: CasePricingFacts, terms: CasePricingTerms,
        after_facts: CasePricingFacts, client_rows: tuple[HistoricalClientAmountRow, ...],
        staff_rows: tuple[HistoricalStaffAmountRow, ...], subsidy_rows: tuple[HistoricalAmountRow, ...],
        settled_subsidy: bool, digest: str, include_payroll: bool, *,
        client_exempt: bool = False, unknown_client_sources: bool = False,
        client_source_pending: tuple[str, ...] = (),
        use_legacy_person_rates: bool = False) -> HistoricalRepricingPlan:
    before = pricing_impact(facts.terms, facts)
    after = pricing_impact(terms, after_facts, use_legacy_person_rates=use_legacy_person_rates)
    pending: list[str] = []
    carry: list[HistoricalAccountingCarry] = []
    previous = {(item.component, item.identity): item for item in facts.accounting_carry}
    birth_blockers = {'historical_pricing_birth_original_value_required', 'historical_pricing_birth_bound_policy_required'}
    def defer(component: Literal['client', 'subsidy', 'payroll'], identity: str,
              basis: int | None, reasons: tuple[str, ...], subsidy_claim_basis: int | None = None) -> None:
        prior = previous.get((component, identity))
        reasons = tuple(dict.fromkeys(reasons))
        pending.extend(reasons)
        carry.append(HistoricalAccountingCarry(component, identity,
            prior.basis_amount if prior else basis, reasons,
            prior.financial_sources_digest if prior else digest,
            prior.subsidy_claim_basis if prior else subsidy_claim_basis))
    client_updates: list[HistoricalAmountUpdate] = []
    staff_updates: list[HistoricalAmountUpdate] = []
    client_prior = previous.get(('client', facts.case_no))
    client_basis = client_prior.basis_amount if client_prior else (
        before.client_amount if facts.historical_service_hours is not None else None)
    volume_known = after_facts.historical_service_hours is not None
    client_delta = (after.client_amount - client_basis
        if client_basis is not None and after.client_amount is not None else None)
    client_exempt = client_exempt and volume_known and terms.is_full_subsidy(after_facts.historical_service_hours) is True
    if client_prior and (client_basis is None or birth_blockers.intersection(client_prior.pending)):
        client_delta = None
        defer('client', facts.case_no, None, client_prior.pending)
    elif client_basis is None:
        defer('client', facts.case_no, None, ('historical_pricing_original_calculation_basis_required',))
    elif not volume_known:
        defer('client', facts.case_no, client_basis, ('historical_pricing_total_service_hours_required',))
    elif unknown_client_sources or len({row['obligation_type'] for row in client_rows}) != len(client_rows):
        defer('client', facts.case_no, client_basis, ('historical_pricing_original_installments_ambiguous',))
    elif not client_rows and not client_exempt:
        defer('client', facts.case_no, client_basis,
            ('historical_pricing_original_installments_required', *client_source_pending))
    elif client_rows and client_delta is not None:
        remainder = client_delta
        proposed: list[HistoricalAmountUpdate] = []
        for row in reversed(client_rows):
            source = _historical_amount_facts(row)
            applied = max(-source.computed, remainder) if remainder < 0 else remainder
            proposed.append(_amount_update(source, applied))
            remainder -= applied
        if remainder:
            defer('client', facts.case_no, client_basis, ('historical_pricing_client_amount_unresolved',))
        else:
            client_updates.extend(proposed)
    subsidy_prior = previous.get(('subsidy', facts.case_no))
    subsidy_basis = subsidy_prior.basis_amount if subsidy_prior else (
        before.subsidy_return_amount if facts.historical_service_hours is not None else None)
    claim_basis = subsidy_prior.subsidy_claim_basis if subsidy_prior else (
        before.subsidy_amount if facts.historical_service_hours is not None else None)
    subsidy_delta = (after.subsidy_return_amount - subsidy_basis
        if subsidy_basis is not None and after.subsidy_return_amount is not None else None)
    if subsidy_prior and (subsidy_basis is None or birth_blockers.intersection(subsidy_prior.pending)):
        subsidy_delta = None
        defer('subsidy', facts.case_no, None, subsidy_prior.pending, claim_basis)
    elif subsidy_basis is None:
        defer('subsidy', facts.case_no, None,
            ('historical_pricing_original_calculation_basis_required',), claim_basis)
    elif not volume_known:
        defer('subsidy', facts.case_no, subsidy_basis,
            ('historical_pricing_total_service_hours_required',), claim_basis)
    elif settled_subsidy and (subsidy_delta or after.subsidy_amount != claim_basis):
        defer('subsidy', facts.case_no, subsidy_basis,
            ('case_pricing_settled_subsidy_correction_required',), claim_basis)
    elif len(subsidy_rows) > 1:
        defer('subsidy', facts.case_no, subsidy_basis,
            ('historical_pricing_original_subsidy_return_ambiguous',), claim_basis)
    elif subsidy_rows and subsidy_delta is not None:
        try:
            client_updates.append(_amount_update(_historical_amount_facts(subsidy_rows[0]), subsidy_delta))
        except PricingConflict:
            defer('subsidy', facts.case_no, subsidy_basis,
                ('historical_pricing_subsidy_amount_unresolved',), claim_basis)
    elif subsidy_delta:
        defer('subsidy', facts.case_no, subsidy_basis,
            ('historical_pricing_original_subsidy_return_required',), claim_basis)
    after_people = _person_amounts(terms, after_facts, use_legacy_person_rates=use_legacy_person_rates)
    standard_rate = after_facts.historical_payroll_rate if use_legacy_person_rates else None
    persons: list[HistoricalPersonPricing] = []
    for person in after_facts.historical_people:
        originals = _original_payables(person, staff_rows)
        source = _historical_amount_facts(originals[0]) if len(originals) == 1 else None
        calculated = after_people.get(person.assignment_identity)
        update = None
        person_prior = previous.get(('payroll', person.assignment_identity))
        if person_prior and standard_rate is None and birth_blockers.intersection(person_prior.pending):
            defer('payroll', person.assignment_identity, None, person_prior.pending)
        elif calculated is None:
            if include_payroll:
                defer('payroll', person.assignment_identity, None,
                    ('historical_pricing_person_service_hours_required:' + person.assignment_identity,))
        elif source is None:
            if include_payroll:
                code = 'historical_pricing_original_payable_ambiguous:' if len(originals) > 1 else 'historical_pricing_original_payable_required:'
                defer('payroll', person.assignment_identity, calculated, (code + person.assignment_identity,))
        else:
            try:
                update = _amount_update(source, calculated - source.computed)
                if include_payroll:
                    staff_updates.append(update)
            except PricingConflict:
                if include_payroll:
                    defer('payroll', person.assignment_identity, calculated,
                        ('historical_pricing_payroll_amount_unresolved:' + person.assignment_identity,))
        persons.append(HistoricalPersonPricing(person.assignment_identity, person.staff_id,
            person.staff_name, person.hours, source.effective if source else None,
            update.effective if update else None,
            update.effective - source.effective if update is not None and source is not None else None,
            snapshot_hourly_rate=person.original_hourly_rate if standard_rate else None,
            effective_hourly_rate=standard_rate.amount if standard_rate else None,
            calculated_amount=calculated if standard_rate else None))
    if include_payroll and not after_facts.historical_people:
        pending.append('historical_pricing_assignments_required')
    for person in after_facts.historical_people:
        if person.hours is None or person.actual_service_days is None:
            marker = 'historical_completed_service_volume_unresolved:' + person.assignment_identity
            if marker in facts.accounting_pending:
                pending.append(marker)
    for item in facts.accounting_carry:
        if item.component == 'payroll' and (not include_payroll or
                item.identity not in {person.assignment_identity for person in after_facts.historical_people}):
            carry.append(item)
            pending.extend(item.pending)
    return HistoricalRepricingPlan(facts.case_no, facts.versions[1], facts.versions[2],
        tuple(client_updates), tuple(staff_updates), facts.versions, None, tuple(persons),
        tuple(dict.fromkeys(pending)), client_exempt, client_delta, subsidy_delta, digest, tuple(carry))


def persist_historical_repricing(connection, plan, actor, reason, key):
    from infrastructure.mysql.client_difference_repository import persist_historical_source_amounts as client_apply
    client_apply(connection, plan, actor, reason, key)
    if plan.payroll_changed:
        from infrastructure.mysql.payroll_amount_correction_repository import persist_historical_source_amounts as staff_apply
        staff_apply(connection, plan, actor, reason, key)


def preview_historical_service_volume_correction(connection, *, case_no: str,
        before_hours_by_assignment: dict[str, Decimal], after_hours_by_assignment: dict[str, Decimal],
        for_update: bool = False) -> HistoricalRepricingPlan:
    facts = load_historical_pricing_facts(connection, case_no, lock=for_update)
    if facts is None or not facts.historical:
        raise PricingConflict('historical_order_source_status_invalid')
    expected = {person.assignment_identity for person in facts.historical_people}
    if not set(before_hours_by_assignment) <= expected or not set(after_hours_by_assignment) <= expected:
        raise PricingConflict('historical_actual_service_days_assignment_mismatch')
    before_people = tuple(replace(person, hours=before_hours_by_assignment.get(person.assignment_identity))
                          for person in facts.historical_people)
    after_people = tuple(replace(person, hours=after_hours_by_assignment.get(person.assignment_identity))
                         for person in facts.historical_people)
    before = replace(facts, historical_people=before_people,
        historical_service_hours=(sum(before_hours_by_assignment.values(), Decimal(0))
            if set(before_hours_by_assignment) == expected else None))
    after = replace(facts, historical_people=after_people,
        historical_service_hours=(sum(after_hours_by_assignment.values(), Decimal(0))
            if set(after_hours_by_assignment) == expected else None))
    return historical_repricing_plan(connection, before, facts.terms, lock=for_update,
        after_facts=after, include_payroll=True, use_legacy_person_rates=facts.source == 'legacy')


def preview_historical_birth_correction(connection, *, case_no: str, before_birth_count: str | None,
        after_birth_count: str, for_update: bool = False) -> HistoricalBirthCorrectionPreview:
    from infrastructure.mysql.order_terms_read_model import select_order
    facts = load_historical_pricing_facts(connection, case_no, lock=for_update)
    if facts is None or not facts.historical:
        raise PricingConflict('historical_order_source_status_invalid')
    with connection.cursor() as cursor:
        order = select_order(cursor, case_no, lock=for_update)
        policy_id = order.get('pricing_policy_id')
        terms = facts.terms
        if before_birth_count == after_birth_count and facts.historical_payroll_rate is None:
            raise PricingConflict('historical_pricing_birth_repair_not_required')
        if facts.source == 'policy' and policy_id is not None and before_birth_count in {'單胞胎', '雙胞胎'}:
            cursor.execute('SELECT policy_json FROM accounting_pricing_policies WHERE id=%s' +
                (' FOR UPDATE' if for_update else ''), (policy_id,))
            policy = policy_from_payload(cursor.fetchone()['policy_json'])
            after_terms = policy.for_case(str(order['client_identity_status']), twins=after_birth_count == '雙胞胎')
            terms = replace(facts.terms, client=after_terms.client, payroll=after_terms.payroll)
        authority: HistoricalRateAuthority = ('policy' if facts.source == 'policy' else
            'manual' if facts.source == 'manual' else 'legacy')
        standard_rate = (standard_hourly_rate(PayrollPolicyKind.TWINS)
            if authority == 'legacy' and after_birth_count == '雙胞胎' else None)
        if standard_rate is not None:
            carry = tuple(replace(item, pending=tuple(code for code in item.pending if code != _LEGACY_BIRTH_POLICY_BLOCKER))
                for item in facts.accounting_carry)
            facts = replace(facts, accounting_carry=tuple(item for item in carry if item.pending))
        after = replace(facts, historical_payroll_rate=standard_rate)
        plan = replace(historical_repricing_plan(connection, facts, terms, lock=for_update,
            after_facts=after, use_legacy_person_rates=authority == 'legacy'), rate_authority=authority)
        if before_birth_count == after_birth_count and not plan.payroll_changed and all(
                person.delta is not None for person in plan.persons):
            raise PricingConflict('historical_pricing_birth_repair_not_required')
        if standard_rate is None and before_birth_count not in {'單胞胎', '雙胞胎'}:
            code = 'historical_pricing_birth_original_value_required'
            bases = {(item.component, item.identity): item for item in (*facts.accounting_carry, *plan.carry)}
            before = pricing_impact(facts.terms, facts)
            basis_entries: tuple[tuple[Literal['client', 'subsidy', 'payroll'], str, int | None], ...] = (
                    ('client', facts.case_no, before.client_amount),
                    ('subsidy', facts.case_no, before.subsidy_return_amount),
                    *(('payroll', person.assignment_identity, None) for person in facts.historical_people))
            for component, identity, basis in basis_entries:
                prior = bases.get((component, identity))
                bases[(component, identity)] = HistoricalAccountingCarry(component, identity,
                    prior.basis_amount if prior else basis,
                    tuple(dict.fromkeys((*(prior.pending if prior else ()), code))),
                    prior.financial_sources_digest if prior else plan.financial_sources_digest,
                    prior.subsidy_claim_basis if prior else before.subsidy_amount if component == 'subsidy' else None)
            plan = replace(plan, client_updates=(), staff_updates=(), carry=tuple(bases.values()),
                client_delta=None, subsidy_delta=None,
                persons=tuple(replace(person, after_amount=None, delta=None) for person in plan.persons),
                pending=tuple(dict.fromkeys((*plan.pending, code))))
    fingerprint = fingerprint_payload(pricing_payload({'case_no': case_no, 'facts_versions': facts.versions,
        'revision': facts.revision, 'before': before_birth_count, 'after': after_birth_count,
        'terms': terms, 'plan': plan}))
    return HistoricalBirthCorrectionPreview(fingerprint, plan, facts, terms, before_birth_count, after_birth_count)


def apply_historical_birth_correction(connection, *, preview: HistoricalBirthCorrectionPreview,
        actor: str, reason: str, idempotency_key: str) -> None:
    current = preview_historical_birth_correction(connection, case_no=preview.facts.case_no,
        before_birth_count=preview.before_birth_count, after_birth_count=preview.after_birth_count, for_update=True)
    if current.fingerprint != preview.fingerprint:
        raise PricingConflict('case_pricing_preview_stale')
    MySqlPricingConfigurationRepository(connection).save_case(
        replace(current.facts, historical_plan=current.impact), current.terms, actor, reason,
        'historical-birth-pricing:' + idempotency_key)


class MySqlPricingConfigurationRepository:
    def __init__(self, connection):
        self.connection = connection
        self.accounting_pending: tuple[str, ...] = ()

    def historical_plan(self, facts: CasePricingFacts, terms: CasePricingTerms, *, lock: bool) -> HistoricalRepricingPlan:
        resolved = 'historical_pricing_birth_bound_policy_required'
        facts = replace(facts, accounting_carry=tuple(replace(item,
            pending=tuple(code for code in item.pending if code != resolved)) for item in facts.accounting_carry))
        return replace(historical_repricing_plan(self.connection, facts, terms, lock=lock), rate_authority='manual')

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
        payload = _object(row["result_json"])
        self.accounting_pending = tuple(payload.get('accounting_pending', ()))
        return int(payload["revision"])

    def save_receipt(self, key, actor, command_hash, revision):
        with self.connection.cursor() as cursor:
            cursor.execute("INSERT INTO accounting_pricing_receipts(idempotency_key,command_hash,actor,result_json,created_at_utc) VALUES(%s,%s,%s,%s,UTC_TIMESTAMP(6))",
                (key, command_hash, actor, json.dumps({"revision": revision, 'accounting_pending': self.accounting_pending})))

    def save_policy(self, policy, revision, actor, reason):
        self.accounting_pending = ()
        with self.connection.cursor() as cursor:
            cursor.execute("INSERT INTO accounting_pricing_policies(id,effective_on,policy_json,actor,reason,created_at_utc) VALUES(%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))",
                (revision, policy.effective_on, _json(policy), actor, reason))
            cursor.execute("UPDATE accounting_pricing_state SET revision=%s WHERE singleton_id=1 AND revision=%s", (revision, revision-1))
            if cursor.rowcount != 1:
                raise PricingConflict("pricing_policy_stale")

    def reporting_case_total_amount(self, case_no: str) -> int:
        """Read customer pricing without the repricing writer's payroll prerequisites."""
        from domains.client_finance.pricing_policy import calculate_case_total_amount
        from infrastructure.mysql.order_terms_read_model import select_order
        from subsystems.client_finance.pricing_configuration import case_total_amount

        with self.connection.cursor() as cursor:
            order = select_order(cursor, case_no, lock=False)
            if str(order["status"]) not in {
                "歷史訂單－服務中", "歷史訂單－服務完成", "歷史訂單－帳務完成",
            }:
                return case_total_amount(self.case(case_no))
            cursor.execute("SELECT current_event_id FROM historical_service_day_projections WHERE case_no=%s", (case_no,))
            projection = cursor.fetchone()
            if projection is None:
                # Preserve the original single-assignment baseline and its protections.
                return case_total_amount(self.case(case_no))
            cursor.execute(
                "SELECT i.actual_service_days FROM historical_service_day_projections p "
                "JOIN historical_service_day_items i ON i.event_id=p.current_event_id "
                "WHERE p.case_no=%s", (case_no,),
            )
            items = tuple(cursor.fetchall())
            if not items:
                raise ValueError("case_pricing_service_facts_required")
            days = sum(int(item["actual_service_days"]) for item in items)
            if days <= 0 or any(int(item["actual_service_days"]) <= 0 for item in items):
                raise ValueError("case_pricing_service_facts_required")
            terms = load_case_pricing(cursor, order, lock=False)
            if terms is None:
                cursor.execute(
                    "SELECT client_hourly_rate_ntd FROM client_payment_terms WHERE case_no=%s",
                    (case_no,),
                )
                payment_terms = cursor.fetchone()
                if payment_terms is None or payment_terms["client_hourly_rate_ntd"] is None:
                    raise ValueError("historical_client_payment_terms_missing")
                rate = int(payment_terms["client_hourly_rate_ntd"])
                if rate <= 0:
                    raise ValueError("historical_client_payment_terms_missing")
                rule, cap = _legacy_rule_and_cap(str(order["client_identity_status"]))
                rates = HourlyRates(rate, rate)
                terms = CasePricingTerms(str(order["client_identity_status"]), rule, cap, rates, rates)
            if (order["service_hours_per_day"] is None or order["floor_fee"] is None
                    or order["service_days"] is None or int(order["service_days"]) <= 0):
                raise ValueError("case_pricing_service_facts_required")
            hours = Decimal(str(order["service_hours_per_day"])) * days
            floor = prorate_historical_floor_fee(MoneyNTD(int(order["floor_fee"])), int(order["service_days"]), days)
            return calculate_case_total_amount(terms, ((hours, False),), floor.amount)

    def case_for_query(self, case_no: str) -> CasePricingFacts | CasePricingKnownTerms:
        from infrastructure.mysql.order_terms_read_model import select_order

        try:
            return self.case(case_no)
        except ValueError as error:
            if str(error) != 'client_finance_bootstrap_required':
                raise
            with self.connection.cursor() as cursor:
                order = select_order(cursor, case_no, lock=False)
                terms = load_case_pricing(cursor, order)
            if terms is None:
                raise
            source = "manual" if order.get("pricing_override_event_id") else "policy"
            return CasePricingKnownTerms(
                case_no=case_no,
                revision=int(order.get("pricing_revision", 0)),
                terms=terms,
                source=source,
                case_total_amount=query_case_pricing_total(self.connection, case_no),
                historical=str(order["status"]).startswith('歷史'),
                accounting_pending=(str(error),),
            )

    def case(self, case_no, *, lock=False):
        from infrastructure.mysql.order_terms_read_model import load_calculable_client_finance_facts, select_order
        with self.connection.cursor() as cursor:
            order = select_order(cursor, case_no, lock=lock)
            historical = load_historical_pricing_facts(self.connection, case_no, lock=lock, order=order,
                readback=True)
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
            from infrastructure.mysql.holiday_repricing import load_frozen_holiday_amounts, load_frozen_holiday_case_total
            frozen = load_frozen_holiday_amounts(cursor, case_no, lock=lock)
            shortening = find_service_shortening_pricing_basis(cursor, order, lock=lock) if frozen is not None else None
            frozen_total = load_frozen_holiday_case_total(cursor, case_no, shortening=shortening) if frozen is not None else None
            from infrastructure.mysql.payroll_rebuild_repository import _load_obligations
            staff_obligations = _load_obligations(cursor, case_no, lock)
            formal_staff = sum(int(row["effective_contractual_amount_ntd"]) for row in staff_obligations) if staff_obligations else None
        return CasePricingFacts(case_no, int(order.get("pricing_revision", 0)),
            (int(order["lifecycle_version"]), finance.account_version, int(payroll["aggregate_version"]) if payroll else -1,
                int(scheduling["aggregate_version"]) if scheduling else -1), terms,
            "manual" if order.get("pricing_override_event_id") else "policy" if order.get("pricing_policy_id") else "legacy",
            tuple(PricingServiceDay(day.service_date, Decimal(str(finance.service_hours_per_day)), day.is_double_pay,
                day.holiday_hours, day.holiday_hour_segments) for day in finance.charge_days),
            finance.floor_fee.amount,
            sum(item.adjustment_total.amount for item in payroll_source.payroll.source_terms) if payroll_source else 0,
            legacy_amount, frozen_amounts=frozen, frozen_case_total=frozen_total, formal_staff_amount=formal_staff,
            formal_client_amount=sum(item.contracted_amount.amount for item in finance.existing_obligations) if finance.existing_obligations else None)

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
            if not identity_reclassification and not facts.historical and before.subsidy_amount != after.subsidy_amount:
                cursor.execute("SELECT m.receipt_id,m.amount_ntd AS member_amount_ntd,e.amount_ntd,e.paid_on FROM government_subsidy_period_members m "
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
            plan = facts.historical_plan
            if facts.historical and plan is None:
                plan = historical_repricing_plan(self.connection, facts, terms, lock=True)
            self.accounting_pending = plan.pending if plan is not None else ()
            payload = pricing_payload(terms)
            if plan is not None:
                payload['historical_accounting'] = pricing_payload(plan)
            cursor.execute("INSERT INTO case_pricing_events(case_no,resulting_revision,pricing_json,actor,reason,created_at_utc) VALUES(%s,%s,%s,%s,%s,UTC_TIMESTAMP(6))",
                (facts.case_no, facts.revision+1, _json(payload), actor, reason))
            event_id = int(cursor.lastrowid)
            cursor.execute("UPDATE orders SET pricing_override_event_id=%s,pricing_revision=pricing_revision+1,lifecycle_version=lifecycle_version+1 WHERE case_no=%s AND pricing_revision=%s",
                (event_id, facts.case_no, facts.revision))
            if cursor.rowcount != 1:
                raise PricingConflict("case_pricing_stale")
            if facts.historical or facts.historical_service_hours is not None:
                plan = plan or historical_repricing_plan(self.connection, facts, terms)
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
