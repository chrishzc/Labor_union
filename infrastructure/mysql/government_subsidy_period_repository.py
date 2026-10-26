"""Period receipt adapter. The application owns the only commit; no external effects."""
from domains.government_subsidy.period_reconciliation import (
    PeriodReconciliationConflict, SubsidyPeriod, SubsidyPeriodLine,
)
from subsystems.government_subsidy.period_reconciliation import CasePeriodCoverage, PeriodBankRow, PeriodCoverage, SubsidyPeriodView
from subsystems.government_subsidy.reconciliation_register_query import (
    _select_established_cases, project_receivable_estimate,
)


_ACTIVE = "entry.reversal_of_id IS NULL AND NOT EXISTS (SELECT 1 FROM government_subsidy_period_entries reversal WHERE reversal.reversal_of_id=entry.id)"
_RECOVERED = "(SELECT COALESCE(SUM(ledger.amount_ntd-COALESCE((SELECT SUM(reversed.amount_ntd) FROM client_ledger_entries reversed WHERE reversed.reversal_of_entry_id=ledger.id),0)),0) FROM government_subsidy_period_members member JOIN client_ledger_entries ledger ON ledger.case_no=member.case_no AND ledger.entry_type='subsidy_advance' WHERE member.receipt_id=entry.id AND ledger.occurred_on<=entry.paid_on)"


