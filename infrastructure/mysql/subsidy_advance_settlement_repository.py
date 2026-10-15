"""Read immutable advance/receipt lineage and persist its existing recovery link."""

import json
from decimal import Decimal

from domains.client_finance.subsidy_advance_settlement import (
    AdvanceEntitlement, AdvanceGovernmentReceipt, AdvanceSettlementFacts,
)
from infrastructure.mysql.subsidy_advance_recovery_repository import MySqlSubsidyAdvanceRecoveryRepository
from subsystems.client_finance.subsidy_advance_settlement import AdvanceSettlementConflict


class MySqlAdvanceSettlementRepository:
    def __init__(self, connection):
        self.connection = connection

    def list_facts(self, after_id, search, limit):
        condition = ''
        values = [after_id]
        if search:
            condition = ' AND (LOCATE(%s,ledger.case_no)>0 OR LOCATE(%s,client.name)>0)'
            values.extend((search, search))
        values.append(limit)
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT ledger.id FROM client_ledger_entries ledger "
                "JOIN orders o ON o.case_no=ledger.case_no JOIN clients client ON client.id=o.client_id "
                "WHERE ledger.entry_type='subsidy_advance' AND ledger.id>%s" + condition +
                ' ORDER BY ledger.id LIMIT %s', tuple(values),
            )
            ids = tuple(int(row['id']) for row in cursor.fetchall())
            return self._details(cursor, ids)

    def load(self, advance_id, *, lock=False):
        with self.connection.cursor() as cursor:
            if lock:
                # Serialize with the automatic consumer before locking its target.
                cursor.execute(
                    'SELECT DISTINCT outbox.id FROM client_ledger_obligation_allocations la '
                    'JOIN client_subsidy_return_claim_item_links link ON link.obligation_identity=la.obligation_identity '
                    "JOIN government_subsidy_allocations a ON a.claim_item_id=link.claim_item_id AND a.allocation_type='receipt' "
                    'JOIN government_subsidy_outbox outbox ON outbox.transaction_id=a.transaction_id '
                    "AND outbox.intent_type='government_subsidy_receipt_allocated' "
                    'WHERE la.ledger_entry_id=%s ORDER BY outbox.id', (advance_id,),
                )
                for row in cursor.fetchall():
                    cursor.execute('SELECT id FROM government_subsidy_outbox WHERE id=%s FOR UPDATE', (row['id'],))
                    cursor.fetchone()
                cursor.execute(
                    'SELECT account.batch_id FROM government_subsidy_batch_accounts account '
                    'WHERE account.batch_id IN (SELECT item.batch_id FROM subsidy_claim_batch_items item '
                    'JOIN client_subsidy_return_claim_item_links link ON link.claim_item_id=item.id '
                    'JOIN client_ledger_obligation_allocations la ON la.obligation_identity=link.obligation_identity '
                    'WHERE la.ledger_entry_id=%s) ORDER BY account.batch_id FOR UPDATE', (advance_id,),
                )
                cursor.fetchall()
                cursor.execute(
                    'SELECT account.case_no FROM client_finance_accounts account '
                    'JOIN client_ledger_entries ledger ON ledger.case_no=account.case_no '
                    'WHERE ledger.id=%s FOR UPDATE', (advance_id,),
                )
                cursor.fetchall()
            facts = self._details(cursor, (advance_id,), lock=lock)
            return facts[0] if facts else None

    def _details(self, cursor, ids, *, lock=False):
        if not ids:
            return ()
        cursor.execute(_DETAIL_SQL + ' WHERE ledger.id IN (' + ','.join(['%s'] * len(ids)) +
                       ") AND ledger.entry_type='subsidy_advance' ORDER BY ledger.id,link.id,a.id" +
                       (' FOR UPDATE' if lock else ''), ids)
        groups = {}
        for row in cursor.fetchall():
            groups.setdefault(int(row['advance_id']), []).append(row)
        return tuple(_facts(rows) for rows in groups.values())

    def load_receipt(self, key):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT command_fingerprint,result_snapshot FROM client_finance_apply_receipts '
                           'WHERE idempotency_key=%s FOR UPDATE', (key,))
            row = cursor.fetchone()
        if row is None:
            return None
        payload = _json(row['result_snapshot'])
        return {'command_fingerprint': row['command_fingerprint'], 'result_snapshot': payload.get('result', payload)}

    def recovery_repository(self):
        return MySqlSubsidyAdvanceRecoveryRepository(self.connection)

    def save_receipt(self, command, command_hash, facts, result):
        audit = {
            'operation': 'subsidy_advance_settlement.v1', 'actor': command.actor, 'reason': command.reason,
            'advance_id': facts.advance_id, 'claim_item_id': facts.entitlements[0].claim_item_id,
            'government_allocation_id': facts.receipts[0].allocation_id,
            'source_outbox_id': facts.receipts[0].source_outbox_id, 'result': result,
        }
        encoded = json.dumps(audit, ensure_ascii=False, separators=(',', ':'))
        with self.connection.cursor() as cursor:
            cursor.execute('UPDATE client_finance_accounts SET aggregate_version=aggregate_version+1 '
                           'WHERE case_no=%s AND aggregate_version=%s', (facts.case_no, command.expected_account_version))
            if cursor.rowcount != 1:
                raise AdvanceSettlementConflict('stale_preview')
            cursor.execute('INSERT INTO client_finance_apply_receipts '
                           '(idempotency_key,command_fingerprint,preview_fingerprint,case_no,resulting_account_version,result_snapshot) '
                           'VALUES (%s,%s,%s,%s,%s,%s)',
                           (command.idempotency_key, command_hash, command.preview_fingerprint,
                            facts.case_no, result['account_version'], encoded))
            cursor.execute('INSERT INTO client_finance_outbox (case_no,intent_type,intent_key,payload_snapshot) '
                           "VALUES (%s,'projection_refresh',%s,%s)",
                           (facts.case_no, f'advance-settlement:{command_hash}', encoded))


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


