"""Application acknowledgements, arrangement history and case markers; no money mutations."""
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pymysql.err import IntegrityError
from domains.finance_import.statement_archive import ArrangementEvent, CaseArrangement, SubsidyPlanEvent, CaseSubsidyPlan

from subsystems.finance_import.accounting_workspace import HistoricalAccountingMarker, HistoricalAccountingAmount, AccountingConflict


def build_accounting_workspace(connection):
    """One composition for the case page, payable export and original owner writers."""
    from functools import partial
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting
    from infrastructure.mysql.client_payments_query_repository import query_case_accounting, query_case_funding
    from infrastructure.mysql.monthly_accounting_repository import MySqlMonthlyAccountingSource
    from infrastructure.mysql.government_subsidy_period_repository import MySqlGovernmentSubsidyPeriodRepository
    from subsystems.finance_import.accounting_workspace import AccountingWorkspace
    state = MySqlAccountingWorkspaceState(connection)
    return AccountingWorkspace(state, partial(query_case_accounting, connection),
        partial(query_case_staff_accounting, connection), MySqlMonthlyAccountingSource(connection).case_bank_facts,
        lambda case_no: MySqlGovernmentSubsidyPeriodRepository(connection).case_coverage(case_no)['amount_ntd'],
        partial(query_case_funding, connection), plan=state.subsidy_plan)


class MySqlAccountingWorkspaceState:
    def __init__(self, connection):
        self.connection = connection

    def case_client(self, case_no):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT c.name FROM orders o JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s", (case_no,))
            row = cursor.fetchone()
        if row is None:
            raise LookupError("accounting_case_not_found")
        return str(row["name"])

    def lock_arrangement_case(self, case_no):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT case_no FROM orders WHERE case_no=%s FOR UPDATE", (case_no,))
            row = cursor.fetchone()
            if row is None or row["case_no"] != case_no:
                raise LookupError("accounting_case_not_found")

    def subsidy_plan(self, case_no):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT version,scheme,actor,UNIX_TIMESTAMP(created_at) created_epoch FROM finance_case_subsidy_plan_events WHERE case_no=%s ORDER BY version", (case_no,))
            events = tuple(SubsidyPlanEvent(int(row["version"]), row["scheme"], row["actor"], datetime.fromtimestamp(int(row["created_epoch"]), timezone.utc).isoformat()) for row in cursor.fetchall())
        return CaseSubsidyPlan(case_no, events[-1].version if events else 0, events)

    def subsidy_plan_command(self, key):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT case_no,version,scheme,actor FROM finance_case_subsidy_plan_events WHERE operation_key=%s", (key,))
            row = cursor.fetchone()
        return None if row is None else (row["case_no"], int(row["version"])-1, row["scheme"], row["actor"])

    def append_subsidy_plan(self, case_no, version, scheme, actor, key):
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("INSERT INTO finance_case_subsidy_plan_events(case_no,version,scheme,actor,operation_key) VALUES (%s,%s,%s,%s,%s)", (case_no,version,scheme,actor,key))
        except IntegrityError as error:
            if error.args[0] == 1062:
                raise AccountingConflict("subsidy_plan_version_changed") from None
            raise

    def arrangement(self, case_no):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT version,action,reason,actor,UNIX_TIMESTAMP(created_at) created_epoch FROM finance_case_arrangement_events WHERE case_no=%s ORDER BY version", (case_no,))
            events = tuple(ArrangementEvent(int(row["version"]), row["action"], row["reason"], row["actor"], datetime.fromtimestamp(int(row["created_epoch"]), timezone.utc).isoformat()) for row in cursor.fetchall())
        return CaseArrangement(case_no, events[-1].version if events else 0, events)

    def arrangement_command(self, key):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT case_no,version,action,reason,actor FROM finance_case_arrangement_events WHERE operation_key=%s", (key,))
            row = cursor.fetchone()
        return None if row is None else (row["case_no"], int(row["version"])-1, row["action"], row["reason"], row["actor"])

    def append_arrangement(self, case_no, version, action, reason, actor, key):
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("INSERT INTO finance_case_arrangement_events(case_no,version,action,reason,actor,operation_key) VALUES (%s,%s,%s,%s,%s,%s)",
                    (case_no, version, action, reason, actor, key))
        except IntegrityError as error:
            if error.args[0] == 1062:
                raise AccountingConflict("arrangement_version_changed") from None
            raise

    def marker(self, case_no):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT case_no,reason,actor,created_at,accounting_snapshot FROM finance_case_accounting_markers WHERE case_no=%s", (case_no,))
            row = cursor.fetchone()
        if row is None:
            return None
        snapshot = row["accounting_snapshot"]
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        return HistoricalAccountingMarker(row["case_no"], row["reason"], row["actor"], str(row["created_at"]), tuple(HistoricalAccountingAmount(**item) for item in snapshot["amounts"]))

    def marker_command(self, key):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT case_no,reason,actor,source_versions FROM finance_case_accounting_markers WHERE operation_key=%s", (key,))
            row = cursor.fetchone()
        if row is None:
            return None
        versions = row["source_versions"]
        return row["case_no"], row["reason"], row["actor"], json.loads(versions) if isinstance(versions, str) else versions

    def mark(self, case_no, reason, actor, versions, key, amounts):
        with self.connection.cursor() as cursor:
            try:
                cursor.execute("INSERT INTO finance_case_accounting_markers(case_no,reason,actor,source_versions,operation_key,accounting_snapshot) VALUES (%s,%s,%s,%s,%s,%s)", (case_no, reason, actor, json.dumps(versions, sort_keys=True), key, json.dumps({"amounts": [asdict(item) for item in amounts]}, sort_keys=True)))
            except IntegrityError as error:
                if error.args[0] == 1062:
                    raise AccountingConflict("historical_accounting_already_marked") from None
                raise

    def dismissed(self, case_no, *, for_update=False):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT item_identity,warning_kind,difference_ntd,actor,created_at FROM finance_accounting_dismissals WHERE case_no=%s OR item_identity LIKE 'staff-overpayment:%%'" + (" FOR UPDATE" if for_update else ""), (case_no,))
            rows = cursor.fetchall()
        return {(row["item_identity"], row["warning_kind"], int(row["difference_ntd"])): (row["actor"], str(row["created_at"])) for row in rows}

    def payment_cases(self):
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT case_no FROM client_ledger_entries UNION "
                "SELECT o.case_no FROM staff_payable_projections p JOIN staff_obligations o "
                "ON o.obligation_identity=p.obligation_identity ORDER BY case_no"
            )
            return tuple(row["case_no"] for row in cursor.fetchall())

    def dismiss(self, case_no, warning, actor):
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO finance_accounting_dismissals(case_no,item_identity,warning_kind,difference_ntd,source_version,actor) VALUES (%s,%s,%s,%s,%s,%s)",
                (case_no, warning.item_identity, warning.kind, warning.difference_ntd, warning.source_version, actor),
            )

    def begin(self):
        self.connection.begin()

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()


