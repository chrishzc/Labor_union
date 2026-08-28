/**
 * File: client_settlement_remediation.test.tsx
 * Description: 驗證三碼 exact dispatcher 與客戶應付部分／完整 root readback 判斷。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AnomalyDetailViewSchema } from '../api/anomalies/anomaly_detail_schemas';
import type { ClientSettlementRemediationClient } from '../api/client_finance/client_settlement_remediation_client';
import { clientSettlementTarget } from '../adapters/anomalies/client_settlement_target';
import { ClientSettlementRemediationWorkbench } from '../components/ClientSettlementRemediationWorkbench';

const fingerprint = 'a'.repeat(64);
const previewFingerprint = 'b'.repeat(64);

function detail() {
  return AnomalyDetailViewSchema.parse({
    summary: {
      fingerprint, definition_code: 'CLIENTPAYABLE-001', source_domain: 'client_payable',
      source_identity: 'CASE-1', source_version: 1, severity: 'warning', predicate_active: true,
      workflow_status: 'open', workflow_version: 1, staff_calendar_navigation: null,
      display_snapshot: { redaction_version: 'anomaly-safe.v1', definition_code: 'CLIENTPAYABLE-001', fields: [] },
    }, timeline: [],
    available_actions: [{
      action_key: 'settle_client_payable', label: '核銷逾期客戶退款應付', owning_domain: 'client_finance',
      form_schema_key: 'client_finance.client_payable_refund.v1',
      source_binding_keys: ['account_version', 'case_no'],
      source_bindings: [{ kind: 'version', key: 'account_version', value: 3 }, { kind: 'identity', key: 'case_no', value: 'CASE-1' }],
      required_operator_inputs: ['bank_fact_identities', 'obligation_identities', 'reason'],
      preview_operation: 'PreviewClientRefund', apply_operation: 'ApplyClientRefund', required_capability: null,
      completion_predicate: 'client_payable_overdue_obligations_cleared', action_contract_version: 1, requires_preview: true,
    }],
  });
}

const firstQuery = {
  case_no: 'CASE-1', account_version: 3, as_of: '2026-08-27', receivable_obligations: [],
  refund_obligations: [
    { obligation_identity: 'refund:1', obligation_type: 'refund' as const, amount_due_ntd: 500, due_date: '2026-08-01' },
    { obligation_identity: 'adjustment:2', obligation_type: 'adjustment' as const, amount_due_ntd: 700, due_date: '2026-08-02' },
  ], subsidy_return_obligations: [], incoming_bank_facts: [],
  refund_bank_facts: [{ finance_import_row_id: 11, amount_ntd: 500, transaction_date: '2026-08-27', eligible_obligation_identities: ['refund:1'] }],
  subsidy_return_bank_facts: [],
};
const payablePreview = {
  account_version: 3,
  candidate: {
    correction_type: 'refund' as const, case_no: 'CASE-1', amount: { amount: 500 },
    entries: [{ identity: 'refund-bank:11', entry_type: 'refund' as const, amount: { amount: 500 }, occurred_on: '2026-08-27', reversal_of_entry_identity: null, finance_import_row_identity: '11' }],
    allocations: [{ entry_identity: 'refund-bank:11', obligation_identity: 'refund:1', amount: { amount: 500 } }],
    affected_obligations: ['refund:1'], reversal_entry_type: null, recovery_amount: { amount: 0 }, fingerprint,
  }, preview_fingerprint: previewFingerprint,
};

function owner(secondQuery: typeof firstQuery): ClientSettlementRemediationClient {
  return {
    query: vi.fn().mockResolvedValueOnce(firstQuery).mockResolvedValueOnce(secondQuery),
    previewReceipt: vi.fn(), applyReceipt: vi.fn(),
    previewPayable: vi.fn().mockResolvedValue(payablePreview),
    applyPayable: vi.fn().mockResolvedValue({ case_no: 'CASE-1', correction_type: 'refund', account_version: 4, correction_identity: fingerprint, ledger_entry_count: 1, allocation_count: 1, affected_obligations: ['refund:1'] }),
  };
}

describe('client settlement anomaly remediation', () => {
  it('routes only an exact bound Client Finance action', () => {
    expect(clientSettlementTarget(detail())).toEqual({ kind: 'refund', caseNo: 'CASE-1', accountVersion: 3 });
    const drifted = detail();
    drifted.available_actions[0].completion_predicate = 'receipt_exists';
    expect(clientSettlementTarget(drifted)).toBeNull();
  });

  it('keeps the anomaly active when another same-code overdue obligation remains', async () => {
    const partial = { ...firstQuery, account_version: 4, refund_obligations: [firstQuery.refund_obligations[1]], refund_bank_facts: [] };
    const client = owner(partial);
    const onResolved = vi.fn();
    render(<ClientSettlementRemediationWorkbench target={{ kind: 'refund', caseNo: 'CASE-1', accountVersion: 3 }} client={client} onResolved={onResolved} />);
    await waitFor(() => expect(screen.getByText(/refund:1/)).toBeInTheDocument());
    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[0]); fireEvent.click(checkboxes[2]);
    fireEvent.change(screen.getByLabelText('人工核對理由'), { target: { value: '客戶以電話確認退款帳戶，已核對銀行流水' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查核銷影響' }));
    await waitFor(() => expect(screen.getByText(/Preview 金額/)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/我已核對 owner Query/));
    fireEvent.click(screen.getByRole('button', { name: '確認並套用' }));
    await waitFor(() => expect(screen.getByText(/adjustment:2/)).toBeInTheDocument());
    expect(onResolved).not.toHaveBeenCalled();
    expect(screen.getByText(/若仍有其他同碼逾期義務/)).toBeInTheDocument();
  });

  it('reports resolution only after fresh owner query has no same-code overdue obligations', async () => {
    const terminal = { ...firstQuery, account_version: 4, refund_obligations: [], refund_bank_facts: [] };
    const client = owner(terminal);
    const onResolved = vi.fn();
    render(<ClientSettlementRemediationWorkbench target={{ kind: 'refund', caseNo: 'CASE-1', accountVersion: 3 }} client={client} onResolved={onResolved} />);
    await waitFor(() => expect(screen.getByText(/refund:1/)).toBeInTheDocument());
    const checkboxes = screen.getAllByRole('checkbox'); fireEvent.click(checkboxes[0]); fireEvent.click(checkboxes[2]);
    fireEvent.change(screen.getByLabelText('人工核對理由'), { target: { value: '電話補充帳戶後已核對正式出款' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查核銷影響' }));
    await waitFor(() => screen.getByText(/Preview 金額/)); fireEvent.click(screen.getByLabelText(/我已核對 owner Query/)); fireEvent.click(screen.getByRole('button', { name: '確認並套用' }));
    await waitFor(() => expect(onResolved).toHaveBeenCalledTimes(1));
    expect(screen.getByText(/此碼已無逾期未清義務/)).toBeInTheDocument();
  });
});