class MySqlGovernmentSubsidyPeriodRepository:
    def __init__(self, connection):
        self.connection = connection

    def query(self, period, *, lock=False):
        with self.connection.cursor() as cursor:
            if lock:
                cursor.execute('INSERT IGNORE INTO government_subsidy_period_years(period_year) VALUES (%s)', (period.year,))
            cursor.execute('SELECT aggregate_version FROM government_subsidy_period_years WHERE period_year=%s' +
                           (' FOR UPDATE' if lock else ''), (period.year,))
            root = cursor.fetchone()
            version = int(root['aggregate_version']) if root else 0
            sources = _select_established_cases(self.connection, period.start, period.end, lock=lock)
            by_case = {}
            for source in sources:
                estimate = project_receivable_estimate(source)
                line = SubsidyPeriodLine(source['case_no'], source['actual_end_date'], estimate.amount_ntd, estimate.unavailable_reason)
                if line.case_no in by_case and by_case[line.case_no] != line:
                    raise PeriodReconciliationConflict('subsidy_period_source_ambiguous')
                by_case[line.case_no] = line
            lines = tuple(by_case.values())
            cursor.execute('SELECT entry.id,entry.period_unit,entry.period_year,entry.period_index,entry.amount_ntd,'+_RECOVERED+' recovered_advance_ntd FROM government_subsidy_period_entries entry WHERE ' + _ACTIVE +
                ' AND entry.period_start<%s AND entry.period_end>%s ORDER BY entry.id', (period.end, period.start))
            coverage = tuple(PeriodCoverage(int(row['id']), SubsidyPeriod(row['period_unit'], row['period_year'], row['period_index']),
                                           int(row['amount_ntd']), int(row['recovered_advance_ntd'])) for row in cursor.fetchall())
            # A case moved to a different month/year after receipt remains attached to its immutable receipt.
            blocked = []
            if lines:
                cursor.execute('SELECT DISTINCT member.case_no FROM government_subsidy_period_members member '
                    'JOIN government_subsidy_period_entries entry ON entry.id=member.receipt_id WHERE ' + _ACTIVE +
                    ' AND member.case_no IN (' + ','.join(['%s'] * len(lines)) + ')', tuple(line.case_no for line in lines))
                blocked = [row['case_no'] for row in cursor.fetchall()]
            # Preserved legacy cash is evidence of payment, never permission to collect it again.
            cursor.execute("SELECT DISTINCT item.case_no FROM subsidy_claim_batch_items item "
                "JOIN government_subsidy_allocations allocation ON allocation.claim_item_id=item.id "
                "JOIN orders o ON o.case_no=item.case_no WHERE COALESCE(o.actual_end_date,o.end_date)>=%s "
                "AND COALESCE(o.actual_end_date,o.end_date)<%s GROUP BY item.case_no "
                "HAVING SUM(CASE WHEN allocation.allocation_type='receipt' THEN allocation.allocated_amount ELSE -allocation.allocated_amount END)>0",
                (period.start, period.end))
            blocked.extend(row['case_no'] for row in cursor.fetchall())
            cursor.execute('SELECT member.* FROM government_subsidy_period_members member '
                'JOIN government_subsidy_period_entries entry ON entry.id=member.receipt_id WHERE ' + _ACTIVE +
                ' AND member.service_end_date>=%s AND member.service_end_date<%s ORDER BY member.case_no', (period.start,period.end))
            recorded = tuple(SubsidyPeriodLine(row['case_no'],row['service_end_date'],int(row['amount_ntd']),None) for row in cursor.fetchall())
            changed = tuple(sorted(set(line.case_no for line in recorded if by_case.get(line.case_no) != line) |
                {line.case_no for line in lines if any(item.period.contains(line.service_end_date) for item in coverage)
                 and line.case_no not in {record.case_no for record in recorded}}))
        total = sum(line.amount_ntd for line in lines) if all(line.amount_ntd is not None for line in lines) else None
        return SubsidyPeriodView(period, version, lines, total, coverage, tuple(sorted(set(blocked))),recorded,changed,
                                 bool(lines) and total is not None and total > 0 and not coverage and not blocked)

    def find_replay(self, key, command):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT id,period_unit,period_year,period_index,finance_import_row_id,reversal_of_id '
                           'FROM government_subsidy_period_entries WHERE idempotency_key=%s FOR UPDATE', (key,))
            row = cursor.fetchone()
        if row is None:
            return None
        actual = tuple(row[name] for name in ('period_unit','period_year','period_index','finance_import_row_id','reversal_of_id'))
        if actual != command:
            raise PeriodReconciliationConflict('subsidy_period_idempotency_conflict')
        return int(row['id'])

    def bank_amount(self, bank_row_id, *, reversal=False):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT bank.credit,bank.debit,bank.currency,bank.transaction_date,bank.direction, '
                'COALESCE(classification.classification_type,bank.classification_type) classification_type '
                'FROM finance_import_rows bank LEFT JOIN finance_import_classification_events classification '
                'ON classification.id=(SELECT MAX(latest.id) FROM finance_import_classification_events latest '
                'WHERE latest.finance_import_row_id=bank.id) WHERE bank.id=%s FOR UPDATE', (bank_row_id,))
            row = cursor.fetchone()
            if (row is None or row['currency'] not in (None,'TWD','NTD') or row['transaction_date'] is None
                    or row['classification_type'] != 'government_subsidy'
                    or row['direction'] != ('outgoing' if reversal else 'incoming')):
                raise PeriodReconciliationConflict('subsidy_period_bank_invalid')
            amount, other = (row['debit'], row['credit']) if reversal else (row['credit'], row['debit'])
            if amount is None or amount <= 0 or int(amount) != amount or (other or 0) != 0:
                raise PeriodReconciliationConflict('subsidy_period_bank_invalid')
            cursor.execute('SELECT id FROM government_subsidy_period_entries WHERE finance_import_row_id=%s UNION ALL '
                'SELECT id FROM government_subsidy_transactions WHERE finance_import_row_id=%s UNION ALL '
                'SELECT id FROM finance_import_reconciliation_receipts WHERE finance_import_row_id=%s UNION ALL '
                'SELECT id FROM client_ledger_entries WHERE finance_import_row_id=%s UNION ALL '
                'SELECT id FROM staff_payout_events WHERE finance_import_row_id=%s',
                (bank_row_id, bank_row_id, bank_row_id,bank_row_id,bank_row_id))
            if cursor.fetchone():
                raise PeriodReconciliationConflict('subsidy_period_bank_already_used')
        return int(amount)

    def bank_rows(self) -> tuple[PeriodBankRow, ...]:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT bank.id,bank.transaction_date,bank.credit,bank.debit FROM finance_import_rows bank "
                "LEFT JOIN finance_import_classification_events classification ON classification.id=(SELECT MAX(latest.id) "
                "FROM finance_import_classification_events latest WHERE latest.finance_import_row_id=bank.id) "
                "WHERE COALESCE(classification.classification_type,bank.classification_type)='government_subsidy' "
                "AND NOT EXISTS(SELECT 1 FROM government_subsidy_period_entries entry WHERE entry.finance_import_row_id=bank.id) "
                "AND NOT EXISTS(SELECT 1 FROM government_subsidy_transactions old WHERE old.finance_import_row_id=bank.id) "
                "AND NOT EXISTS(SELECT 1 FROM finance_import_reconciliation_receipts receipt WHERE receipt.finance_import_row_id=bank.id) "
                "ORDER BY bank.transaction_date DESC,bank.id DESC LIMIT 200")
            return tuple({'id': int(row['id']), 'paid_on': row['transaction_date'],
                          'amount_ntd': int(row['credit'] or 0) - int(row['debit'] or 0)} for row in cursor.fetchall())

    def case_coverage(self, case_no: str) -> CasePeriodCoverage:
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT COALESCE(actual_end_date,end_date) service_end_date FROM orders WHERE case_no=%s',(case_no,))
            row = cursor.fetchone()
            if row is None:
                raise PeriodReconciliationConflict('subsidy_case_not_found')
            end = row['service_end_date']
            view = self.query(SubsidyPeriod('month',end.year,end.month)) if end else None
            line = next((line for line in view.lines if line.case_no==case_no),None) if view else None
            cursor.execute('SELECT entry.id,entry.period_unit,entry.period_year,entry.period_index,entry.amount_ntd,'+_RECOVERED+' recovered_advance_ntd,member.service_end_date,member.amount_ntd member_amount_ntd '
                'FROM government_subsidy_period_members member JOIN government_subsidy_period_entries entry ON entry.id=member.receipt_id '
                'WHERE member.case_no=%s AND '+_ACTIVE+' ORDER BY entry.id',(case_no,))
            coverage = tuple({'receipt_id':int(record['id']),
                'label':SubsidyPeriod(record['period_unit'],record['period_year'],record['period_index']).label,
                'amount_ntd':int(record['amount_ntd']),'recorded_case_amount_ntd':int(record['member_amount_ntd']),
                'recorded_service_end_date':record['service_end_date'],
                'recovered_advance_ntd':int(record['recovered_advance_ntd'])} for record in cursor.fetchall())
            return {'case_no':case_no,'service_end_date':end,'amount_ntd':line.amount_ntd if line else None,'coverage':coverage}

    def save(self, view, bank_row_id, key, actor):
        with self.connection.cursor() as cursor:
            period = view.period
            # Current client accounts serialize refund payout classification and government recovery.
            for line in sorted(view.lines, key=lambda item: item.case_no):
                cursor.execute('SELECT case_no FROM client_finance_accounts WHERE case_no=%s FOR UPDATE', (line.case_no,))
                cursor.fetchall()
            identity = self._insert(cursor, period, bank_row_id, view.total_ntd, None, key, actor)
            for line in view.lines:
                cursor.execute('INSERT INTO government_subsidy_period_members(receipt_id,case_no,service_end_date,amount_ntd) '
                               'VALUES (%s,%s,%s,%s)', (identity,line.case_no,line.service_end_date,line.amount_ntd))
            self._advance_version(cursor, period.year)
            return identity

    def reverse(self, receipt_id, bank_row_id, key, actor):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT * FROM government_subsidy_period_entries WHERE id=%s', (receipt_id,))
            row = cursor.fetchone()
            if not row or row['reversal_of_id'] is not None:
                raise PeriodReconciliationConflict('subsidy_period_receipt_not_found')
            period = SubsidyPeriod(row['period_unit'],row['period_year'],row['period_index'])
            replay = self.find_replay(key,(period.unit,period.year,period.index,bank_row_id,receipt_id))
            if replay is not None:
                return replay
            cursor.execute('SELECT aggregate_version FROM government_subsidy_period_years WHERE period_year=%s FOR UPDATE', (period.year,))
            cursor.fetchone()
            cursor.execute('SELECT id FROM government_subsidy_period_entries WHERE reversal_of_id=%s', (receipt_id,))
            if cursor.fetchone():
                raise PeriodReconciliationConflict('subsidy_period_already_reversed')
            if self.bank_amount(bank_row_id,reversal=True) != int(row['amount_ntd']):
                raise PeriodReconciliationConflict('subsidy_period_amount_mismatch')
            identity = self._insert(cursor,period,bank_row_id,row['amount_ntd'],receipt_id,key,actor)
            self._advance_version(cursor,period.year)
            return identity

    @staticmethod
    def _advance_version(cursor, year):
        cursor.execute('UPDATE government_subsidy_period_years SET aggregate_version=aggregate_version+1 WHERE period_year=%s', (year,))

    @staticmethod
    def _insert(cursor,period,bank_row_id,amount,reversal,key,actor):
        cursor.execute('INSERT INTO government_subsidy_period_entries(period_unit,period_year,period_index,period_start,period_end,'
            'finance_import_row_id,amount_ntd,reversal_of_id,paid_on,idempotency_key,actor) '
            'SELECT %s,%s,%s,%s,%s,id,%s,%s,transaction_date,%s,%s FROM finance_import_rows WHERE id=%s',
            (period.unit,period.year,period.index,period.start,period.end,amount,reversal,key,actor,bank_row_id))
        return int(cursor.lastrowid)