def query_subsidy_payable_handoff(connection, case_no):
    """Borrow current Orders, owner money facts and the last saved plan; query only."""
    from domains.staff_payables.subsidy_handoff import SubsidyHandoffFacts, decide_subsidy_handoff
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT o.status,EXISTS(SELECT 1 FROM client_obligations b "
            "WHERE b.case_no=o.case_no AND b.obligation_type='subsidy_return' "
            "AND b.direction='payable_to_client' AND b.status='open' AND b.amount_due_ntd>0) "
            "AS has_customer_subsidy_payable FROM orders o WHERE o.case_no=%s", (case_no,))
        row = cursor.fetchone()
    if row is None:
        raise LookupError('accounting_case_not_found')
    case = build_accounting_workspace(connection).query(case_no)
    from infrastructure.mysql.client_payments_query_repository import query_case_funding
    funding = query_case_funding(connection, case_no)
    total = case.staff_receivable_ntd if case.staff_receivable_ntd is not None else (funding.total_ntd if funding else None)
    stages = tuple(item for item in case.client_items if item.payment_stage in {'deposit', 'first', 'second'})
    cash = case.cash_by_flow
    customer_paid = (sum(item.actual_ntd for item in stages)
                     if {item.payment_stage for item in stages} == {'deposit', 'first', 'second'} else None)
    if customer_paid is not None and cash is not None:
        customer_paid -= cash['RS']
    staff = tuple(item for item in case.staff_items if item.direction == 'payable' and item.summary_included)
    return decide_subsidy_handoff(SubsidyHandoffFacts(
        case.subsidy_plan.selected_scheme if case.subsidy_plan is not None else None,
        case.scheme, case.scheme_conflict, str(row['status']), total,
        case.subsidy_ntd, case.customer_amount_ntd, customer_paid,
        sum(item.actual_ntd for item in staff) if staff else None,
        None if cash is None else cash['PT'], None if cash is None else cash['RT'],
        None if cash is None else cash['G'], bool(row['has_customer_subsidy_payable']),
        funding.full_subsidy if funding is not None else False,
        funding is not None and case.staff_receivable_ntd is not None and funding.total_ntd != case.staff_receivable_ntd))