def _ntd(value):
    number = Decimal(str(value))
    if not number.is_finite() or number != number.to_integral_value() or number < 0:
        raise ValueError('subsidy_advance_money_invalid')
    return int(number)


def _evidence_matches(row):
    if row['source_outbox_id'] is None:
        return False
    try:
        payload = _json(row['payload_snapshot'])
        return (isinstance(payload, dict) and payload.get('kind') == 'receipt'
                and payload.get('transaction_id') == row['transaction_id']
                and payload.get('batch_id') == row['batch_id']
                and sum(1 for allocation in payload.get('allocations', [])
                        if allocation.get('claim_item_id') == row['claim_item_id']
                        and allocation.get('case_no') == row['case_no']
                        and allocation.get('amount_ntd') == _ntd(row['receipt_amount'])) == 1)
    except (ValueError, TypeError, AttributeError):
        return False


def _facts(rows):
    first = rows[0]
    entitlements, receipts, obligations = {}, {}, {}
    for row in rows:
        if row['obligation_identity'] is not None:
            obligations[row['obligation_identity']] = _ntd(row['advance_allocation_amount'])
        if row['link_id'] is not None:
            entitlements[row['link_id']] = AdvanceEntitlement(
                int(row['link_id']), int(row['claim_item_id']), int(row['batch_id']),
                int(row['batch_version'] or 0), _ntd(row['entitled_amount_ntd']),
                _ntd(row['approved_amount']),
                row['claim_case_no'] == row['case_no'] and row['obligation_case_no'] == row['case_no']
                and row['obligation_type'] == 'subsidy_return' and row['direction'] == 'payable_to_client'
                and row['batch_version'] is not None,
            )
        if row['allocation_id'] is not None:
            receipts[row['allocation_id']] = AdvanceGovernmentReceipt(
                int(row['allocation_id']), int(row['transaction_id']), int(row['claim_item_id']),
                _ntd(row['receipt_amount']), _ntd(row['receipt_reversed']), row['received_on'],
                row['source_outbox_id'], _evidence_matches(row), int(row['advance_target_count']),
            )
    return AdvanceSettlementFacts(
        int(first['advance_id']), first['case_no'], first['client_name'],
        _ntd(first['advance_amount_ntd']), first['advanced_on'], first['actual_end_date'],
        first['account_version'], len(obligations), sum(obligations.values()),
        _ntd(first['advance_reversed']), tuple(entitlements.values()), tuple(receipts.values()),
        _ntd(first['recovered_amount_ntd']), first['recovered_allocation_id'],
    )


