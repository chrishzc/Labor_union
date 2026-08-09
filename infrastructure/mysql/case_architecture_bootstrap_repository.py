"""MySQL persistence for canonical first-use case bootstrap."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from domains.bootstrap.case_architecture import (
    BootstrapDomainError,
    BootstrapIssue,
    BootstrapMutation,
    BootstrapPresence,
    CaseArchitectureBootstrapCandidate,
    CaseArchitectureBootstrapFacts,
    CaseArchitectureBootstrapIntent,
    CaseRootFacts,
    PayrollPolicyKind,
    RatePolicyFacts,
    policy_kind_for_identity,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.bootstrap.case_architecture_workflow import (
    CaseArchitectureBootstrapReceipt,
    CommandClaimState,
    EnsureCaseArchitectureBootstrap,
    StoredCaseArchitectureBootstrapReceipt,
)

_COMMAND_FAMILY = "case_architecture_bootstrap"


class MySqlCaseArchitectureBootstrapRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_for_preview(
        self,
        intent: CaseArchitectureBootstrapIntent,
    ) -> CaseArchitectureBootstrapFacts:
        with self._connection.cursor() as cursor:
            return _load_facts(cursor, intent, lock=False)

    def load_for_ensure(
        self,
        intent: CaseArchitectureBootstrapIntent,
    ) -> CaseArchitectureBootstrapFacts:
        with self._connection.cursor() as cursor:
            return _load_facts(cursor, intent, lock=True)

    def claim_command(
        self,
        command: EnsureCaseArchitectureBootstrap,
        command_fingerprint: PreviewFingerprint,
    ) -> CommandClaimState:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CLAIM_INSERT_SQL,
                (
                    command.idempotency_key.value,
                    _COMMAND_FAMILY,
                    command.intent.case_no,
                    command_fingerprint.value,
                    command.correlation_id.value,
                ),
            )
            if cursor.rowcount == 1:
                return CommandClaimState.CREATED
            row = _select_claim(cursor, command.idempotency_key)
        return _claim_state(command, command_fingerprint, row)

    def find_receipt(
        self,
        key: IdempotencyKey,
        *,
        for_update: bool,
    ) -> StoredCaseArchitectureBootstrapReceipt | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL + suffix, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_receipt(row)

    # Kept cohesive because this order is the single bootstrap transaction map.
    def create_bootstrap(
        self,
        command: EnsureCaseArchitectureBootstrap,
        candidate: CaseArchitectureBootstrapCandidate,
    ) -> int:
        with self._connection.cursor() as cursor:
            _insert_accounts(cursor, candidate)
            terms_event_id = _insert_client_payment_terms(
                cursor,
                command,
                candidate,
            )
            bootstrap_event_id = _insert_bootstrap_event(
                cursor,
                command,
                candidate,
                terms_event_id,
            )
            _insert_payroll_policy_snapshot(
                cursor,
                candidate,
                bootstrap_event_id,
            )
            return bootstrap_event_id

    def existing_bootstrap_event_id(self, case_no: str) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM case_architecture_bootstrap_events "
                "WHERE case_no=%s FOR UPDATE",
                (case_no,),
            )
            row = cursor.fetchone()
        if not isinstance(row, Mapping):
            raise RuntimeError("case_architecture_bootstrap_event_missing")
        return int(row["id"])

    def save_receipt(
        self,
        key: IdempotencyKey,
        stored: StoredCaseArchitectureBootstrapReceipt,
    ) -> None:
        receipt = stored.receipt
        with self._connection.cursor() as cursor:
            cursor.execute(
                _RECEIPT_INSERT_SQL,
                _receipt_insert_values(key, stored),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    "case_architecture_bootstrap_receipt_insert_failed"
                )


def _load_facts(cursor, intent, *, lock):
    order_row = _select_order(cursor, intent.case_no, lock)
    policy_kind = policy_kind_for_identity(str(order_row["identity_status"]))
    policy_row = _select_rate_policy(
        cursor,
        intent.payroll_policy_version,
        policy_kind,
        lock,
    )
    presence = _load_presence(cursor, intent.case_no, lock)
    return CaseArchitectureBootstrapFacts(
        order=_order_facts(order_row),
        payroll_rate_policy=_rate_policy(policy_row),
        presence=presence,
    )


def _select_order(cursor, case_no, lock):
    cursor.execute(_ORDER_SELECT_SQL + _lock_suffix(lock), (case_no,))
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise BootstrapDomainError(
            BootstrapIssue.CASE_NOT_FOUND,
            "The case does not exist.",
        )
    return row


def _select_rate_policy(cursor, version, policy_kind, lock):
    cursor.execute(
        _RATE_POLICY_SELECT_SQL + _lock_suffix(lock),
        (version, policy_kind.value),
    )
    return cursor.fetchone()


# Kept cohesive so partial-state detection reads the complete component set.
def _load_presence(cursor, case_no, lock):
    rows = tuple(
        _select_optional_row(cursor, statement, case_no, lock)
        for statement in _PRESENCE_SELECT_SQL
    )
    root_event = _select_root_event(cursor, case_no, lock)
    scheduling = rows[4]
    return BootstrapPresence(
        client_finance_account=rows[0] is not None,
        client_payment_terms=rows[1] is not None,
        payroll_case_account=rows[2] is not None,
        payroll_case_policy=rows[3] is not None,
        scheduling_aggregate=scheduling is not None,
        scheduling_version=_scheduling_value(
            scheduling,
            "aggregate_version",
        ),
        scheduling_generation=_scheduling_value(
            scheduling,
            "generation_counter",
        ),
        root_event_fingerprint=(
            PreviewFingerprint(str(root_event["candidate_fingerprint"]))
            if isinstance(root_event, Mapping)
            else None
        ),
        components_consistent=_components_consistent(rows, root_event),
    )


def _select_optional_row(cursor, statement, case_no, lock):
    cursor.execute(
        statement + _lock_suffix(lock),
        (case_no,),
    )
    row = cursor.fetchone()
    return row if isinstance(row, Mapping) else None


def _select_root_event(cursor, case_no, lock):
    cursor.execute(
        "SELECT id,client_payment_terms_event_id,client_policy_version,"
        "client_hourly_rate_ntd,payroll_policy_version,"
        "payroll_policy_kind,payroll_hourly_rate_ntd,"
        "source_identity_status,candidate_fingerprint "
        "FROM case_architecture_bootstrap_events WHERE case_no=%s"
        + _lock_suffix(lock),
        (case_no,),
    )
    return cursor.fetchone()


def _components_consistent(rows, root_event) -> bool:
    if not isinstance(root_event, Mapping):
        return True
    if any(row is None for row in rows):
        return False
    client_account, client_terms, payroll_account, payroll_policy, scheduling = rows
    return all(
        (
            int(client_account["aggregate_version"]) == 0,
            _client_terms_are_consistent(client_terms, root_event),
            int(payroll_account["aggregate_version"]) == 0,
            _payroll_policy_is_consistent(payroll_policy, root_event),
            _scheduling_is_generation_zero(scheduling),
        )
    )


# Kept cohesive so the immutable event and current projection are compared whole.
def _client_terms_are_consistent(terms, root_event) -> bool:
    return all(
        (
            int(terms["current_event_id"])
            == int(root_event["client_payment_terms_event_id"]),
            str(terms["policy_version"]) == str(terms["event_policy_version"]),
            str(terms["event_policy_version"])
            == str(root_event["client_policy_version"]),
            int(terms["client_hourly_rate_ntd"])
            == int(terms["event_client_hourly_rate_ntd"]),
            int(terms["event_client_hourly_rate_ntd"])
            == int(root_event["client_hourly_rate_ntd"]),
            int(terms["deposit_service_days"])
            == int(terms["event_deposit_service_days"]),
            terms["deposit_due_date"] == terms["event_deposit_due_date"],
            terms["first_payment_due_date"]
            == terms["event_first_payment_due_date"],
            terms["second_payment_due_date"]
            == terms["event_second_payment_due_date"],
            int(terms["event_expected_account_version"]) == 0,
        )
    )


def _payroll_policy_is_consistent(policy, root_event) -> bool:
    return all(
        (
            int(policy["source_event_id"]) == int(root_event["id"]),
            str(policy["policy_version"])
            == str(root_event["payroll_policy_version"]),
            str(policy["policy_kind"])
            == str(root_event["payroll_policy_kind"]),
            int(policy["hourly_rate_ntd"])
            == int(root_event["payroll_hourly_rate_ntd"]),
            str(policy["source_identity_status"])
            == str(root_event["source_identity_status"]),
        )
    )


def _scheduling_is_generation_zero(scheduling) -> bool:
    return all(
        (
            int(scheduling["aggregate_version"]) >= 0,
            int(scheduling["generation_counter"]) >= 0,
        )
    )


def _scheduling_value(scheduling, field_name) -> int:
    if not isinstance(scheduling, Mapping):
        return 0
    return int(scheduling[field_name])


def _order_facts(row):
    _require_order_numeric_root(row, "service_days")
    _require_order_numeric_root(row, "service_hours_per_day")
    return CaseRootFacts(
        case_no=str(row["case_no"]),
        order_version=int(row["lifecycle_version"]),
        planned_start_date=row["start_date"],
        service_days=int(row["service_days"]),
        service_hours_per_day=int(row["service_hours_per_day"]),
        source_identity_status=str(row["identity_status"]),
    )


def _require_order_numeric_root(row, field_name) -> None:
    value = row[field_name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise BootstrapDomainError(
            BootstrapIssue.INVALID_ROOT_FACTS,
            f"{field_name} must be an integer root fact.",
        )


def _rate_policy(row):
    if not isinstance(row, Mapping):
        return None
    return RatePolicyFacts(
        policy_version=str(row["policy_version"]),
        policy_kind=PayrollPolicyKind(str(row["policy_kind"])),
        hourly_rate=MoneyNTD(_integer_ntd(row["hourly_rate_ntd"])),
        effective_from=row["effective_from"],
        effective_until=row["effective_until"],
    )


# Kept cohesive because the missing Domain roots form one bootstrap invariant.
def _insert_accounts(cursor, candidate) -> None:
    statements = (
        (
            "INSERT INTO client_finance_accounts "
            "(case_no,aggregate_version) VALUES (%s,0)",
            (candidate.case_no,),
        ),
        (
            "INSERT INTO payroll_case_accounts "
            "(case_no,aggregate_version) VALUES (%s,0)",
            (candidate.case_no,),
        ),
        (
            "INSERT INTO scheduling_aggregates "
            "(case_no,aggregate_version,generation_counter,"
            "effective_generation_id) VALUES (%s,0,0,NULL)",
            (candidate.case_no,),
        ),
    )
    required_statements = (
        statements
        if candidate.mutation is BootstrapMutation.CREATE
        else statements[:2]
    )
    for statement, parameters in required_statements:
        cursor.execute(statement, parameters)
        if cursor.rowcount != 1:
            raise RuntimeError("case_architecture_account_insert_failed")


# Kept cohesive because the root event and current terms row are inseparable.
def _insert_client_payment_terms(cursor, command, candidate):
    terms = candidate.client_payment_terms
    cursor.execute(
        _PAYMENT_TERMS_EVENT_INSERT_SQL,
        (
            candidate.case_no,
            terms.policy_version,
            terms.client_hourly_rate.amount,
            terms.deposit_service_days,
            terms.deposit_due_date,
            terms.first_payment_due_date,
            terms.second_payment_due_date,
            0,
            f"case-bootstrap:{candidate.fingerprint.value}",
            f"bootstrap-terms:{candidate.fingerprint.value}",
            command.actor.actor_id,
            command.reason,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("client_payment_terms_event_insert_failed")
    event_id = int(cursor.lastrowid)
    _insert_current_client_payment_terms(cursor, candidate, event_id)
    return event_id


def _insert_current_client_payment_terms(cursor, candidate, event_id):
    terms = candidate.client_payment_terms
    cursor.execute(
        _PAYMENT_TERMS_INSERT_SQL,
        (
            candidate.case_no,
            terms.policy_version,
            terms.client_hourly_rate.amount,
            terms.deposit_service_days,
            terms.deposit_due_date,
            terms.first_payment_due_date,
            terms.second_payment_due_date,
            event_id,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("client_payment_terms_insert_failed")


def _insert_payroll_policy_snapshot(cursor, candidate, bootstrap_event_id):
    policy = candidate.payroll_rate_policy
    cursor.execute(
        _PAYROLL_POLICY_SNAPSHOT_INSERT_SQL,
        (
            candidate.case_no,
            policy.policy_version,
            policy.policy_kind.value,
            policy.hourly_rate.amount,
            candidate.source_identity_status,
            bootstrap_event_id,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("case_payroll_policy_snapshot_insert_failed")


def _insert_bootstrap_event(cursor, command, candidate, terms_event_id):
    policy = candidate.payroll_rate_policy
    terms = candidate.client_payment_terms
    cursor.execute(
        _BOOTSTRAP_EVENT_INSERT_SQL,
        _bootstrap_event_values(
            command,
            candidate,
            terms_event_id,
            terms,
            policy,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("case_architecture_bootstrap_event_insert_failed")
    return int(cursor.lastrowid)


def _bootstrap_event_values(command, candidate, event_id, terms, policy):
    return (
        candidate.case_no,
        candidate.order_version,
        event_id,
        terms.policy_version,
        terms.client_hourly_rate.amount,
        policy.policy_version,
        policy.policy_kind.value,
        policy.hourly_rate.amount,
        candidate.source_identity_status,
        candidate.fingerprint.value,
        command.idempotency_key.value,
        command.actor.actor_id,
        command.reason,
        command.correlation_id.value,
    )


def _select_claim(cursor, key):
    cursor.execute(
        "SELECT command_family,aggregate_identity,command_fingerprint "
        "FROM application_command_claims "
        "WHERE idempotency_key=%s FOR UPDATE",
        (key.value,),
    )
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise RuntimeError("case_architecture_bootstrap_claim_missing")
    return row


def _claim_state(command, fingerprint, row):
    matches = (
        str(row["command_family"]) == _COMMAND_FAMILY
        and str(row["aggregate_identity"]) == command.intent.case_no
        and str(row["command_fingerprint"]) == fingerprint.value
    )
    return CommandClaimState.MATCHED if matches else CommandClaimState.MISMATCH


def _stored_receipt(row):
    receipt = _receipt_from_row(row)
    if _json_value(row["result_snapshot"]) != _receipt_payload(receipt):
        raise RuntimeError("case_architecture_bootstrap_receipt_corrupt")
    return StoredCaseArchitectureBootstrapReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _receipt_from_row(row):
    return CaseArchitectureBootstrapReceipt(
        case_no=str(row["case_no"]),
        order_version=int(row["order_version"]),
        client_finance_version=int(row["client_finance_version"]),
        payroll_version=int(row["payroll_version"]),
        scheduling_version=int(row["scheduling_version"]),
        scheduling_generation=int(row["scheduling_generation"]),
        bootstrap_created=bool(row["bootstrap_created"]),
        bootstrap_event_id=int(row["bootstrap_event_id"]),
        preview_fingerprint=PreviewFingerprint(
            str(row["preview_fingerprint"])
        ),
    )


def _receipt_insert_values(key, stored):
    receipt = stored.receipt
    return (
        key.value,
        stored.command_fingerprint.value,
        receipt.preview_fingerprint.value,
        receipt.case_no,
        receipt.bootstrap_event_id,
        receipt.order_version,
        receipt.client_finance_version,
        receipt.payroll_version,
        receipt.scheduling_version,
        receipt.scheduling_generation,
        int(receipt.bootstrap_created),
        _receipt_json(receipt),
    )


def _receipt_json(receipt) -> str:
    return json.dumps(
        _receipt_payload(receipt),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _receipt_payload(receipt):
    return {
        "bootstrap_created": receipt.bootstrap_created,
        "bootstrap_event_id": receipt.bootstrap_event_id,
        "case_no": receipt.case_no,
        "client_finance_version": receipt.client_finance_version,
        "order_version": receipt.order_version,
        "payroll_version": receipt.payroll_version,
        "scheduling_generation": receipt.scheduling_generation,
        "scheduling_version": receipt.scheduling_version,
    }


def _json_value(value):
    return json.loads(value) if isinstance(value, str) else value


def _integer_ntd(value) -> int:
    integer = int(value)
    if integer != value:
        raise ValueError("non_integer_payroll_input")
    return integer


def _lock_suffix(lock: bool) -> str:
    return " FOR UPDATE" if lock else ""


_ORDER_SELECT_SQL = (
    "SELECT o.case_no,o.lifecycle_version,o.start_date,o.service_days,"
    "o.service_hours_per_day,o.service_start_time,o.service_end_time,"
    "o.service_end_day_offset,c.identity_status FROM orders o "
    "JOIN clients c ON c.id=o.client_id AND c.case_no=o.case_no "
    "WHERE o.case_no=%s"
)

_RATE_POLICY_SELECT_SQL = (
    "SELECT policy_version,policy_kind,hourly_rate_ntd,effective_from,"
    "effective_until FROM payroll_rate_policies "
    "WHERE policy_version=%s AND policy_kind=%s"
)

_PRESENCE_SELECT_SQL = (
    "SELECT case_no,aggregate_version FROM client_finance_accounts "
    "WHERE case_no=%s",
    "SELECT p.case_no,p.policy_version,p.client_hourly_rate_ntd,"
    "p.deposit_service_days,p.deposit_due_date,p.first_payment_due_date,"
    "p.second_payment_due_date,p.current_event_id,"
    "e.policy_version AS event_policy_version,"
    "e.client_hourly_rate_ntd AS event_client_hourly_rate_ntd,"
    "e.deposit_service_days AS event_deposit_service_days,"
    "e.deposit_due_date AS event_deposit_due_date,"
    "e.first_payment_due_date AS event_first_payment_due_date,"
    "e.second_payment_due_date AS event_second_payment_due_date,"
    "e.expected_account_version AS event_expected_account_version "
    "FROM client_payment_terms p JOIN client_payment_terms_events e "
    "ON e.id=p.current_event_id WHERE p.case_no=%s",
    "SELECT case_no,aggregate_version FROM payroll_case_accounts "
    "WHERE case_no=%s",
    "SELECT case_no,policy_version,policy_kind,hourly_rate_ntd,"
    "source_identity_status,source_event_id "
    "FROM case_payroll_rate_policy_snapshots WHERE case_no=%s",
    "SELECT case_no,aggregate_version,generation_counter,"
    "effective_generation_id FROM scheduling_aggregates WHERE case_no=%s",
)

_CLAIM_INSERT_SQL = (
    "INSERT IGNORE INTO application_command_claims "
    "(idempotency_key,command_family,aggregate_identity,"
    "command_fingerprint,correlation_id) VALUES (%s,%s,%s,%s,%s)"
)

_PAYMENT_TERMS_EVENT_INSERT_SQL = (
    "INSERT INTO client_payment_terms_events "
    "(case_no,policy_version,client_hourly_rate_ntd,"
    "deposit_service_days,deposit_due_date,first_payment_due_date,"
    "second_payment_due_date,expected_account_version,"
    "source_event_identity,idempotency_key,actor,reason) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

_PAYMENT_TERMS_INSERT_SQL = (
    "INSERT INTO client_payment_terms "
    "(case_no,policy_version,client_hourly_rate_ntd,"
    "deposit_service_days,deposit_due_date,first_payment_due_date,"
    "second_payment_due_date,current_event_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
)

_PAYROLL_POLICY_SNAPSHOT_INSERT_SQL = (
    "INSERT INTO case_payroll_rate_policy_snapshots "
    "(case_no,policy_version,policy_kind,hourly_rate_ntd,"
    "source_identity_status,source_event_id) "
    "VALUES (%s,%s,%s,%s,%s,%s)"
)

_BOOTSTRAP_EVENT_INSERT_SQL = (
    "INSERT INTO case_architecture_bootstrap_events "
    "(case_no,order_version,client_payment_terms_event_id,"
    "client_policy_version,client_hourly_rate_ntd,"
    "payroll_policy_version,payroll_policy_kind,"
    "payroll_hourly_rate_ntd,source_identity_status,"
    "candidate_fingerprint,idempotency_key,actor,reason,correlation_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,preview_fingerprint,case_no,"
    "bootstrap_event_id,order_version,client_finance_version,"
    "payroll_version,scheduling_version,scheduling_generation,"
    "bootstrap_created,result_snapshot "
    "FROM case_architecture_bootstrap_receipts WHERE idempotency_key=%s"
)

_RECEIPT_INSERT_SQL = (
    "INSERT INTO case_architecture_bootstrap_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,case_no,"
    "bootstrap_event_id,order_version,client_finance_version,"
    "payroll_version,scheduling_version,scheduling_generation,"
    "bootstrap_created,result_snapshot) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
