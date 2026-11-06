"""Exact server-bound manual initial receipt proof; no provider/bank attestation."""
from datetime import date
import json

from domains.government_subsidy.period_reconciliation import PeriodReconciliationConflict, SubsidyPeriod
from subsystems.government_subsidy.period_reconciliation import ManualInitialPeriodReceipt, ManualInitialPeriodSource, ManualInitialReceiptProof


def manual_initial_references(command):
    return {'source': 'manual_supplement', 'manual_source_kind': 'government_period_initial_receipt',
            'reason': command.reason, 'manual_command': command.payload, 'manual_command_digest': command.digest}


def manual_initial_command(references):
    try:
        refs = json.loads(references) if isinstance(references, str) else references
        payload = refs['manual_command']
        if (refs['source'] != 'manual_supplement' or refs['manual_source_kind'] != 'government_period_initial_receipt'
            or payload['kind'] != 'government_period_initial_manual_receipt'):
            return None
        period = payload['period']
        command = ManualInitialPeriodReceipt(SubsidyPeriod(period['unit'], period['year'], period['index']),
            payload['amount_ntd'], date.fromisoformat(payload['paid_on']), payload['handling'], payload['reason'],
            payload['expected_version'], payload['key'], payload['actor'])
        if refs != manual_initial_references(command):
            return None
        return command
    except (KeyError, TypeError, ValueError):
        return None


def require_manual_initial_source(source, row, *, replay=False):
    if not isinstance(source, ManualInitialPeriodSource):
        raise PeriodReconciliationConflict('subsidy_period_manual_source_invalid')
    command = source.command
    actual = manual_initial_command(row.get('bank_references')) if row else None
    if (actual != command or type(row.get('id')) is not int or row['id'] != source.row_id
        or row.get('format_id') != 'legacy' or row.get('direction') != 'incoming'
        or row.get('credit') != command.amount_ntd or (row.get('debit') or 0) != 0
        or str(row.get('transaction_date')) != command.paid_on.isoformat() or row.get('currency') != 'TWD'
        or row.get('classification_type') != 'government_subsidy'
        or any(row.get(field) is not None for field in ('batch_id','source_file','sheet_name','source_row',
            'source_reference','source_bank_account','counterparty_account','resolved_counterparty_account'))
        or row.get('reconciliation_status') not in ({'pending', 'reconciled'} if replay else {'pending'})):
        raise PeriodReconciliationConflict('subsidy_period_manual_source_invalid')


def verified_manual_initial_receipt(row, entry):
    """Match manual facts to the actual immutable period receipt, not a marker."""
    try:
        entry = json.loads(entry) if isinstance(entry, str) else entry
        command = manual_initial_command(row.get('bank_references'))
        if command is None or not isinstance(entry, dict):
            return False
        require_manual_initial_source(ManualInitialPeriodSource(row['id'], command), row, replay=True)
        expected = {'period_unit': command.period.unit, 'period_year': command.period.year,
                    'period_index': command.period.index, 'finance_import_row_id': row['id'], 'amount_ntd': command.amount_ntd,
                    'paid_on': command.paid_on.isoformat(), 'actor': command.actor, 'idempotency_key': command.owner_key,
                    'reversal_of_id': None}
        return all(key in entry and (str(entry[key]) == value if key == 'paid_on' else entry[key] == value)
                   for key, value in expected.items())
    except (KeyError, TypeError, ValueError):
        return False


PERIOD_RECEIPT_PROOF_JSON_SQL = ("JSON_OBJECT('period_unit',entry.period_unit,'period_year',entry.period_year,'period_index',entry.period_index,"
    "'finance_import_row_id',entry.finance_import_row_id,'amount_ntd',entry.amount_ntd,'paid_on',CAST(entry.paid_on AS CHAR),"
    "'actor',entry.actor,'idempotency_key',entry.idempotency_key,'reversal_of_id',entry.reversal_of_id)")


def manual_initial_receipt_readback(rows, command, receipt_id):
    """Build the immutable receipt from persisted source/entry facts, not request echo."""
    if len(rows) != 1:
        raise PeriodReconciliationConflict('subsidy_period_manual_readback_invalid')
    row = rows[0]
    try:
        entry = json.loads(row['period_receipt']) if isinstance(row['period_receipt'], str) else row['period_receipt']
        actual = manual_initial_command(row['bank_references'])
        if (row['receipt_id'] != receipt_id or actual != command
            or not verified_manual_initial_receipt(row, entry)
            or row['stored_key'] != actual.key or row['stored_digest'] != actual.digest or row['stored_actor'] != actual.actor
            or row['stored_result_identity'] != f"government-manual:{row['id']}:{row['receipt_id']}"):
            raise PeriodReconciliationConflict('subsidy_period_manual_readback_invalid')
        return ManualInitialReceiptProof(row['receipt_id'],
            SubsidyPeriod(entry['period_unit'], entry['period_year'], entry['period_index']), entry['amount_ntd'],
            date.fromisoformat(str(entry['paid_on'])), '人工補登', actual.key)
    except (KeyError, TypeError, ValueError) as error:
        raise PeriodReconciliationConflict('subsidy_period_manual_readback_invalid') from error
