"""Application acknowledgements, arrangement history and case markers; no money mutations."""
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pymysql.err import IntegrityError
from domains.finance_import.statement_archive import ArrangementEvent, CaseArrangement, SubsidyPlanEvent, CaseSubsidyPlan

from subsystems.finance_import.accounting_workspace import CaseBankMemo, HistoricalAccountingMarker, HistoricalAccountingAmount, AccountingConflict
from domains.finance_import.cancellation_code import extract_sinopac_memo_case_suffix
from subsystems.client_finance.virtual_account_resolution import resolve_case_virtual_account, resolve_client_virtual_account_suffix


def build_accounting_workspace(connection):
    """One composition for the case page, payable export and original owner writers."""
    from functools import partial
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting
    from infrastructure.mysql.client_payments_query_repository import query_cancellation_accounting, query_case_accounting, query_case_payment_terms
    from infrastructure.mysql.monthly_accounting_repository import MySqlMonthlyAccountingSource
    from infrastructure.mysql.government_subsidy_period_repository import query_case_subsidy_amount
    from subsystems.finance_import.accounting_workspace import AccountingWorkspace
    from infrastructure.mysql.subsidy_confirmation_repository import preview_manual_subsidy_plan, apply_manual_subsidy_plan
    state = MySqlAccountingWorkspaceState(connection)
    return AccountingWorkspace(state, partial(query_case_accounting, connection),
        partial(query_case_staff_accounting, connection), MySqlMonthlyAccountingSource(connection).case_bank_facts,
        lambda case_no: query_case_subsidy_amount(connection, case_no).amount_ntd,
        partial(query_case_payment_terms, connection), plan=state.subsidy_plan,
        cancellation=partial(query_cancellation_accounting, connection),
        bank_memos=partial(query_case_bank_memos, connection),
        subsidy_plan_preview=partial(preview_manual_subsidy_plan, connection),
        subsidy_plan_apply=partial(apply_manual_subsidy_plan, connection))


def query_case_bank_memos(connection, case_no):
    """Read original Taishin notes under the canonical case account; no cash inference."""
    with connection.cursor() as cursor:
        account = resolve_case_virtual_account(cursor, case_no)
        if account['result'] != 'resolved' or not account['virtual_account']:
            return ()
        suffix = account['virtual_account'][-6:]
        resolution = resolve_client_virtual_account_suffix(cursor, suffix)
        if resolution['result'] != 'resolved' or resolution['case_no'] != case_no:
            return ()
        fullwidth = suffix.translate(str.maketrans('0123456789', '０１２３４５６７８９'))
        cursor.execute(
            "SELECT id,transaction_date,memo FROM finance_import_rows "
            "WHERE format_id='taishin' AND direction='outgoing' "
            "AND (memo LIKE %s OR memo LIKE %s) ORDER BY transaction_date,id",
            (f'%{suffix}%', f'%{fullwidth}%'),
        )
        rows = cursor.fetchall()
        result = []
        for row in rows:
            if extract_sinopac_memo_case_suffix(row['memo']) != suffix:
                continue
            occurred = row['transaction_date']
            result.append(CaseBankMemo(f"finance-import-row:{row['id']}",
                occurred.isoformat() if hasattr(occurred, 'isoformat') else str(occurred) if occurred else None,
                row['memo']))
        return tuple(result)


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
            cursor.execute("SELECT version,scheme,actor,operation_key,UNIX_TIMESTAMP(created_at) created_epoch FROM finance_case_subsidy_plan_events WHERE case_no=%s ORDER BY version", (case_no,))
            events = tuple(SubsidyPlanEvent(int(row["version"]), row["scheme"], row["actor"],
                datetime.fromtimestamp(int(row["created_epoch"]), timezone.utc).isoformat(),
                'bank' if str(row['operation_key']).startswith('bank-subsidy:') else 'manual',
                'finance-import-row:' + row['operation_key'].split(':')[1]
                if str(row['operation_key']).startswith('bank-subsidy:') else None)
                for row in cursor.fetchall())
        return CaseSubsidyPlan(case_no, events[-1].version if events else 0, events)

    def subsidy_plan_command(self, key):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT case_no,version,scheme,actor FROM finance_case_subsidy_plan_events WHERE operation_key=%s", (key,))
            row = cursor.fetchone()
        return None if row is None else (row["case_no"], int(row["version"])-1, row["scheme"], row["actor"])

    def append_subsidy_plan(self, case_no, version, scheme, actor, key, *, bank_row_id=None):
        # The reserved operation namespace binds a bank confirmation to immutable
        # source evidence using the existing append-only event/uniqueness owner.
        # Public/manual writers cannot manufacture bank provenance.
        if bank_row_id is None and key.startswith('bank-subsidy:'):
            raise ValueError('reserved_subsidy_confirmation_key')
        if bank_row_id is not None:
            from hashlib import sha256
            if not isinstance(bank_row_id, int) or isinstance(bank_row_id, bool) or bank_row_id <= 0:
                raise ValueError('subsidy_bank_row_invalid')
            key = f'bank-subsidy:{bank_row_id}:' + sha256(key.encode()).hexdigest()
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


def query_subsidy_payable_handoff(connection, case_no, *, proposed_scheme=None, payroll_candidate_total=None):
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
    funding = case.funding
    staff_total = case.staff_receivable_ntd
    if staff_total is None:
        staff_total = payroll_candidate_total
    total = staff_total if staff_total is not None else (funding.total_ntd if funding else None)
    cash = case.cash_by_flow
    customer_paid = case.customer_paid_ntd
    if customer_paid is not None and cash is not None:
        customer_paid -= cash['RS']
    staff = tuple(item for item in case.staff_items if item.direction == 'payable' and item.summary_included)
    return decide_subsidy_handoff(SubsidyHandoffFacts(
        proposed_scheme if proposed_scheme is not None else case.subsidy_plan.selected_scheme if case.subsidy_plan is not None else None,
        case.scheme, case.scheme_conflict, str(row['status']), total,
        case.subsidy_ntd, case.customer_amount_ntd, customer_paid,
        sum(item.actual_ntd for item in staff) if staff else None,
        None if cash is None else cash['PT'], None if cash is None else cash['RT'],
        None if cash is None else cash['G'], bool(row['has_customer_subsidy_payable']),
        funding.full_subsidy if funding is not None else False,
        funding is not None and staff_total is not None and funding.total_ntd != staff_total,
        'bank' if proposed_scheme is not None else case.subsidy_plan.confirmation_source if case.subsidy_plan else None))
