"""
File: historical_service_accounting_repository.py
Description: 支援計次歷史服務帳務的 MySQL 持久化儲存與查詢配接器。
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import date, datetime, time
from decimal import Decimal
import json
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from domains.bootstrap.case_architecture import payroll_policy_kind_for_case
from domains.client_finance.subsidy_coverage import normalize_subsidy_policy_identity
from domains.orders.lifecycle import OrderLifecycleStatus
from domains.orders.lifecycle import LifecycleImpactCandidate
from domains.orders.historical_service_accounting import HistoricalAssignmentServiceFact
from domains.payroll.calculation import DEFAULT_PAYROLL_POLICY_VERSION, AssignmentRateSnapshot, PayrollPolicyKind
from domains.scheduling.generation import AssignmentIdentityResolution
from infrastructure.mysql.effective_case_service_rate import BIRTH_COUNT_JOINS, BIRTH_COUNT_SQL
from infrastructure.mysql.historical_assignment_writer import MySqlHistoricalAssignmentWriter
from infrastructure.mysql.order_lifecycle_impact_writer import persist_order_lifecycle_impact, persist_order_lifecycle_projection
from infrastructure.mysql.order_terms_read_model import (
    _select_case_payroll_policy, _select_staff_obligations, _staff_obligation,
    lock_staff_mutexes, select_current_assignments, select_order,
)
from infrastructure.mysql.payroll_terms_writer import persist_payroll_terms_impact
from infrastructure.mysql.staff_payout_repository import query_staff_funding_portions
from infrastructure.mysql.staff_payable_correction_sql import effective_staff_obligation_amount
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.orders.historical_service_accounting_workflow import (
    HistoricalServiceAccountingAssignmentFacts,
    HistoricalAttributionIntent,
    HistoricalAttributionPreview,
    HistoricalServiceAccountingBaseline,
    HistoricalServiceFactsCorrectionCandidate,
    HistoricalServiceAccountingFacts,
    HistoricalServiceAccountingReceipt,
    StoredHistoricalServiceAccountingReceipt,
    _command_fingerprint,
)
from subsystems.orders.terms_workflow import LifecycleImpactPersistenceCommand, PayrollImpactPersistenceCommand
from subsystems.payroll.terms_impact import CasePayrollPolicyTerms, PayrollTermsSourceFacts, SourceAssignmentPayrollTerms
from subsystems.client_finance.pricing_configuration import pricing_payload

class MySqlHistoricalServiceAccountingRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load(self, case_no: str, *, for_update: bool) -> HistoricalServiceAccountingFacts:
        lock = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(_ROOT_SQL + lock, (case_no,))
            root = cursor.fetchone()
            if root is None:
                raise ValueError("historical_order_not_found")
            if (
                root["client_policy_version"] is None
                or root["client_hourly_rate_ntd"] is None
            ):
                from infrastructure.mysql.pricing_configuration_repository import load_case_pricing
                order = select_order(cursor, case_no, lock=for_update)
                terms = load_case_pricing(cursor, order, lock=for_update)
                if terms is None:
                    raise ValueError("historical_client_payment_terms_missing")
                rate = terms.client.covered if terms.client.covered > 0 else terms.client.excess
                if rate <= 0:
                    raise ValueError("historical_client_payment_terms_missing")
                root = {**root,
                    "client_policy_version": f"case-pricing:{order.get('pricing_policy_id')}:{order.get('pricing_override_event_id')}",
                    "client_hourly_rate_ntd": rate,
                }
            cursor.execute(_ASSIGNMENTS_SQL + lock, (case_no, int(root["adoption_receipt_id"])))
            rows = tuple(cursor.fetchall())
            if any(row["payroll_policy_version"] is None for row in rows):
                policy = _select_historical_default_payroll_policy(cursor, case_no, for_update)
                rows = tuple(
                    row if row["payroll_policy_version"] is not None else {
                        **row,
                        "payroll_policy_version": policy.policy_version,
                        "payroll_policy_kind": policy.policy_kind.value,
                        "payroll_hourly_rate_ntd": policy.hourly_rate.amount,
                    }
                    for row in rows
                )
            adjustment_rows = _load_adjustments(
                cursor,
                tuple(int(row["assignment_id"]) for row in rows),
                lock,
            )
        adjustments = {
            int(row["assignment_id"]): MoneyNTD(int(row["amount_ntd"]))
            for row in adjustment_rows
        }
        snapshot = _object(root["day_result_snapshot"]) if root.get("day_result_snapshot") else {}
        service_facts = {
            item.assignment_identity: item for item in (
                _service_fact(value) for value in snapshot.get("service_facts", ())
            )
        }
        assignments = [
            HistoricalServiceAccountingAssignmentFacts(
                f"assignment:{int(row['assignment_id'])}",
                int(row["staff_id"]),
                str(row["staff_name"]),
                AssignmentRateSnapshot(
                    f"assignment:{int(row['assignment_id'])}",
                    str(row["payroll_policy_version"]),
                    PayrollPolicyKind(str(row["payroll_policy_kind"])),
                    MoneyNTD(int(row["payroll_hourly_rate_ntd"])),
                ),
                adjustments.get(int(row["assignment_id"]), MoneyNTD(0)),
                (int(row["actual_service_days"]) if row.get("actual_service_days") is not None
                 else int(root["service_days"]) if len(rows) == 1 else None),
                (Decimal(str(row["actual_service_hours"])) if row.get("actual_service_hours") is not None
                 else Decimal(str(root["service_hours_per_day"])) * int(root["service_days"]) if len(rows) == 1 else None),
                service_facts.get(f"assignment:{int(row['assignment_id'])}"),
                row.get("assigned_start_date"), row.get("assigned_end_date"),
            )
            for row in rows
        ]
        return HistoricalServiceAccountingFacts(
            str(root["case_no"]),
            OrderLifecycleStatus(str(root["status"])),
            int(root["lifecycle_version"]),
            int(root["adoption_receipt_id"]),
            str(root["source_event_identity"]),
            int(root["historical_day_revision"]),
            int(root["client_finance_version"]),
            int(root["payroll_version"]),
            int(root["service_days"]),
            Decimal(str(root["service_hours_per_day"])),
            MoneyNTD(int(root["floor_fee"])),
            str(root["identity_status"]),
            tuple(sorted(assignments, key=lambda item: item.assignment_identity)),
            str(root["client_policy_version"]),
            MoneyNTD(int(root["client_hourly_rate_ntd"])),
            _date_value(root["completed_on"]),
            _optional_date_value(root["staff_payment_due_date"]),
            bool(root.get("attribution_adopted", False)),
            tuple(_object(root["day_result_snapshot"]).get("accounting_pending", ())) if root.get("day_result_snapshot") else (),
            (HistoricalServiceAccountingBaseline(
                int(root["day_event_id"]), int(root["day_total_actual_service_days"]),
                Decimal(str(root["day_total_actual_service_hours"])), int(root["day_historical_floor_fee_ntd"]),
                int(root["day_client_obligation_amount_ntd"]), int(root["day_staff_obligation_amount_ntd"]),
            ) if root.get("day_event_id") is not None else None),
        )

    def find_receipt(self, key):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT command_fingerprint,result_snapshot FROM historical_service_day_events "
                "WHERE idempotency_key=%s FOR UPDATE",
                (key.value,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        payload = _object(row["result_snapshot"])
        return StoredHistoricalServiceAccountingReceipt(
            PreviewFingerprint(str(row["command_fingerprint"])),
            HistoricalServiceAccountingReceipt(
                str(payload["case_no"]),
                int(payload["resulting_historical_day_revision"]),
                int(payload["resulting_client_finance_version"]),
                int(payload["resulting_payroll_version"]),
                int(payload["total_actual_service_days"]),
                int(payload["client_obligation_amount_ntd"]),
                int(payload["staff_obligation_amount_ntd"]),
                PreviewFingerprint(str(payload["preview_fingerprint"])),
                accounting_pending=tuple(payload.get("accounting_pending", ())),
            ),
        )

    def lock_attribution_order(self, case_no):
        with _cursor(self._connection) as cursor:
            select_order(cursor, case_no, lock=True)

    def preview_service_volume(self, case_no: str, before: dict[str, Decimal], after: dict[str, Decimal], *, for_update: bool):
        from infrastructure.mysql.pricing_configuration_repository import preview_historical_service_volume_correction
        return preview_historical_service_volume_correction(
            self._connection, case_no=case_no, before_hours_by_assignment=before,
            after_hours_by_assignment=after, for_update=for_update,
        )

    def load_attribution(self, case_no, staff_ids, *, for_update):
        suffix = " FOR UPDATE" if for_update else ""
        facts = self.load(case_no, for_update=for_update)
        with _cursor(self._connection) as cursor:
            if facts.lifecycle_status not in {
                OrderLifecycleStatus.HISTORICAL_IN_SERVICE, OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
                OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
            }:
                raise ValueError("historical_order_lifecycle_transition_invalid")
            current = select_current_assignments(cursor, case_no, None)
            if not current or {f"assignment:{row['id']}" for row in current} != {
                item.assignment_identity for item in facts.assignments
            }:
                raise ValueError("historical_attribution_assignment_conflict")
            impacted = tuple(sorted(set(staff_ids) | {item.staff_id for item in facts.assignments}))
            if for_update:
                lock_staff_mutexes(cursor, impacted)
            placeholders = ",".join("%s" for _ in impacted)
            cursor.execute(
                f"SELECT staff_id,aggregate_version FROM staff_payable_accounts WHERE staff_id IN ({placeholders}) "
                "ORDER BY staff_id" + suffix, impacted,
            )
            payable_versions = tuple((int(row["staff_id"]), int(row["aggregate_version"])) for row in cursor.fetchall())
            cursor.execute(f"SELECT id,name FROM staff WHERE id IN ({placeholders})" + suffix, impacted)
            people = {int(row["id"]): str(row["name"]) for row in cursor.fetchall()}
            if people.keys() != set(impacted):
                raise ValueError("historical_attribution_staff_missing")
            cursor.execute("SELECT aggregate_version FROM payroll_case_accounts WHERE case_no=%s" + suffix, (case_no,))
            account = cursor.fetchone()
            obligations = tuple(_staff_obligation(row) for row in _select_staff_obligations(cursor, case_no, for_update))
            cursor.execute(
                "SELECT p.obligation_identity FROM historical_staff_payout_projections p "
                "JOIN staff_obligations o ON o.obligation_identity=p.obligation_identity "
                "WHERE o.case_no=%s AND o.status<>'cancelled'" + suffix, (case_no,),
            )
            historical_payouts = {row["obligation_identity"] for row in cursor.fetchall()}
            pending = ()
            if any(item.obligation_identity in historical_payouts and (
                not item.historically_settled or not item.payout_history_exists
                or item.paid_net_amount.amount != item.contractual_amount.amount
                or item.paid_net_amount.amount <= 0
            ) for item in obligations):
                pending = ("historical_attribution_actual_payout_evidence_missing",)
            previous_funding = []
            funded = set()
            for item in obligations:
                if item.obligation_kind.value != "service_pay":
                    continue
                cursor.execute(
                    "SELECT " + effective_staff_obligation_amount() + " AS entitlement "
                    "FROM staff_obligations obligations WHERE obligation_identity=%s" + suffix,
                    (item.obligation_identity,),
                )
                entitlement = int(cursor.fetchone()["entitlement"])
                portions = query_staff_funding_portions(
                    cursor, item.obligation_identity, lock=for_update,
                    settled_total=item.paid_net_amount.amount,
                    amount_total=entitlement,
                )
                if portions:
                    if any(portion.settled_ntd is None for portion in portions):
                        raise ValueError("historical_attribution_source_payout_evidence_missing")
                    if item.staff_id in funded:
                        raise ValueError("historical_attribution_funding_review_required")
                    funded.add(item.staff_id)
                    previous_funding.extend((item.staff_id, portion) for portion in portions)
            if funded and any(item.paid_net_amount.amount and item.staff_id not in funded for item in obligations):
                raise ValueError("historical_attribution_source_payout_evidence_missing")
            cursor.execute(
                "SELECT c.obligation_identity,o.staff_id,c.computed_ntd,c.effective_ntd,c.settlement_base_ntd "
                "FROM payroll_amount_controls c JOIN staff_obligations o ON o.obligation_identity=c.obligation_identity "
                "WHERE o.case_no=%s AND o.status<>'cancelled' AND c.amount_mode='manual' ORDER BY c.obligation_identity"
                + suffix, (case_no,),
            )
            controls = tuple(cursor.fetchall())
            by_identity = {item.obligation_identity: item for item in obligations}
            for control in controls:
                obligation = by_identity.get(control["obligation_identity"])
                if (obligation is None or obligation.obligation_kind.value != "service_pay"
                        or obligation.payout_history_exists or obligation.historically_settled
                        or control["settlement_base_ntd"] is not None):
                    raise ValueError("historical_attribution_paid_manual_review_required")
            manual_amounts = tuple(
                (str(row["obligation_identity"]), int(row["staff_id"]), int(row["computed_ntd"]), int(row["effective_ntd"]))
                for row in controls
            )
            if account is None and obligations:
                raise ValueError("payroll_bootstrap_required")
            policy = _select_case_payroll_policy(cursor, case_no, for_update, required=False)
            if policy is None:
                policy = _select_historical_default_payroll_policy(cursor, case_no, for_update)
            source = PayrollTermsSourceFacts(
                case_no, int(account["aggregate_version"]) if account else 0,
                tuple(SourceAssignmentPayrollTerms(
                    _assignment_id(item.assignment_identity), item.staff_id, item.rate_snapshot.policy_version,
                    item.rate_snapshot.policy_kind, adjustment_total=item.effective_adjustment,
                    hourly_rate=item.rate_snapshot.hourly_rate,
                ) for item in facts.assignments),
                tuple(replace(item, historically_settled=False) if item.historically_settled else item
                      for item in obligations),
                facts.staff_payment_due_date, policy,
            )
            if source.staff_payment_due_date is None:
                from subsystems.payroll.historical_baseline_obligation_sync import _funding_schedule
                funding = _funding_schedule(self._connection, case_no, {
                    "actual_end_date": facts.completed_on, "staff_payment_due_date": None,
                }, 1)
                if funding is None or funding[1]:
                    raise ValueError("historical_attribution_funding_review_required")
                source = replace(source, staff_payment_due_date=funding[0])
            cursor.execute("SELECT total_actual_service_days FROM historical_service_day_projections WHERE case_no=%s" + suffix, (case_no,))
            projection = cursor.fetchone()
        return (facts, source, int(projection["total_actual_service_days"]) if projection else facts.contracted_service_days,
                people, payable_versions, manual_amounts, tuple(previous_funding), pending)

    def persist_attribution(self, intent, preview, command, *, actor, reason, key, correlation):
        candidate = preview.comparison
        facts = candidate.facts
        if isinstance(candidate, HistoricalServiceFactsCorrectionCandidate):
            return self._persist_partial_service_facts(intent, preview, command, actor=actor,
                                                       reason=reason, key=key, correlation=correlation)
        assignments = {}
        if preview.volume_repricing is not None:
            from infrastructure.mysql.pricing_configuration_repository import persist_historical_repricing
            persist_historical_repricing(self._connection, preview.volume_repricing, actor.actor_id, reason, key.value)
        additions = tuple(item for item in facts.assignments if item.assignment_identity.startswith("new-staff:"))
        with _cursor(self._connection) as cursor:
            order = select_order(cursor, facts.case_no, lock=True)
            current = select_current_assignments(cursor, facts.case_no, None)
            if additions:
                start = min(item["assigned_start_date"] for item in current)
                end = max(item["assigned_end_date"] for item in current)
                ids = MySqlHistoricalAssignmentWriter(self._connection).append_completed_assignments(
                    facts.case_no, tuple((item.staff_id, start, end) for item in additions),
                )
                for item, assignment_id in zip(additions, ids, strict=True):
                    assignments[item.assignment_identity] = assignment_id
                    rate = item.rate_snapshot
                    cursor.execute(
                        "INSERT INTO assignment_payroll_rate_snapshots(assignment_id,policy_version,policy_kind,"
                        "hourly_rate_ntd,source_identity_status) VALUES(%s,%s,%s,%s,'case-policy')",
                        (assignment_id, rate.policy_version, rate.policy_kind.value, rate.hourly_rate.amount),
                    )
            for item in facts.assignments:
                if item.assignment_identity not in assignments:
                    assignments[item.assignment_identity] = _assignment_id(item.assignment_identity)
            mapped = {key: f"assignment:{value}" for key, value in assignments.items()}
            mapped_candidate = replace(
                candidate,
                facts=replace(facts,
                    client_finance_version=(preview.volume_repricing.client_version + int(preview.volume_repricing.client_changed)
                                            if preview.volume_repricing else facts.client_finance_version),
                    payroll_version=(preview.volume_repricing.payroll_version + int(preview.volume_repricing.payroll_changed)
                                     if preview.volume_repricing and preview.volume_repricing.payroll_version is not None
                                     else preview.payroll.resulting_payroll_version if preview.payroll else facts.payroll_version),
                    assignments=tuple(sorted((
                        replace(item, assignment_identity=mapped[item.assignment_identity],
                                rate_snapshot=replace(item.rate_snapshot, assignment_identity=mapped[item.assignment_identity]))
                        for item in facts.assignments
                    ), key=lambda item: item.assignment_identity))),
                service_days=replace(candidate.service_days, allocations=tuple(
                    replace(item, assignment_identity=mapped[item.assignment_identity])
                    for item in candidate.service_days.allocations
                )),
                payroll=replace(candidate.payroll, assignments=tuple(
                    replace(item, assignment_identity=mapped[item.assignment_identity])
                    for item in candidate.payroll.assignments
                )),
                fingerprint=preview.fingerprint,
            )
            request = SimpleNamespace(idempotency_key=key, actor=actor, reason=reason, correlation_id=correlation)
            receipt = self.persist(request, mapped_candidate, command_fingerprint=command.value,
                                   evidence=intent.evidence, funding=preview.funding,
                                   original_funding=preview.original_funding, accounting_pending=preview.accounting_pending,
                                   financial_plan=preview.volume_repricing)
            if preview.reopen:
                self._reopen_attribution(cursor, order, facts, preview, key, actor, reason, correlation)
            if preview.payroll is None:
                return receipt
            cursor.execute("INSERT IGNORE INTO payroll_case_accounts(case_no) VALUES(%s)", (facts.case_no,))
            cursor.execute("SELECT current_event_id FROM historical_service_day_projections WHERE case_no=%s FOR UPDATE", (facts.case_no,))
            source_event_id = int(cursor.fetchone()["current_event_id"])
            by_staff = {item.staff_id: assignments[item.assignment_identity] for item in facts.assignments}
            resolution = AssignmentIdentityResolution({
                item.assignment_identity: by_staff[item.staff_id] for item in preview.payroll.payroll.assignments
            })
            persist_payroll_terms_impact(cursor, PayrollImpactPersistenceCommand(
                preview.payroll, resolution, key, actor, reason, correlation,
                source_event_id, reuse_existing_assignments=True,
                replace_unpaid_amount_controls=tuple(item[0] for item in preview.manual_amounts),
            ))
            for staff_id, funding_kind, amount, _, due_date in preview.funding:
                cursor.execute(
                    "SELECT obligation_identity FROM staff_obligations WHERE case_no=%s AND assignment_id=%s "
                    "AND obligation_kind='service_pay' AND status='open' FOR UPDATE",
                    (facts.case_no, by_staff[staff_id]),
                )
                roots = tuple(cursor.fetchall())
                if len(roots) != 1:
                    raise ValueError("historical_attribution_funding_root_conflict")
                cursor.execute(
                    "INSERT INTO staff_obligation_installments(obligation_identity,funding_kind,amount_ntd,due_date) "
                    "VALUES(%s,%s,%s,%s) ON DUPLICATE KEY UPDATE amount_ntd=VALUES(amount_ntd),due_date=VALUES(due_date)",
                    (roots[0]["obligation_identity"], funding_kind, amount, due_date),
                )
        return receipt

    def _reopen_attribution(self, cursor, order, facts, preview, key, actor, reason, correlation):
        locked = bool(order["service_data_locked"])
        lifecycle = LifecycleImpactCandidate(
            facts.case_no, facts.lifecycle_status, OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
            order["actual_end_date"], None, datetime.now(ZoneInfo("Asia/Taipei")).date(),
            False, locked, locked, (), preview.fingerprint,
        )
        command = LifecycleImpactPersistenceCommand(
            lifecycle, facts.lifecycle_version, facts.lifecycle_version + 1, None, key,
            actor, reason, correlation, "historical_accounting_reopened",
        )
        persist_order_lifecycle_impact(cursor, command)
        persist_order_lifecycle_projection(cursor, command)

    def _persist_partial_service_facts(
        self, intent: HistoricalAttributionIntent, preview: HistoricalAttributionPreview,
        command: PreviewFingerprint, *, actor: ActorContext, reason: str,
        key: IdempotencyKey, correlation: CorrelationId,
    ) -> HistoricalServiceAccountingReceipt:
        from infrastructure.mysql.pricing_configuration_repository import persist_historical_repricing
        candidate = preview.comparison
        if not isinstance(candidate, HistoricalServiceFactsCorrectionCandidate):
            raise TypeError("partial service facts candidate required")
        facts = candidate.facts
        baseline = facts.service_baseline
        plan = preview.volume_repricing
        if baseline is None or plan is None:
            raise ValueError("historical_completed_service_partial_baseline_required")
        persist_historical_repricing(self._connection, plan, actor.actor_id, reason, key.value)
        receipt = HistoricalServiceAccountingReceipt(
            facts.case_no, facts.historical_day_revision + 1,
            plan.client_version + int(plan.client_changed),
            (plan.payroll_version + int(plan.payroll_changed) if plan.payroll_version is not None else facts.payroll_version),
            baseline.total_actual_service_days, baseline.client_obligation_amount_ntd,
            baseline.staff_obligation_amount_ntd, preview.fingerprint, accounting_pending=preview.accounting_pending,
        )
        snapshot = {
            **_receipt_payload(receipt), "comparison_amounts_basis": "preserved_incomplete_attribution_baseline",
            "comparison_baseline_event_id": baseline.event_id,
            "financial_correction": pricing_payload(plan), "service_attribution_evidence": intent.evidence,
            "service_facts": tuple(item.canonical_payload() for item in candidate.service_facts),
            "accounting_pending": preview.accounting_pending,
        }
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO historical_service_day_events "
                "(event_identity,case_no,historical_adoption_receipt_id,expected_day_revision,"
                "resulting_day_revision,total_actual_service_days,total_actual_service_hours,"
                "historical_floor_fee_ntd,client_obligation_amount_ntd,staff_obligation_amount_ntd,"
                "preview_fingerprint,command_fingerprint,idempotency_key,actor_id,reason,correlation_id,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (f"historical-service-days-pending:{command.value}", facts.case_no, facts.adoption_receipt_id,
                 facts.historical_day_revision, receipt.resulting_historical_day_revision,
                 baseline.total_actual_service_days, baseline.total_actual_service_hours,
                 baseline.historical_floor_fee_ntd, baseline.client_obligation_amount_ntd,
                 baseline.staff_obligation_amount_ntd, preview.fingerprint.value, command.value,
                 key.value, actor.actor_id, reason, correlation.value, _json(snapshot)),
            )
            event_id = int(cursor.lastrowid)
            selected = {item.assignment_identity: item for item in intent.service_facts}
            hour_cases: list[str] = []
            hour_parameters: list[int | Decimal] = []
            for item in facts.assignments:
                if item.actual_service_days is not None and item.assignment_identity in selected:
                    hour_cases.append("WHEN assignment_id=%s AND staff_id=%s THEN %s*actual_service_days")
                    hour_parameters.extend((_assignment_id(item.assignment_identity), item.staff_id,
                                            selected[item.assignment_identity].service_hours_per_day))
            hours_sql = ("CASE " + " ".join(hour_cases) + " ELSE actual_service_hours END"
                         if hour_cases else "actual_service_hours")
            cursor.execute(
                "INSERT INTO historical_service_day_items "
                "(event_id,assignment_id,staff_id,item_ordinal,actual_service_days,actual_service_hours,"
                "floor_fee_allocated_ntd,staff_obligation_amount_ntd,payroll_policy_version,payroll_policy_kind,hourly_rate_ntd) "
                "SELECT %s,assignment_id,staff_id,item_ordinal,actual_service_days," + hours_sql + ","
                "floor_fee_allocated_ntd,staff_obligation_amount_ntd,payroll_policy_version,payroll_policy_kind,hourly_rate_ntd "
                "FROM historical_service_day_items WHERE event_id=%s",
                (event_id, *hour_parameters, baseline.event_id),
            )
            cursor.execute(
                "UPDATE historical_service_day_projections SET current_event_id=%s,day_revision=%s WHERE case_no=%s",
                (event_id, receipt.resulting_historical_day_revision, facts.case_no),
            )
        return receipt

    def persist(self, request, candidate, *, command_fingerprint=None, evidence=None, funding=(), original_funding=(), accounting_pending=(), financial_plan=None):
        resulting_day_revision = candidate.facts.historical_day_revision + 1
        receipt = HistoricalServiceAccountingReceipt(
            candidate.facts.case_no,
            resulting_day_revision,
            candidate.facts.client_finance_version,
            candidate.facts.payroll_version,
            candidate.service_days.total_actual_service_days,
            candidate.client_finance.total_receivable.amount,
            candidate.payroll.total_payable.amount,
            candidate.fingerprint,
            accounting_pending=accounting_pending,
        )
        result_snapshot = _receipt_payload(receipt)
        if financial_plan is not None:
            result_snapshot["comparison_amounts_basis"] = "legacy_rate_snapshot_comparison_only"
            result_snapshot["financial_correction"] = pricing_payload(financial_plan)
        periods = tuple(item.service_fact.canonical_payload() for item in candidate.service_days.allocations
                        if item.service_fact is not None)
        if periods:
            result_snapshot["service_facts"] = periods
        if evidence is not None:
            result_snapshot["service_attribution_evidence"] = evidence
        if accounting_pending:
            result_snapshot["accounting_pending"] = accounting_pending
        elif evidence is not None and candidate.facts.accounting_pending:
            result_snapshot["resolved_accounting_pending_day_revision"] = candidate.facts.historical_day_revision
        if funding:
            result_snapshot["funding_attribution"] = tuple((*row[:-1], row[-1].isoformat() if row[-1] else None) for row in funding)
            result_snapshot["original_funding_attribution"] = tuple(
                (*row[:-1], row[-1].isoformat() if row[-1] else None) for row in original_funding
            )
        command_fingerprint = command_fingerprint or _command_fingerprint(request).value
        kind = "historical-service-days-pending" if accounting_pending else "historical-service-days"
        event_identity = f"{kind}:{command_fingerprint}"
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO historical_service_day_events "
                "(event_identity,case_no,historical_adoption_receipt_id,expected_day_revision,"
                "resulting_day_revision,total_actual_service_days,total_actual_service_hours,"
                "historical_floor_fee_ntd,client_obligation_amount_ntd,staff_obligation_amount_ntd,"
                "preview_fingerprint,command_fingerprint,idempotency_key,actor_id,reason,correlation_id,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    event_identity,
                    candidate.facts.case_no,
                    candidate.facts.adoption_receipt_id,
                    candidate.facts.historical_day_revision,
                    resulting_day_revision,
                    candidate.service_days.total_actual_service_days,
                    candidate.service_days.total_actual_service_hours,
                    candidate.service_days.historical_floor_fee_ntd,
                    candidate.client_finance.total_receivable.amount,
                    candidate.payroll.total_payable.amount,
                    candidate.fingerprint.value,
                    command_fingerprint,
                    request.idempotency_key.value,
                    request.actor.actor_id,
                    request.reason,
                    request.correlation_id.value,
                    _json(result_snapshot),
                ),
            )
            event_id = int(cursor.lastrowid)
            _insert_items(cursor, event_id, candidate)
            cursor.execute(
                "INSERT INTO historical_service_day_projections "
                "(case_no,current_event_id,historical_adoption_receipt_id,day_revision,total_actual_service_days,total_actual_service_hours) "
                "VALUES (%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "current_event_id=VALUES(current_event_id),historical_adoption_receipt_id=VALUES(historical_adoption_receipt_id),"
                "day_revision=VALUES(day_revision),total_actual_service_days=VALUES(total_actual_service_days),"
                "total_actual_service_hours=VALUES(total_actual_service_hours)",
                (
                    candidate.facts.case_no,
                    event_id,
                    candidate.facts.adoption_receipt_id,
                    resulting_day_revision,
                    candidate.service_days.total_actual_service_days,
                    candidate.service_days.total_actual_service_hours,
                ),
            )
            if not accounting_pending:
                cursor.execute(
                    "INSERT INTO historical_service_accounting_outbox "
                    "(event_id,intent_key,intent_type,bounded_snapshot) VALUES (%s,%s,'historical_service_accounting_applied',%s)",
                    (event_id, f"{request.idempotency_key.value}:applied", _json(result_snapshot)),
                )
        return receipt


def _select_historical_default_payroll_policy(cursor, case_no, lock):
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT c.identity_status,"
        f"{BIRTH_COUNT_SQL} AS multi_birth_count FROM orders o JOIN clients c ON c.id=o.client_id"
        + BIRTH_COUNT_JOINS + " WHERE o.case_no=%s" + suffix,
        (case_no,),
    )
    order = cursor.fetchone()
    identity = normalize_subsidy_policy_identity(order["identity_status"])
    kind = payroll_policy_kind_for_case(
        "補助市民" if identity == "原住民" else identity,
        order["multi_birth_count"],
    )
    cursor.execute(
        "SELECT hourly_rate_ntd FROM payroll_rate_policies WHERE policy_version=%s AND policy_kind=%s" + suffix,
        (DEFAULT_PAYROLL_POLICY_VERSION, kind.value),
    )
    rate = cursor.fetchone()
    if rate is None:
        raise ValueError("historical_payroll_rate_policy_missing")
    return CasePayrollPolicyTerms(DEFAULT_PAYROLL_POLICY_VERSION, kind, MoneyNTD(int(rate["hourly_rate_ntd"])))


def _insert_items(cursor, event_id, candidate):
    payroll = {item.assignment_identity: item for item in candidate.payroll.assignments}
    facts = {item.assignment_identity: item for item in candidate.facts.assignments}
    rows = []
    for ordinal, allocation in enumerate(candidate.service_days.allocations, start=1):
        assignment = facts[allocation.assignment_identity]
        payable = payroll[allocation.assignment_identity]
        rows.append((
            event_id,
            _assignment_id(allocation.assignment_identity),
            allocation.staff_id,
            ordinal,
            allocation.actual_service_days,
            allocation.actual_service_hours,
            allocation.floor_fee_ntd,
            payable.total_payable.amount,
            assignment.rate_snapshot.policy_version,
            assignment.rate_snapshot.policy_kind.value,
            assignment.rate_snapshot.hourly_rate.amount,
        ))
    cursor.executemany(
        "INSERT INTO historical_service_day_items "
        "(event_id,assignment_id,staff_id,item_ordinal,actual_service_days,actual_service_hours,"
        "floor_fee_allocated_ntd,staff_obligation_amount_ntd,payroll_policy_version,payroll_policy_kind,hourly_rate_ntd) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        rows,
    )


def _assignment_id(identity):
    value = str(identity).removeprefix("assignment:")
    if not value.isdigit() or int(value) <= 0:
        raise ValueError("historical_actual_service_days_assignment_mismatch")
    return int(value)


def _receipt_payload(receipt):
    return {
        "case_no": receipt.case_no,
        "resulting_historical_day_revision": receipt.resulting_historical_day_revision,
        "resulting_client_finance_version": receipt.resulting_client_finance_version,
        "resulting_payroll_version": receipt.resulting_payroll_version,
        "total_actual_service_days": receipt.total_actual_service_days,
        "client_obligation_amount_ntd": receipt.client_obligation_amount_ntd,
        "staff_obligation_amount_ntd": receipt.staff_obligation_amount_ntd,
        "preview_fingerprint": receipt.preview_fingerprint.value,
    }


def _object(value):
    result = json.loads(value) if isinstance(value, str) else value
    if not isinstance(result, dict):
        raise ValueError("historical_accounting_obligation_binding_invalid")
    return result


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@contextmanager
def _cursor(connection):
    cursor = connection.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


def _date_value(value) -> date:
    if not isinstance(value, date):
        raise ValueError("historical_order_completion_date_missing")
    return value


def _optional_date_value(value) -> date | None:
    if value is None:
        return None
    return _date_value(value)


def _service_fact(value: dict[str, object]) -> HistoricalAssignmentServiceFact:
    return HistoricalAssignmentServiceFact(
        str(value["assignment_identity"]), int(value["staff_id"]),
        date.fromisoformat(str(value["actual_start_date"])), date.fromisoformat(str(value["actual_end_date"])),
        time.fromisoformat(str(value["service_start_time"])), time.fromisoformat(str(value["service_end_time"])),
        Decimal(str(value["service_hours_per_day"])), int(value.get("service_end_day_offset", 0)),
    )


_ROOT_SQL = (
    "SELECT o.case_no,o.status,o.lifecycle_version,o.service_days,o.service_hours_per_day,o.floor_fee,"
    "COALESCE(o.actual_end_date,o.end_date) AS completed_on,o.staff_payment_due_date,"
    "c.identity_status,COALESCE(client_account.aggregate_version,0) AS client_finance_version,"
    "COALESCE(payroll_account.aggregate_version,0) AS payroll_version,receipt.id AS adoption_receipt_id,"
    "receipt.source_event_identity,COALESCE(day_projection.day_revision,0) AS historical_day_revision,"
    "client_terms.policy_version AS client_policy_version,client_terms.client_hourly_rate_ntd,"
    "JSON_CONTAINS_PATH(day_event.result_snapshot,'one','$.service_attribution_evidence') AS attribution_adopted,"
    "day_event.result_snapshot AS day_result_snapshot,"
    "day_event.id AS day_event_id,day_event.total_actual_service_days AS day_total_actual_service_days,"
    "day_event.total_actual_service_hours AS day_total_actual_service_hours,"
    "day_event.historical_floor_fee_ntd AS day_historical_floor_fee_ntd,"
    "day_event.client_obligation_amount_ntd AS day_client_obligation_amount_ntd,"
    "day_event.staff_obligation_amount_ntd AS day_staff_obligation_amount_ntd "
    "FROM orders o JOIN clients c ON c.id=o.client_id "
    "LEFT JOIN client_finance_accounts client_account ON client_account.case_no=o.case_no "
    "LEFT JOIN payroll_case_accounts payroll_account ON payroll_account.case_no=o.case_no "
    "LEFT JOIN client_payment_terms client_terms ON client_terms.case_no=o.case_no "
    "JOIN historical_order_adoption_receipts receipt ON receipt.id=("
    "SELECT MAX(r.id) FROM historical_order_adoption_receipts r WHERE r.case_no=o.case_no AND r.outcome='adopted') "
    "LEFT JOIN historical_service_day_projections day_projection ON day_projection.case_no=o.case_no "
    "LEFT JOIN historical_service_day_events day_event ON day_event.id=day_projection.current_event_id "
    "WHERE o.case_no=%s"
)
_ASSIGNMENTS_SQL = (
    "SELECT assignment.id AS assignment_id,assignment.staff_id,staff.name AS staff_name,"
    "assignment.assigned_start_date,assignment.assigned_end_date,"
    "day_item.actual_service_days,day_item.actual_service_hours,"
    "COALESCE(rate.policy_version,case_rate.policy_version) AS payroll_policy_version,"
    "COALESCE(rate.policy_kind,case_rate.policy_kind) AS payroll_policy_kind,"
    "COALESCE(rate.hourly_rate_ntd,case_rate.hourly_rate_ntd) AS payroll_hourly_rate_ntd "
    "FROM case_staff_assignments assignment JOIN staff ON staff.id=assignment.staff_id "
    "LEFT JOIN case_payroll_rate_policy_snapshots case_rate ON case_rate.case_no=assignment.case_no "
    "LEFT JOIN assignment_payroll_rate_snapshots rate ON rate.assignment_id=assignment.id "
    "LEFT JOIN historical_service_day_projections day_projection ON day_projection.case_no=assignment.case_no "
    "LEFT JOIN historical_service_day_items day_item ON day_item.event_id=day_projection.current_event_id "
    "AND day_item.assignment_id=assignment.id AND day_item.staff_id=assignment.staff_id "
    "WHERE assignment.case_no=%s AND assignment.generation_id IS NULL "
    "AND assignment.status IN ('planned','active','completed') AND ("
    "EXISTS(SELECT 1 FROM historical_order_pairing_evidence evidence "
    "WHERE evidence.receipt_id=%s AND evidence.assignment_id=assignment.id AND evidence.staff_id=assignment.staff_id) "
    "OR EXISTS(SELECT 1 FROM historical_service_day_projections p "
    "JOIN historical_service_day_items i ON i.event_id=p.current_event_id "
    "WHERE p.case_no=assignment.case_no AND i.assignment_id=assignment.id AND i.staff_id=assignment.staff_id)) "
    "ORDER BY assignment.id"
)


def _load_adjustments(cursor, assignment_ids, lock):
    if not assignment_ids:
        return ()
    placeholders = ",".join("%s" for _ in assignment_ids)
    cursor.execute(
        "SELECT assignment_id,COALESCE(SUM(amount_ntd),0) AS amount_ntd "
        "FROM payroll_adjustment_allocations WHERE assignment_id IN ("
        + placeholders
        + ") GROUP BY assignment_id"
        + lock,
        assignment_ids,
    )
    return tuple(cursor.fetchall())


__all__ = ["MySqlHistoricalServiceAccountingRepository"]