_DETAIL_SQL = """
SELECT ledger.id advance_id,ledger.case_no,ledger.amount_ntd advance_amount_ntd,ledger.occurred_on advanced_on,
       client.name client_name,o.actual_end_date,account.aggregate_version account_version,
       la.obligation_identity,la.amount_ntd advance_allocation_amount,
       obligation.case_no obligation_case_no,obligation.obligation_type,obligation.direction,
       link.id link_id,link.entitled_amount_ntd,item.id claim_item_id,item.case_no claim_case_no,
       item.batch_id,item.approved_amount,batch_account.aggregate_version batch_version,
       a.id allocation_id,a.transaction_id,a.allocated_amount receipt_amount,DATE(gov_transaction.occurred_at) received_on,
       outbox.id source_outbox_id,outbox.payload_snapshot,
       COALESCE((SELECT SUM(r.amount_ntd) FROM client_ledger_entries r
                 WHERE r.reversal_of_entry_id=ledger.id),0) advance_reversed,
       COALESCE((SELECT SUM(r.allocated_amount) FROM government_subsidy_allocations r
                 WHERE r.reversal_of_allocation_id=a.id AND r.allocation_type='reversal'),0) receipt_reversed,
       (SELECT COUNT(*) FROM client_subsidy_return_claim_item_links target_link
        JOIN client_ledger_obligation_allocations target_la ON target_la.obligation_identity=target_link.obligation_identity
        JOIN client_ledger_entries target_ledger ON target_ledger.id=target_la.ledger_entry_id
            AND target_ledger.entry_type='subsidy_advance'
        WHERE target_link.claim_item_id=a.claim_item_id) advance_target_count,
       COALESCE(recovery.recovered_amount_ntd,0) recovered_amount_ntd,
       recovery.government_allocation_id recovered_allocation_id
FROM client_ledger_entries ledger
JOIN orders o ON o.case_no=ledger.case_no
JOIN clients client ON client.id=o.client_id
LEFT JOIN client_finance_accounts account ON account.case_no=ledger.case_no
LEFT JOIN client_ledger_obligation_allocations la ON la.ledger_entry_id=ledger.id
LEFT JOIN client_obligations obligation ON obligation.obligation_identity=la.obligation_identity
LEFT JOIN client_subsidy_return_claim_item_links link ON link.obligation_identity=la.obligation_identity
LEFT JOIN subsidy_claim_batch_items item ON item.id=link.claim_item_id
LEFT JOIN government_subsidy_batch_accounts batch_account ON batch_account.batch_id=item.batch_id
LEFT JOIN government_subsidy_allocations a ON a.claim_item_id=item.id AND a.claim_batch_id=item.batch_id
    AND a.allocation_type='receipt'
LEFT JOIN government_subsidy_transactions gov_transaction ON gov_transaction.id=a.transaction_id
LEFT JOIN government_subsidy_outbox outbox ON outbox.transaction_id=gov_transaction.id
    AND outbox.intent_type='government_subsidy_receipt_allocated'
LEFT JOIN client_subsidy_advance_recoveries recovery ON recovery.advance_ledger_entry_id=ledger.id
"""
