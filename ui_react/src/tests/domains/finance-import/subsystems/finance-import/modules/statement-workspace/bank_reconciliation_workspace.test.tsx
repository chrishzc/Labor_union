/**
 * File: bank_reconciliation_workspace.test.tsx
 * Description: 銀行對帳工作台（WF-03/04）單元驗收測試，驗證雙行排版、KPI膠囊、篩選與核對抽屜。
 */

import { readFileSync } from 'node:fs';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FinanceBankReconciliationWorkspace } from '../../../../../../../components/FinanceBankReconciliationWorkspace';
import { financeBankReviewPresentation, financeImportReviewReason } from '../../../../../../../adapters/finance/finance_import_query_adapter';
import { financeImportQueryClient } from '../../../../../../../api/finance_import/finance_import_query_client';
import type { FinanceBankTransaction } from '../../../../../../../api/finance_import/finance_import_query_schemas';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { subsidyPeriodClient } from '../../../../../../../api/government_subsidy/period_reconciliation_client';
import { FinancePage } from '../../../../../../../pages/FinancePage';
import { financeAccountingClient } from '../../../../../../../api/finance_import/finance_accounting_client';
import { clientReceiptQueryClient } from '../../../../../../../api/client_finance/client_receipt_query_client';
import { clientSettlementRemediationClient } from '../../../../../../../api/client_finance/client_settlement_remediation_client';
import { caseVirtualAccountClient } from '../../../../../../../api/client_finance/case_virtual_account_client';
import { clientRegistryClient } from '../../../../../../../api/client_registry/client_registry_client';
import { ordersQueryClient } from '../../../../../../../api/orders/order_query_client';
import { paymentOverdueReminderClient } from '../../../../../../../api/line_order_groups/payment_overdue_reminder_client';
import { transport } from '../../../../../../../api/shared/transport';
import { ApiHttpError, ApiTimeoutError } from '../../../../../../../api/shared/typed_errors';
import { differenceResolutionClient } from '../../../../../../../api/client_finance/difference_resolution_client';
import { staffPayoutRemediationClient } from '../../../../../../../api/staff_payables/staff_payout_remediation_client';
import { staffPayoutBlockerMessage } from '../../../../../../../api/staff_payables/staff_payout_remediation_errors';
import { financeImportCorrectionClient } from '../../../../../../../api/finance_import/finance_import_correction_client';
import { financeImportMutationClient } from '../../../../../../../api/finance_import/finance_import_mutation_client';
import { FinanceImportQueryError } from '../../../../../../../api/finance_import/finance_import_query_errors';

vi.mock('../../../../../../../api/finance_import/finance_import_query_client', () => ({
  financeImportQueryClient: { listBankTransactions: vi.fn(), listImportHistory: vi.fn(), listExcludedBankTransactions: vi.fn(), pairBankTransaction: vi.fn(), excludeBankTransaction: vi.fn() },
}));
vi.mock('../../../../../../../components/FinanceStatementArchive', () => ({
  FinanceStatementArchive: ({ compact: _compact }: { compact?: boolean }) => (
    <div data-testid="statement-archive">
      <button type="button">匯出對帳明細</button>
    </div>
  ),
}));
describe('FinanceBankReconciliationWorkspace (WF-03 / WF-04)', () => {
  const onCase = vi.fn();
  const onReconcile = vi.fn();
  const onLookupIngestion = vi.fn();
  const onWorkbookChange = vi.fn();
  const onApplyReasonChange = vi.fn();
  const onIngest = vi.fn();
  const onApply = vi.fn();
  const onObserveApplyOutcome = vi.fn();

  const sinopac: FinanceBankTransaction = {
    row_id: 101, row_identity: 'finance-import-row:101', transaction_date: '2026-01-09',
    bank: 'sinopac', direction: 'incoming', amount_ntd: 15000, classification_type: 'client_receipt',
    status: 'pending', disposition: 'business_pending', review_reason: 'sinopac_virtual_account_matched', available_actions: [],
    reference: 'Sheet1#2', counterparty_name: '林小美', cases: ['115000001'],
    reconciliation_target: { case_no: '115000001', obligation_identities: ['receipt:first'], staff_id: null },
  };
  const taishin: FinanceBankTransaction = {
    ...sinopac, row_id: 102, row_identity: 'finance-import-row:102', bank: 'taishin',
    direction: 'incoming', amount_ntd: 18000, reference: '交易明細#3', classification_type: 'government_subsidy',
    review_reason: 'taishin_incoming_government_subsidy', counterparty_name: '新竹市政府', cases: [], reconciliation_target: null,
  };
  const posted: FinanceBankTransaction = {
    ...sinopac, row_id: 100, row_identity: 'finance-import-row:100', status: 'posted', amount_ntd: 6000,
    reference: 'DEMO-POSTED-01', cases: ['DEMO-08'], bank_memo: '合成原始備註 ****',
    reconciliation_records: [{ owning_domain: 'client_finance', amount_ntd: 6000, recorded_at: '2026-01-09T10:00:00Z' }],
    purpose_review: { classification_version: 1, candidates: [{ case_no: 'DEMO-08', purpose: 'client_refund', person_id: 17 }] },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(financeImportQueryClient.listBankTransactions).mockImplementation(async query => ({
      items: query.row_id ? [taishin, sinopac, posted].filter(row => row.row_id === query.row_id)
        : query.transaction_status === 'posted' ? [posted] : [taishin, sinopac].filter(row => !query.bank || row.bank === query.bank),
      pending_count: query.transaction_status === 'posted' ? null : query.bank ? 1 : 2,
      next_before_row_id: null,
    }));
    vi.mocked(financeImportQueryClient.listImportHistory).mockResolvedValue({
      items: [{ identity: 'attempt:2', started_at: '2026-01-10T00:00:00Z', bank: 'sinopac', source_file: 'statement.xlsx',
        status: 'saved', new_count: 0, duplicate_count: 3, reconciled_count: 0, pending_count: 2,
        source_warning_count: 0, error_code: null }],
      next_before: null,
    });
    vi.mocked(financeImportQueryClient.listExcludedBankTransactions).mockResolvedValue({
      items: [],
      next_before_row_id: null,
    });
  });

  const defaultProps = {
    onCase,
    revision: 0,
    onLookupIngestion,
    financeWorkbook: null,
    onWorkbookChange,
    applyReason: '',
    onApplyReasonChange,
    importBusy: false,
    ingestion: { kind: 'idle' as const },
    batchPreview: { kind: 'idle' as const },
    applyJob: { kind: 'idle' as const },
    batchOutcome: { kind: 'idle' as const },
    onIngest,
    onApply,
    onObserveApplyOutcome,
    onReconcile,
    confirmedImportReceipt: null,
  };

  it('opens the same single-transaction entry for a client subsidy return with a legacy batch hint', async () => {
    const row: FinanceBankTransaction = {
      ...taishin, direction: 'outgoing', classification_type: 'client_subsidy_return', cases: ['115000001'],
      staff_subsidy_batch_identity: 'finance-import-batch:9',
      reconciliation_target: { case_no: '115000001', obligation_identities: ['client:subsidy-return'], staff_id: null },
    };
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({ items: [row], pending_count: 1, next_before_row_id: null });
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);
    const transaction = within(await screen.findByRole('row', { name: /交易明細#3/ }));
    const entries = transaction.getAllByRole('button', { name: /核對交易|核對月嫂補助|單筆人工核對/ });
    expect(entries).toHaveLength(1);
    fireEvent.click(entries[0]);
    expect(onReconcile).toHaveBeenCalledWith(row);
  });

  it('passes a pending transaction without a target to the review drawer from both entry points', async () => {
    const row: FinanceBankTransaction = {
      ...taishin, direction: 'outgoing', classification_type: 'client_subsidy_return',
      reconciliation_unavailable_reason: 'case_unconfirmed',
    };
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({ items: [row], pending_count: 1, next_before_row_id: null });
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);
    fireEvent.click(await screen.findByRole('button', { name: /核對交易/ }));
    fireEvent.click(screen.getByRole('button', { name: `查看交易 ${row.row_identity}` }));
    const detail = screen.getByRole('dialog', { name: '待核對交易明細' });
    fireEvent.click(within(detail).getByRole('button', { name: '核對交易' }));
    expect(onReconcile.mock.calls).toEqual([[row], [row]]);
    expect(onCase).not.toHaveBeenCalled();
  });

  it.each([
    { subsidyNtd: undefined, reason: /尚無可供核對的正式客戶補助退款款項/ },
    { subsidyNtd: null, reason: /本案正式補助金額來源待確認/ },
    { subsidyNtd: 12000, reason: /本案正式補助金額 NT\$ 12,000，目前沒有可供核對的正式客戶補助退款款項/ },
  ])('keeps a client subsidy return with no refund candidate read-only (subsidy data: $subsidyNtd)', async ({ subsidyNtd, reason }) => {
    window.location.hash = '#finance?tab=bank';
    const caseNo = '115000001';
    const row: FinanceBankTransaction = {
      ...taishin, direction: 'outgoing', classification_type: 'client_subsidy_return', cases: [caseNo],
      reconciliation_unavailable_reason: 'no_open_items',
      reconciliation_target: subsidyNtd === undefined ? null : {
        case_no: caseNo, staff_id: null, obligation_identities: [], requires_selection: true,
      },
      pairing_candidates: [{ case_no: caseNo, purpose: 'client_subsidy_return', person_id: 17 }],
      staff_subsidy_batch_identity: 'finance-import-batch:9',
    };
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [row], pending_count: 1, next_before_row_id: null,
    });
    const unexpected = new Error('本筆交易只有案件查閱入口。');
    const post = vi.spyOn(transport, 'post').mockRejectedValue(unexpected);
    const batchPreview = vi.spyOn(financeImportMutationClient, 'preview').mockRejectedValue(unexpected);
    const staffQuery = vi.spyOn(staffPayoutRemediationClient, 'query').mockRejectedValue(unexpected);
    const staffRecovery = vi.spyOn(differenceResolutionClient, 'staff').mockRejectedValue(unexpected);
    const staffPreview = vi.spyOn(staffPayoutRemediationClient, 'preview').mockRejectedValue(unexpected);
    const refundPreview = vi.spyOn(financeImportCorrectionClient, 'preview').mockRejectedValue(unexpected);
    const readCase = vi.spyOn(financeAccountingClient, 'query').mockResolvedValue({
      case_no: caseNo, client_name: '合成客戶', subsidy_ntd: subsidyNtd,
      receivable_ntd: 0, received_ntd: 0, payable_ntd: 0, paid_ntd: 0, pending_warning_count: 0,
      staff_items: [], transactions: [], warnings: [], client_items: [],
    });
    const order = vi.spyOn(ordersQueryClient, 'getOrderDetail').mockRejectedValue(unexpected);
    const registry = vi.spyOn(clientRegistryClient, 'query').mockRejectedValue(unexpected);
    const account = vi.spyOn(caseVirtualAccountClient, 'query').mockRejectedValue(unexpected);
    const reminder = vi.spyOn(paymentOverdueReminderClient, 'case').mockRejectedValue(unexpected);
    try {
      render(<FinancePage />);
      fireEvent.click(await screen.findByRole('button', { name: `核對交易 ${row.reference}` }));
      const review = within(screen.getByRole('dialog', { name: '核對交易' }));
      expect(await review.findByText(reason)).toBeVisible();
      expect(readCase).toHaveBeenCalledTimes(subsidyNtd === undefined ? 0 : 1);
      expect(staffRecovery).not.toHaveBeenCalled();
      fireEvent.click(review.getByRole('button', { name: '查看本案帳務' }));
      const caseView = within(await screen.findByRole('dialog', { name: `案件帳務 · ${caseNo}` }));
      expect(await caseView.findByText(/^本案補助 /)).toBeVisible();
      staffRecovery.mockClear();
      fireEvent.click(caseView.getByRole('button', { name: '返回核對交易' }));
      const returned = within(await screen.findByRole('dialog', { name: '核對交易' }));
      expect(await returned.findByText(reason)).toBeVisible();
      expect(returned.queryByRole('group', { name: '候選案件' })).not.toBeInTheDocument();
      expect(returned.queryByRole('button', { name: /預覽|確認|更正|單筆人工核對|移除誤匯入明細|調整本案/ })).not.toBeInTheDocument();
      expect(financeImportQueryClient.pairBankTransaction).not.toHaveBeenCalled();
      expect(financeImportQueryClient.excludeBankTransaction).not.toHaveBeenCalled();
      expect(batchPreview).not.toHaveBeenCalled();
      expect(staffQuery).not.toHaveBeenCalled();
      expect(staffRecovery).not.toHaveBeenCalled();
      expect(staffPreview).not.toHaveBeenCalled();
      expect(refundPreview).not.toHaveBeenCalled();
      expect(post).not.toHaveBeenCalled();
    } finally {
      [post, batchPreview, staffQuery, staffRecovery, staffPreview, refundPreview, readCase, order, registry, account, reminder]
        .forEach(mock => mock.mockRestore());
      window.location.hash = '';
    }
  });

  it.each(['success', 'typed conflict', 'terminal failure'] as const)(
    'rechecks the same client subsidy refund after viewing the case and handles %s', async (confirmation) => {
    window.location.hash = '#finance?tab=bank';
    const caseNo = '115000001';
    const obligationIdentity = 'client:subsidy-return';
    const row: FinanceBankTransaction = {
      ...taishin, direction: 'outgoing', classification_type: 'client_subsidy_return', cases: [caseNo],
      staff_subsidy_batch_identity: 'finance-import-batch:9',
      reconciliation_target: { case_no: caseNo, obligation_identities: [obligationIdentity], staff_id: null },
    };
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({items: [row], pending_count: 1, next_before_row_id: null});
    const candidate = {
      row_identity: row.row_identity, batch_identity: 'finance-import-batch:7', classification_type: 'client_subsidy_return',
      owning_domain: 'client_finance', bank_amount_ntd: row.amount_ntd,
      allocations: [{ obligation_identity: obligationIdentity, amount_ntd: row.amount_ntd }],
      reason: '', evidence: [row.reference], refund_ledger_entry_identity: null, candidate_fingerprint: 'a'.repeat(64),
      allow_partial_refund_recovery: false, allow_refund_overage_recovery: false, allow_client_receipt_overage: false,
      refund_summary: { transfer_fee_ntd: 0, remaining_ntd: 0 },
    };
    const checked = { candidate, batch_version: 1, canonical_fact_version: 1, alert_version: 0, preview_fingerprint: 'b'.repeat(64) };
    const batchPreview = vi.spyOn(financeImportMutationClient, 'preview');
    const staffPreview = vi.spyOn(staffPayoutRemediationClient, 'preview');
    const preview = vi.spyOn(financeImportCorrectionClient, 'preview')
      .mockRejectedValueOnce(new Error('原銀行出款早於正式退款日。')).mockResolvedValue(checked);
    const apply = vi.spyOn(financeImportCorrectionClient, 'apply').mockResolvedValue({ job_id: 'refund-job', status_url: '/refund-job', replayed: false });
    const outcome = vi.spyOn(financeImportCorrectionClient, 'queryOutcome').mockResolvedValue({
      job_id: 'refund-job', status: 'succeeded', attempt_count: 1, max_attempts: 1, result_reference: 'refund-receipt',
      receipt: { row_identity: row.row_identity, batch_identity: candidate.batch_identity, preview_fingerprint: checked.preview_fingerprint,
        resulting_batch_version: 2, classification_event_count: 1, ledger_entry_count: 1, allocation_count: 1,
        reconciliation_receipt_count: 1, alert_resolved_event_count: 0 },
    });
    if (confirmation === 'typed conflict') {
      apply.mockRejectedValueOnce(new FinanceImportQueryError('stale_preview', '退款資料版本已變更。', false, 409));
    }
    if (confirmation === 'terminal failure') {
      outcome.mockResolvedValueOnce({ job_id: 'refund-job', status: 'failed', attempt_count: 1, max_attempts: 1,
        result_reference: null, receipt: null, failure_code: 'stale_preview' });
    }
    const mocks = [preview, apply, outcome, batchPreview, staffPreview,
      vi.spyOn(financeAccountingClient, 'query').mockResolvedValue({ case_no: caseNo, client_name: '合成客戶',
        receivable_ntd: 0, received_ntd: 0, payable_ntd: row.amount_ntd, paid_ntd: 0, pending_warning_count: 0,
        staff_items: [], transactions: [], warnings: [], client_items: [{ identity: obligationIdentity,
          direction: 'payable', label: '客戶補助退款', party: '合成客戶', expected_ntd: row.amount_ntd,
          actual_ntd: 0, remaining_ntd: row.amount_ntd, has_payment: false, version: '1', due_date: '2026-01-09' }] }),
      vi.spyOn(clientSettlementRemediationClient, 'query').mockResolvedValue({ case_no: caseNo, account_version: 2,
        as_of: '2026-01-09', receivable_obligations: [], refund_obligations: [], subsidy_return_obligations: [],
        incoming_bank_facts: [], refund_bank_facts: [], subsidy_return_bank_facts: [] }),
      vi.spyOn(ordersQueryClient, 'getOrderDetail').mockRejectedValue(new Error('not needed')),
      vi.spyOn(clientRegistryClient, 'query').mockRejectedValue(new Error('not needed')),
      vi.spyOn(caseVirtualAccountClient, 'query').mockRejectedValue(new Error('not needed')),
      vi.spyOn(paymentOverdueReminderClient, 'case').mockRejectedValue(new Error('not needed')),
    ];
    try {
      render(<FinancePage />);
      fireEvent.change(await screen.findByLabelText('篩選銀行'), { target: { value: 'taishin' } });
      fireEvent.click(await screen.findByRole('button', { name: `核對交易 ${row.reference}` }));
      const reviewDrawer = within(await screen.findByRole('dialog', { name: /核對交易/ }));
      const previewButton = await reviewDrawer.findByRole('button', { name: '預覽核銷' });
      expect(reviewDrawer.getByText('退客戶先墊補助')).toBeVisible();
      fireEvent.click(previewButton);
      expect(await reviewDrawer.findByText('原銀行出款早於正式退款日。')).toBeVisible();
      expect(reviewDrawer.queryByRole('button', { name: '確認核銷' })).not.toBeInTheDocument();
      fireEvent.click(previewButton);
      await reviewDrawer.findByRole('button', { name: '確認核銷' });

      await waitFor(() => expect(reviewDrawer.getByRole('button', { name: '查看本案帳務' })).toBeEnabled());
      fireEvent.click(reviewDrawer.getByRole('button', { name: '查看本案帳務' }));
      const rowLookups = vi.mocked(financeImportQueryClient.listBankTransactions).mock.calls.filter(([query]) => query.row_id === row.row_id).length;
      expect(preview).toHaveBeenCalledTimes(2);
      fireEvent.click(await reviewDrawer.findByRole('button', { name: '返回核對交易' }));
      await waitFor(() => expect(preview).toHaveBeenCalledTimes(3));
      expect(vi.mocked(financeImportQueryClient.listBankTransactions).mock.calls.filter(([query]) => query.row_id === row.row_id).length).toBeGreaterThan(rowLookups);
      expect(apply).not.toHaveBeenCalled();

      const confirm = await reviewDrawer.findByRole('button', { name: '確認核銷' });
      act(() => { confirm.click(); confirm.click(); });
      expect(apply).toHaveBeenCalledTimes(1);
      if (confirmation === 'success') {
        await waitFor(() => expect(outcome).toHaveBeenCalledWith('refund-job'));
        await waitFor(() => expect(screen.queryByRole('dialog', { name: '核對交易' })).not.toBeInTheDocument());
      } else {
        const error = confirmation === 'typed conflict' ? '退款資料版本已變更。' : /資料已更新，請重新查詢並預覽/;
        expect(await reviewDrawer.findByText(error)).toBeVisible();
        expect(reviewDrawer.queryByRole('button', { name: /以原操作確認更正結果|確認核銷/ })).not.toBeInTheDocument();
        if (confirmation === 'typed conflict') expect(outcome).not.toHaveBeenCalled();
        fireEvent.click(reviewDrawer.getByRole('button', { name: '預覽核銷' }));
        expect(await reviewDrawer.findByRole('button', { name: '確認核銷' })).toBeEnabled();
        expect(apply).toHaveBeenCalledTimes(1);
      }
      expect(preview).toHaveBeenLastCalledWith(expect.objectContaining({ row_identity: row.row_identity,
        classification_type: 'client_subsidy_return', target_obligation_identities: [obligationIdentity] }));
      expect(batchPreview).not.toHaveBeenCalled();
      expect(staffPreview).not.toHaveBeenCalled();
      expect(screen.getByLabelText('篩選銀行')).toHaveValue('taishin');
    } finally {
      mocks.forEach(mock => mock.mockRestore());
      window.location.hash = '';
    }
  });

  it('keeps one terminal Sinopac review mounted from bank selection to a verified receipt', async () => {
    window.location.hash = '#finance?tab=bank';
    const caseNo = '115000001';
    const row: FinanceBankTransaction = {
      ...sinopac, amount_ntd: 5000, service_end_receipt_case_no: caseNo, reconciliation_target: null,
      review_reason: 'sinopac_client_receipt_no_open_obligation',
    };
    const jobId = 'terminal-sinopac-job';
    const batchIdentity = 'finance-import-batch:17';
    const fingerprint = 'a'.repeat(64);
    const receipt = {
      row_identity: row.row_identity, batch_identity: batchIdentity, preview_fingerprint: fingerprint,
      resulting_batch_version: 2, classification_event_count: 1, ledger_entry_count: 1, allocation_count: 1,
      reconciliation_receipt_count: 1, alert_resolved_event_count: 0,
    };
    let confirmed = false;
    const wrap = <T,>(data: T) => ({ success: true, message: 'ok', error: null, data });
    vi.mocked(financeImportQueryClient.listBankTransactions).mockImplementation(async query => ({
      items: confirmed ? (query.transaction_status === 'posted' || query.row_id
        ? [{ ...row, status: 'posted', service_end_receipt_case_no: null }] : []) : [row],
      pending_count: confirmed ? 0 : 1, next_before_row_id: null,
    }));
    const token = vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-token');
    const post = vi.spyOn(transport, 'post').mockImplementation(async path => {
      if (path === '/api/v1/finance-import/corrections/preview') return wrap({
        candidate: {
          row_identity: row.row_identity, batch_identity: batchIdentity, classification_type: 'client_receipt',
          owning_domain: 'client_finance', bank_amount_ntd: 5000, allocations: [], reason: '',
          evidence: ['永豐對帳單已驗證同案入款'], refund_ledger_entry_identity: null,
          allow_partial_refund_recovery: false, allow_refund_overage_recovery: false,
          allow_client_receipt_overage: false, candidate_fingerprint: 'b'.repeat(64),
          service_end_receipt: { case_no: caseNo, service_due_ntd: 0, fee_ntd: 0,
            new_refund_ntd: 5000, pending_refund_ntd: 5000 }, refund_summary: null,
        },
        batch_version: 1, canonical_fact_version: 1, alert_version: 0, preview_fingerprint: fingerprint,
      }) as never;
      if (path === '/api/v1/finance-import/corrections/apply') return wrap({
        job_id: jobId, status_url: '/jobs/' + jobId, replayed: false,
      }) as never;
      throw new Error(`unexpected POST ${path}`);
    });
    const get = vi.spyOn(transport, 'get').mockImplementation(async path => {
      if (path === `/api/v1/finance-import/jobs/${jobId}/correction-outcome`) {
        confirmed = true;
        return wrap({ job_id: jobId, status: 'succeeded', attempt_count: 1, max_attempts: 1,
          result_reference: `finance_import_correction:${row.row_identity}`, receipt, failure_code: null }) as never;
      }
      throw new Error(`unexpected GET ${path}`);
    });
    const readCase = vi.spyOn(financeAccountingClient, 'query').mockRejectedValue(new Error('synthetic case'));
    const warnings = vi.spyOn(console, 'error');
    try {
      render(<FinancePage />);
      fireEvent.click(await screen.findByRole('button', { name: `核對交易 ${row.reference}` }));
      const drawer = within(await screen.findByRole('dialog', { name: '核對交易' }));
      const preview = await drawer.findByRole('button', { name: '預覽核銷' });
      expect(drawer.getAllByRole('region', { name: '銀行款項更正' })).toHaveLength(1);
      expect(drawer.getByRole('button', { name: '移除誤匯入明細' })).toBeEnabled();
      fireEvent.click(preview);
      const confirm = await drawer.findByRole('button', { name: '確認核銷' });
      expect(drawer.getByLabelText('永豐入款結算預覽')).toHaveTextContent('5,000');
      expect(drawer.getAllByRole('region', { name: '銀行款項更正' })).toHaveLength(1);
      expect(post.mock.calls.map(([path]) => path)).toEqual(['/api/v1/finance-import/corrections/preview']);
      expect(readCase).not.toHaveBeenCalled();
      expect(warnings.mock.calls.some(call => call.some(value => String(value).includes('same key')))).toBe(false);
      fireEvent.click(confirm);
      await screen.findByRole('dialog', { name: `案件帳務 · ${caseNo}` });
      await waitFor(() => expect(readCase).toHaveBeenCalledWith(caseNo, expect.any(AbortSignal)));
      expect(post.mock.calls.map(([path]) => path)).toEqual([
        '/api/v1/finance-import/corrections/preview',
        '/api/v1/finance-import/corrections/apply',
      ]);
      expect(post.mock.calls[1][1]).toMatchObject({ row_identity: row.row_identity,
        service_end_case_no: caseNo, classification_type: 'client_receipt', preview_fingerprint: fingerprint });
      expect(get.mock.calls.filter(([path]) => path.endsWith('/correction-outcome'))).toHaveLength(1);
    } finally {
      [get, post, token, readCase, warnings].forEach(mock => mock.mockRestore());
      window.location.hash = '';
    }
  });

  it.each([false, true])('offers single-transaction manual staff review only for backend eligibility %s', async (allowed) => {
    window.location.hash = '#finance?tab=bank';
    const row: FinanceBankTransaction = { ...taishin, direction: 'outgoing', classification_type: 'staff_payout',
      recorded_pending_reason: 'outgoing_staff_payout_month_no_match', staff_subsidy_manual_review_allowed: allowed,
      reconciliation_target: { case_no: '115000001', obligation_identities: ['staff:payment'], staff_id: 19 } };
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [row], pending_count: 1, next_before_row_id: null,
    });
    const readCase = vi.spyOn(financeAccountingClient, 'query').mockRejectedValue(new Error('synthetic case'));
    try {
      render(<FinancePage />);
      const transaction = within(await screen.findByRole('row', { name: /交易明細#3/ }));
      expect(transaction.getAllByRole('button', { name: /核對交易|單筆人工核對/ })).toHaveLength(1);
      fireEvent.click(transaction.getByRole('button', { name: /核對交易/ }));
      const review = within(screen.getByRole('dialog', { name: '核對交易' }));
      await review.findByRole('heading', { name: '未能核對原因' });
      if (allowed) {
        fireEvent.click(review.getByRole('button', { name: '單筆人工核對' }));
        await waitFor(() => expect(readCase).toHaveBeenCalledWith('115000001', expect.any(AbortSignal)));
      } else {
        expect(review.queryByRole('button', { name: '單筆人工核對' })).not.toBeInTheDocument();
        expect(readCase).not.toHaveBeenCalled();
      }
    } finally { readCase.mockRestore(); window.location.hash = ''; }
  });

  it('previews and applies the selected same-month staff subsidy case for only the original transaction and refreshes after receipt', async () => {
    window.location.hash = '#finance?tab=bank';
    const rowIdentity = 'finance-import-row:102';
    const batchIdentity = 'finance-import-batch:9';
    const selectedCaseNo = '115000002';
    const previewFingerprint = 'b'.repeat(64);
    const jobId = 'staff-subsidy-job';
    const row: FinanceBankTransaction = { ...taishin, direction: 'outgoing', classification_type: 'staff_payout',
      transaction_date: '2026-11-10', amount_ntd: 7970, staff_subsidy_batch_identity: batchIdentity };
    const reconciled: FinanceBankTransaction = { ...row, status: 'posted', disposition: 'existing' };
    let settled = false;
    const readBankTransactions = vi.mocked(financeImportQueryClient.listBankTransactions);
    readBankTransactions.mockImplementation(async query => {
      const current = settled ? reconciled : row;
      const matches = query.row_id === row.row_id || (!query.row_id && query.transaction_status === current.status);
      return { items: matches ? [current] : [], pending_count: settled ? 0 : 1, next_before_row_id: null };
    });
    const preview = vi.spyOn(financeImportMutationClient, 'preview').mockImplementation(async (_batch, _signal, selections) => {
      const chosen = selections?.[rowIdentity] === selectedCaseNo;
      return {
        batch_identity: batchIdentity, batch_version: 0, source_content_digest: 'a'.repeat(64),
        classifier_version: 'v1', fingerprint_version: 'v1', preview_fingerprint: chosen ? previewFingerprint : 'c'.repeat(64),
        rows: [{
          row_identity: rowIdentity, canonical_fact_version: 0, amount_ntd: row.amount_ntd,
          classification_type: 'staff_payout', disposition: chosen ? 'create' : 'business_pending',
          pending_reason: chosen ? null : 'staff_subsidy_multiple_same_month_cases',
          target_identities: chosen ? ['staff:subsidy-second'] : [],
          evidence: [], available_actions: [], integrity_violations: [],
          fingerprint_collision: false, formal_reference_conflict: false,
          selected_staff_subsidy_case: chosen ? selectedCaseNo : null,
          staff_subsidy_cases: [
            { case_no: '115000001', payable_due_date: '2026-11-15', payable_amount_ntd: 12000 },
            { case_no: selectedCaseNo, payable_due_date: '2026-11-15', payable_amount_ntd: 8000 },
          ],
        }], apply_allowed: true, blocking_codes: [], dispatch_summaries: [],
        counts: { source_rows: 1, canonical_created: 1, duplicate_occurrences: 0,
          ready_dispatch: chosen ? 1 : 0, existing: 0, manual_review: 0, business_pending: chosen ? 0 : 1, blocked: 0 },
      };
    });
    const token = vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-session');
    const post = vi.spyOn(transport, 'post').mockResolvedValue({ success: true, message: '', error: null,
      data: { job_id: jobId, status_url: '/staff-subsidy-job', replayed: false } });
    let finishReceipt: () => void = () => { throw new Error('尚未查詢本筆核銷結果。'); };
    const outcome = vi.spyOn(financeImportMutationClient, 'queryBatchOutcome').mockImplementation(() => new Promise(resolve => {
      finishReceipt = () => {
        settled = true;
        resolve({ job_id: jobId, status: 'succeeded', attempt_count: 1, max_attempts: 1, result_reference: 'staff-subsidy-receipt',
          receipt: { batch_identity: batchIdentity, preview_fingerprint: previewFingerprint, resulting_batch_version: 1,
            reconciled_count: 1, existing_count: 0, pending_count: 0 } });
      };
    }));
    try {
      render(<FinancePage />);
      fireEvent.click(await screen.findByRole('button', { name: `核對交易 ${row.reference}` }));
      const review = within(screen.getByRole('dialog', { name: '核對交易' }));
      const firstGroup = await review.findByRole('group', { name: '選擇同月補助案件' });
      expect(within(firstGroup).getByRole('button', { name: /115000001.*12,000/ })).toHaveAttribute('aria-pressed', 'false');
      fireEvent.click(screen.getByRole('button', { name: '關閉核對交易' }));
      fireEvent.click(await screen.findByRole('button', { name: `查看交易 ${rowIdentity}` }));
      const detail = screen.getByRole('dialog', { name: '待核對交易明細' });
      fireEvent.click(within(detail).getByRole('button', { name: '核對交易' }));
      const reopenedReview = within(screen.getByRole('dialog', { name: '核對交易' }));
      const group = await reopenedReview.findByRole('group', { name: '選擇同月補助案件' });
      expect(preview).toHaveBeenCalledTimes(2);
      expect(preview).toHaveBeenLastCalledWith(batchIdentity, expect.any(AbortSignal), undefined, false, rowIdentity);
      expect(reopenedReview.queryByRole('button', { name: '確認核銷本筆交易' })).not.toBeInTheDocument();
      const second = within(group).getByRole('button', { name: /115000002.*8,000/ });
      expect(second).toHaveAttribute('aria-pressed', 'false');
      const countPendingListReads = () => readBankTransactions.mock.calls.filter(([query]) =>
        query.transaction_status === 'pending' && query.row_id === undefined,
      ).length;
      const pendingReadsBeforeSelectedPreview = countPendingListReads();
      // Flush the resolved Preview and its read-only refresh before measuring Apply.
      await act(async () => { fireEvent.click(second); });
      expect(preview).toHaveBeenLastCalledWith(batchIdentity, expect.any(AbortSignal), { [rowIdentity]: selectedCaseNo }, false, rowIdentity);
      expect(await reopenedReview.findByRole('button', { name: /115000002.*8,000/, pressed: true })).toBeVisible();
      expect(countPendingListReads()).toBeGreaterThan(pendingReadsBeforeSelectedPreview);
      const confirm = reopenedReview.getByRole('button', { name: '確認核銷本筆交易' });
      expect(post).not.toHaveBeenCalled();
      readBankTransactions.mockClear();
      await act(async () => { fireEvent.click(confirm); });
      await waitFor(() => expect(outcome).toHaveBeenCalledWith(jobId, expect.any(AbortSignal)));
      expect(post).toHaveBeenCalledTimes(1);
      expect(post).toHaveBeenCalledWith('/api/v1/finance-import/batches/apply', {
        batch_identity: batchIdentity, expected_batch_version: 0, preview_fingerprint: previewFingerprint, reason: '',
        review_row_identity: rowIdentity, staff_subsidy_selections: { [rowIdentity]: selectedCaseNo },
      }, expect.objectContaining({ headers: expect.objectContaining({ 'Idempotency-Key': expect.any(String) }) }));
      expect(reopenedReview.getByText('正在確認本筆核銷結果…')).toBeVisible();
      expect(reopenedReview.queryByText('本筆交易已核銷。')).not.toBeInTheDocument();
      expect(reopenedReview.getByRole('region', { name: '銀行原始交易事實' })).not.toHaveTextContent('已核銷');
      expect(readBankTransactions).not.toHaveBeenCalled();
      await act(async () => finishReceipt());
      expect(await reopenedReview.findByText('本筆交易已核銷。')).toBeVisible();
      await waitFor(() => expect(readBankTransactions).toHaveBeenCalledWith(
        expect.objectContaining({ transaction_status: 'pending' }), expect.objectContaining({ signal: expect.any(AbortSignal) }),
      ));
      fireEvent.click(screen.getByRole('button', { name: '關閉核對交易' }));
      expect(await screen.findByText('目前沒有符合條件的銀行交易資料。')).toBeVisible();
      expect(screen.queryByRole('button', { name: `核對交易 ${row.reference}` })).not.toBeInTheDocument();
      fireEvent.change(screen.getByRole('combobox', { name: '篩選處理狀態' }), { target: { value: 'posted' } });
      expect(await screen.findByRole('row', { name: /交易明細#3.*已核銷/ })).toBeVisible();
      expect(post).toHaveBeenCalledTimes(1);
    } finally {
      [preview, token, post, outcome].forEach(mock => mock.mockRestore());
      window.location.hash = '';
    }
  });

  it('預檢客戶補助退款只顯示候選，取得原操作成功回執後才讀回案件補助方案', async () => {
    window.location.hash = '#finance?tab=bank';
    const caseNo = '115000001';
    const batchIdentity = 'finance-import-batch:9';
    const fingerprint = 'a'.repeat(64);
    const row: FinanceBankTransaction = {
      ...taishin, direction: 'outgoing', amount_ntd: 12000, classification_type: 'client_subsidy_return',
      cases: [caseNo], client_subsidy_batch_identity: batchIdentity, reconciliation_target: null,
    };
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [row], pending_count: 1, next_before_row_id: null,
    });
    const preview = vi.spyOn(financeImportMutationClient, 'preview').mockResolvedValue({
      batch_identity: batchIdentity, batch_version: 0, preview_fingerprint: fingerprint,
      source_content_digest: 'b'.repeat(64), classifier_version: 'v1', fingerprint_version: 'v1',
      counts: { source_rows: 1, canonical_created: 1, duplicate_occurrences: 0, ready_dispatch: 1,
        existing: 0, manual_review: 0, business_pending: 0, blocked: 0 },
      rows: [{
        row_identity: row.row_identity, canonical_fact_version: 0, amount_ntd: 12000,
        classification_type: 'client_subsidy_return', disposition: 'create', target_identities: ['client:refund'],
        evidence: [], available_actions: ['reconcile'], integrity_violations: [], fingerprint_collision: false,
        formal_reference_conflict: false,
        subsidy_preflight: {
          case_no: caseNo, scheme: 'advance', subsidy_ntd: 12000, total_ntd: 48000, confirmation_only: false,
          payable_amount_ntd: 12000, payable_due_date: '2026-11-15', bank_cash_ntd: 12000, transfer_fee_ntd: 0,
          settlement_ntd: 12000, remaining_ntd: 0, blocker: null,
        },
      }], dispatch_summaries: [], blocking_codes: [], apply_allowed: true,
    });
    const apply = vi.spyOn(financeImportMutationClient, 'apply').mockResolvedValue({
      job_id: 'refund-job', status_url: '/refund-job', replayed: false,
    });
    const readCase = vi.spyOn(financeAccountingClient, 'query').mockResolvedValue({
      case_no: caseNo, client_name: '合成客戶', receivable_ntd: 48000, received_ntd: 48000, payable_ntd: 12000,
      paid_ntd: 12000, subsidy_ntd: 12000, scheme: 'advance', pending_warning_count: 0,
      client_items: [], staff_items: [], transactions: [], warnings: [],
    });
    let finish: () => void = () => { throw new Error('等待查詢核銷結果'); };
    const outcome = vi.spyOn(financeImportMutationClient, 'queryBatchOutcome').mockImplementation(() => new Promise(resolve => {
      finish = () => resolve({ job_id: 'refund-job', status: 'succeeded', attempt_count: 1, max_attempts: 1,
        result_reference: 'refund-receipt', receipt: { batch_identity: batchIdentity, preview_fingerprint: fingerprint,
          resulting_batch_version: 1, reconciled_count: 1, existing_count: 0, pending_count: 0 } });
    }));
    try {
      render(<FinancePage />);
      fireEvent.click(await screen.findByRole('button', { name: `核對交易 ${row.reference}` }));
      const review = within(await screen.findByRole('dialog', { name: '核對交易' }));
      expect(await review.findByText(/補助款退還客戶 · 明細候選/)).toBeVisible();
      expect(preview).toHaveBeenCalledWith(batchIdentity, expect.any(AbortSignal), undefined, false, row.row_identity);
      expect(apply).not.toHaveBeenCalled();
      expect(readCase).not.toHaveBeenCalled();
      fireEvent.click(review.getByRole('button', { name: '確認核銷本筆交易' }));
      await waitFor(() => expect(outcome).toHaveBeenCalledWith('refund-job', expect.any(AbortSignal)));
      expect(readCase).not.toHaveBeenCalled();
      expect(review.queryByText('本筆交易已核銷。')).not.toBeInTheDocument();
      await act(async () => finish());
      expect(await review.findByText('本筆交易已核銷。')).toBeVisible();
      expect(await review.findByText('本案補助方案 客戶先墊後退')).toBeVisible();
      expect(readCase).toHaveBeenCalledWith(caseNo, expect.any(AbortSignal));
    } finally {
      [preview, apply, readCase, outcome].forEach(mock => mock.mockRestore());
      window.location.hash = '';
    }
  });

  it.each(['typed conflict', 'timeout then conflict', 'failed', 'cancelled', 'unknown outcome'] as const)(
    'recovers a single staff subsidy Apply after %s', async firstResult => {
    window.location.hash = '#finance?tab=bank';
    const batchIdentity = 'finance-import-batch:9';
    const row: FinanceBankTransaction = {
      ...taishin, direction: 'outgoing', classification_type: 'staff_payout',
      staff_subsidy_batch_identity: batchIdentity,
    };
    const jobId = 'staff-subsidy-job';
    const conflictMessage = '本筆月嫂補助的預檢版本已變更。';
    let previewVersion = 0;
    let previewFingerprint = '';
    let applyCount = 0;
    let outcomeCount = 0;
    const readBankTransactions = vi.mocked(financeImportQueryClient.listBankTransactions);
    readBankTransactions.mockResolvedValue({ items: [row], pending_count: 1, next_before_row_id: null });
    const token = vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-session');
    const envelope = (data: unknown) => ({ success: true, message: '', error: null, data });
    const post = vi.spyOn(transport, 'post').mockImplementation(async path => {
      if (path.endsWith('/preview')) {
        previewVersion = firstResult === 'typed conflict' ? previewVersion + 1 : 1;
        previewFingerprint = previewVersion === 1 ? 'a'.repeat(64) : 'b'.repeat(64);
        return envelope({
          batch_identity: batchIdentity, batch_version: previewVersion, preview_fingerprint: previewFingerprint,
          source_content_digest: 'c'.repeat(64), classifier_version: 'v1', fingerprint_version: 'v1',
          counts: { source_rows: 1, canonical_created: 1, duplicate_occurrences: 0, ready_dispatch: 1,
            existing: 0, manual_review: 0, business_pending: 0, blocked: 0 },
          rows: [{ row_identity: row.row_identity, canonical_fact_version: previewVersion, amount_ntd: row.amount_ntd,
            classification_type: 'staff_payout', disposition: 'create', target_identities: ['staff:subsidy'],
            evidence: [], available_actions: [], integrity_violations: [], fingerprint_collision: false, formal_reference_conflict: false }],
          dispatch_summaries: [], blocking_codes: [], apply_allowed: true,
        });
      }
      expect(path).toBe('/api/v1/finance-import/batches/apply');
      applyCount += 1;
      if (firstResult === 'timeout then conflict' && applyCount === 1) throw new ApiTimeoutError(30_000);
      if ((firstResult === 'typed conflict' && applyCount === 1) || (firstResult === 'timeout then conflict' && applyCount === 2)) {
        throw new ApiHttpError(409, 'stale_preview', conflictMessage);
      }
      return envelope({ job_id: jobId, status_url: '/staff-subsidy-job', replayed: firstResult === 'timeout then conflict' });
    });
    const get = vi.spyOn(transport, 'get').mockImplementation(async path => {
      expect(path).toBe(`/api/v1/finance-import/jobs/${jobId}/batch-outcome`);
      outcomeCount += 1;
      if (outcomeCount === 1 && firstResult === 'unknown outcome') throw new ApiTimeoutError(30_000);
      const status = outcomeCount === 1 && (firstResult === 'failed' || firstResult === 'cancelled') ? firstResult : 'succeeded';
      return envelope({ job_id: jobId, status, attempt_count: 1, max_attempts: 1,
        result_reference: status === 'succeeded' ? 'staff-receipt' : null,
        receipt: status === 'succeeded' ? { batch_identity: batchIdentity, preview_fingerprint: previewFingerprint,
          resulting_batch_version: previewVersion + 1, reconciled_count: 1, existing_count: 0, pending_count: 0 } : null,
      });
    });
    const previewRequests = () => post.mock.calls.filter(([path]) => path.endsWith('/preview'));
    const applyRequests = () => post.mock.calls.filter(([path]) => path.endsWith('/apply'));
    try {
      render(<FinancePage />);
      fireEvent.click(await screen.findByRole('button', { name: `核對交易 ${row.reference}` }));
      const review = within(await screen.findByRole('dialog', { name: '核對交易' }));
      const confirm = await review.findByRole('button', { name: '確認核銷本筆交易' });
      expect(applyRequests()).toHaveLength(0);
      readBankTransactions.mockClear();
      fireEvent.click(confirm);
      if (firstResult === 'timeout then conflict') {
        const original = await review.findByRole('button', { name: '以原操作確認核銷結果' });
        expect(review.getByRole('button', { name: '關閉核對交易' })).toBeDisabled();
        expect(review.queryByRole('button', { name: '重新查詢本筆預檢' })).not.toBeInTheDocument();
        fireEvent.click(original);
        expect(await review.findByText(`${conflictMessage} 核銷結果尚未確認，請使用原操作重新確認。`)).toBeVisible();
        expect(review.getByRole('button', { name: '關閉核對交易' })).toBeDisabled();
        expect(review.queryByText('本筆交易已核銷。')).not.toBeInTheDocument();
        expect(previewRequests()).toHaveLength(1);
        expect(get).not.toHaveBeenCalled();
        expect(readBankTransactions).not.toHaveBeenCalled();
        fireEvent.click(review.getByRole('button', { name: '以原操作確認核銷結果' }));
        const [firstRequest] = applyRequests();
        expect(applyRequests()).toEqual([firstRequest, firstRequest, firstRequest]);
      } else if (firstResult === 'unknown outcome') {
        const observe = await review.findByRole('button', { name: '重新查詢核銷結果' });
        expect(review.getByRole('button', { name: '關閉核對交易' })).toBeDisabled();
        expect(review.queryByRole('button', { name: /重新查詢本筆預檢|以原操作確認核銷結果/ })).not.toBeInTheDocument();
        expect(readBankTransactions).not.toHaveBeenCalled();
        fireEvent.click(observe);
        expect(applyRequests()).toHaveLength(1);
        expect(get).toHaveBeenCalledTimes(2);
      } else {
        const recheck = await review.findByRole('button', { name: '重新查詢本筆預檢' });
        expect(review.getByRole('alert')).toHaveTextContent(firstResult === 'typed conflict' ? conflictMessage
          : firstResult === 'failed' ? '本筆核銷作業失敗。' : '本筆核銷作業已取消。');
        expect(review.getByRole('button', { name: '關閉核對交易' })).toBeEnabled();
        expect(review.queryByRole('button', { name: /以原操作確認核銷結果|確認核銷本筆交易/ })).not.toBeInTheDocument();
        expect(review.queryByText('本筆交易已核銷。')).not.toBeInTheDocument();
        expect(readBankTransactions).not.toHaveBeenCalled();
        expect(get).toHaveBeenCalledTimes(firstResult === 'typed conflict' ? 0 : 1);

        fireEvent.click(recheck);
        expect(previewRequests()).toHaveLength(2);
        expect(previewRequests()[1][1]).toEqual({ batch_identity: batchIdentity, review_row_identity: row.row_identity });
        const freshConfirm = await review.findByRole('button', { name: '確認核銷本筆交易' });
        expect(applyRequests()).toHaveLength(1);
        readBankTransactions.mockClear();
        fireEvent.click(freshConfirm);
        const [original, fresh] = applyRequests();
        expect(fresh[1]).toEqual(expect.objectContaining({
          preview_fingerprint: (firstResult === 'typed conflict' ? 'b' : 'a').repeat(64),
          expected_batch_version: firstResult === 'typed conflict' ? 2 : 1, review_row_identity: row.row_identity,
        }));
        expect(fresh[2]?.headers?.['Idempotency-Key']).not.toEqual(original[2]?.headers?.['Idempotency-Key']);
        expect(fresh[2]?.headers?.['X-Correlation-ID']).not.toEqual(original[2]?.headers?.['X-Correlation-ID']);
      }
      expect(await review.findByText('本筆交易已核銷。')).toBeVisible();
      await waitFor(() => expect(readBankTransactions).toHaveBeenCalled());
    } finally {
      [token, post, get].forEach(mock => mock.mockRestore());
      window.location.hash = '';
    }
  });

  it.each(['staff_payout','staff_salary'] as const)(
    'keeps Sinopac %s source failures consistent with payout preview and Apply and preserves the review entry', async classification => {
      const {cleanup}=await import('@testing-library/react');
      for(const source of ['recorded_pending_reason','dispatch_reason'] as const){
        for(const [code,expected] of [
          ['bank_transaction_date_missing','原銀行流水缺少交易日，無法核銷月嫂付款，請先查核來源資料。'],
          ['bank_currency_not_twd','原銀行流水幣別不是新臺幣，無法核銷月嫂付款，請先查核來源資料。'],
        ] as const){
          const row:FinanceBankTransaction={...sinopac,direction:'outgoing',classification_type:classification,
            transaction_date:code==='bank_transaction_date_missing'?null:sinopac.transaction_date,
            [source]:code,reconciliation_target:{case_no:'115000001',staff_id:7,obligation_identities:['staff:first']}};
          const presentation=financeBankReviewPresentation(row);
          expect(presentation.reason).toBe(expected);
          expect(presentation.reason).toBe(staffPayoutBlockerMessage(code,'sinopac'));
          expect(presentation.reason).not.toContain('退款／補助');
          expect(presentation.label).toBe('待核對');
          expect(presentation.nextStep).toContain(code==='bank_transaction_date_missing'?'交易日':'幣別');
          vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({items:[row],pending_count:1,next_before_row_id:null});
          render(<FinanceBankReconciliationWorkspace {...defaultProps}/>);
          expect(await screen.findByText(expected)).toBeInTheDocument();
          const review=screen.getByRole('button',{name:'核對交易 Sheet1#2'});
          expect(review).toBeEnabled();fireEvent.click(review);
          expect(onReconcile).toHaveBeenLastCalledWith(row);
          cleanup();
        }
      }
    });

  it('renders the WF-03 banner, KPI summary pills, and integrated filters', async () => {
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);

    expect(screen.getByText('兩家銀行，一處核對')).toBeInTheDocument();
    expect(screen.getByText('先辨識來源，再確認款項交給誰。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '匯入永豐對帳單' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '匯入台新對帳單' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '匯出對帳明細' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新配對並核銷' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '新增人工明細' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '匯入紀錄' })).toBeInTheDocument();
    expect(screen.queryByLabelText('篩選匯入批次')).not.toBeInTheDocument();

    const stats = await screen.findByLabelText('銀行對帳統計摘要');
    expect(stats).toHaveTextContent('待核對 2 筆');
    expect(stats).not.toHaveTextContent('已核銷');
    // Filters
    expect(screen.getByLabelText('篩選銀行')).toBeInTheDocument();
    expect(screen.getByLabelText('篩選方向')).toBeInTheDocument();
    expect(screen.getByLabelText('篩選處理狀態')).toBeInTheDocument();
    expect(screen.getByLabelText('交易起日')).toBeInTheDocument();
    expect(screen.getByLabelText('交易迄日')).toBeInTheDocument();
    expect(screen.getByLabelText('搜尋交易')).toBeInTheDocument();
  });

  it('searches transactions by associated case and allows opening the matched case', async () => {
    vi.mocked(financeImportQueryClient.listBankTransactions).mockImplementation(async query => {
      if (query.search === '115000001' || query.search === 'HC115000001') {
        return {
          items: [sinopac],
          pending_count: 1,
          next_before_row_id: null,
        };
      }
      return {
        items: [taishin, sinopac],
        pending_count: 2,
        next_before_row_id: null,
      };
    });

    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);
    expect(await screen.findByRole('button', { name: '核對交易 Sheet1#2' })).toBeVisible();

    const searchInput = screen.getByLabelText('搜尋交易');
    fireEvent.change(searchInput, { target: { value: '115000001' } });

    await waitFor(() => {
      expect(financeImportQueryClient.listBankTransactions).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: '115000001' }),
        expect.anything(),
      );
    });

    expect(await screen.findByRole('button', { name: '115000001' })).toBeVisible();
    expect(screen.queryByRole('button', { name: '核對交易 交易明細#3' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '115000001' }));
    expect(onCase).toHaveBeenCalledWith('115000001');
  });

  it('runs one rematch and refreshes the bank list after showing the counts', async () => {
    const rematch = vi.spyOn(financeImportMutationClient, 'reconcilePending').mockResolvedValue({
      checked_count: 5, reconciled_count: 3, existing_count: 0, pending_count: 2,
    });
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);
    await screen.findByLabelText('銀行對帳統計摘要');
    const initialRequests = vi.mocked(financeImportQueryClient.listBankTransactions).mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: '重新配對並核銷' }));
    expect(await screen.findByText('已查核 5 筆，核銷 3 筆，仍待核對 2 筆。')).toBeInTheDocument();
    expect(rematch).toHaveBeenCalledOnce();
    await waitFor(() => expect(financeImportQueryClient.listBankTransactions).toHaveBeenCalledTimes(initialRequests + 1));
    rematch.mockRestore();
  });

  it('marks a known difference separately from government period selection', async () => {
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [{ ...sinopac, recorded_client_receipt_review: { reason: 'client_receipt_underpaid', candidates: [] } }, taishin],
      pending_count: 2,
      next_before_row_id: null,
    });

    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);

    expect(within(await screen.findByRole('row', { name: /Sheet1#2/ })).getByText('金額不符')).toBeVisible();
    expect(within(screen.getByRole('row', { name: /交易明細#3/ })).getByText('待核對')).toBeVisible();
  });

  it.each<{
    name: string; patch: Partial<FinanceBankTransaction>; label: string; reason: RegExp; nextStep: RegExp;
  }>([
    { name: 'receipt underpaid', patch: { recorded_client_receipt_review: { reason: 'client_receipt_underpaid', candidates: [] } },
      label: '金額不符', reason: /實收低於/, nextStep: /請核對金額並選擇處理方式/ },
    { name: 'receipt overpaid', patch: { recorded_client_receipt_review: { reason: 'client_receipt_overpaid', candidates: [] } },
      label: '金額不符', reason: /實收高於/, nextStep: /請核對金額並選擇處理方式/ },
    ...(['sinopac', 'taishin'] as const).flatMap(bank => [
      { name: `${bank} staff amount`, patch: { bank, direction: 'outgoing' as const, classification_type: 'staff_payout', recorded_pending_reason: 'staff_payout_amount_mismatch' },
        label: '金額不符', reason: /銀行實付與本次待付合計/, nextStep: /請核對金額並選擇處理方式/ },
      { name: `${bank} staff candidates`, patch: { bank, direction: 'outgoing' as const, classification_type: 'staff_payout', recorded_pending_reason: 'outgoing_staff_payout_multiple_fee_matches' },
        label: '有多個候選款項', reason: /多個單筆或合併付款集合/, nextStep: /請選擇本次核銷款項/ },
      { name: `${bank} staff date`, patch: { bank, direction: 'outgoing' as const, classification_type: 'staff_payout', recorded_pending_reason: 'due_date_missing' },
        label: '待核對', reason: /缺少原預計撥款日/, nextStep: /請核對款項日期/ },
      { name: `${bank} refund amount`, patch: { bank, direction: 'outgoing' as const, classification_type: bank === 'sinopac' ? 'client_refund' : 'client_subsidy_return', recorded_pending_reason: 'outgoing_client_refund_amount_mismatch' },
        label: '金額不符', reason: /銀行實付/, nextStep: /請核對金額並選擇處理方式/ },
      { name: `${bank} refund candidates override old amount`, patch: { bank, direction: 'outgoing' as const, classification_type: bank === 'sinopac' ? 'client_refund' : 'client_subsidy_return', review_reason: 'outgoing_client_refund_amount_mismatch', recorded_pending_reason: 'outgoing_client_refund_multiple_fee_matches' },
        label: '有多個候選款項', reason: /多個單筆或合併/, nextStep: /請選擇本次核銷款項/ },
      { name: `${bank} refund date`, patch: { bank, direction: 'outgoing' as const, classification_type: bank === 'sinopac' ? 'client_refund' : 'client_subsidy_return', recorded_pending_reason: 'due_date_missing' },
        label: '待核對', reason: /缺少.*退款日|缺少.*到期日/, nextStep: /請核對款項日期/ },
    ]),
    { name: 'receipt candidates', patch: { recorded_client_receipt_review: {
      reason: 'sinopac_client_receipt_multiple_month_candidates', candidates: [
        { obligation_identity: 'test:first', obligation_type: 'first', due_date: '2026-10-19' },
        { obligation_identity: 'test:second', obligation_type: 'second', due_date: '2026-10-27' },
      ],
    } }, label: '有多個候選款項', reason: /第一期（到期日 2026-10-19）、第二期（到期日 2026-10-27）/, nextStep: /請選擇本次核銷款項/ },
    { name: 'receipt missing due date', patch: { recorded_client_receipt_review: { reason: 'due_date_missing', candidates: [] } },
      label: '待核對', reason: /缺少原到期日/, nextStep: /請核對款項日期/ },
    { name: 'missing transaction date overrides candidates', patch: { transaction_date: null, dispatch_reason: 'bank_transaction_date_missing', recorded_client_receipt_review: { reason: 'sinopac_client_receipt_multiple_month_candidates', candidates: [] } },
      label: '待核對', reason: /缺少交易日/, nextStep: /補正原銀行流水交易日/ },
    { name: 'currency overrides old and saved amount causes', patch: { review_reason: 'outgoing_client_refund_amount_mismatch', dispatch_reason: 'bank_currency_not_twd', recorded_pending_reason: 'client_receipt_underpaid' },
      label: '待核對', reason: /幣別不是新臺幣/, nextStep: /查核原銀行流水幣別/ },
    { name: 'generic operation failure preserves actual cause', patch: { dispatch_reason: 'bank_fact_not_eligible', recorded_pending_reason: 'client_receipt_underpaid' },
      label: '金額不符', reason: /實收低於/, nextStep: /請核對金額並選擇處理方式/ },
    { name: 'old source recognition only', patch: { review_reason: 'sinopac_valid_virtual_account' },
      label: '待核對', reason: /未留存當次未核銷原因，請進入核對確認/, nextStep: /未留存當次未核銷原因，請進入核對確認/ },
    { name: 'old unknown cause', patch: { review_reason: 'unrecognized_historical_reason' },
      label: '待核對', reason: /未留存當次未核銷原因，請進入核對確認/, nextStep: /未留存當次未核銷原因，請進入核對確認/ },
    { name: 'no saved cause', patch: { review_reason: null },
      label: '待核對', reason: /未留存當次未核銷原因，請進入核對確認/, nextStep: /未留存當次未核銷原因，請進入核對確認/ },
  ])('uses one actual cause for the badge and next step: $name', async ({ patch, label, reason, nextStep }) => {
    const transaction = { ...sinopac, ...patch };
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [transaction], pending_count: 1, next_before_row_id: null,
    });
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);
    const row = within(await screen.findByRole('row', { name: /Sheet1#2/ }));
    const cells = row.getAllByRole('cell');
    expect(cells[6]).toHaveTextContent(label);
    expect(row.getByText(reason)).toBeVisible();
    expect(row.getByText(nextStep)).toBeVisible();
    expect(row.queryByText('差額待核對')).not.toBeInTheDocument();
    fireEvent.click(row.getByRole('button', { name: '核對交易 Sheet1#2' }));
    expect(onReconcile).toHaveBeenCalledWith(transaction);
  });

  it.each([
    ['sinopac','client_receipt',['sinopac_valid_virtual_account','sinopac_virtual_account_matched']],
    ['sinopac','staff_payout',['outgoing_staff_payout_target_ambiguous','unique_staff_payout_name_month_fee_matched']],
    ['sinopac','client_refund',['outgoing_client_refund_target_ambiguous','client_refund_disambiguated_by_month_and_amount']],
    ['taishin','staff_payout',['outgoing_staff_payout_target_ambiguous','unique_staff_payout_name_and_month_matched']],
    ['taishin','client_subsidy_return',['outgoing_client_refund_target_ambiguous','taishin_client_subsidy_case_suffix_in_memo']],
  ] as const)('keeps legacy %s %s diagnostics unknown in the list and details, with the original review entry',async(bank,classification,codes)=>{
    const {cleanup}=await import('@testing-library/react');
    const message='未留存當次未核銷原因，請進入核對確認';
    for(const code of codes){
      for(const source of ['review_reason','recorded_pending_reason','dispatch_reason'] as const){
        const staff=classification==='staff_payout';
        const row:FinanceBankTransaction={...sinopac,bank,classification_type:classification,
          direction:classification==='client_receipt'?'incoming':'outgoing',review_reason:null,[source]:code,
          reconciliation_target:{case_no:'115000001',staff_id:staff?7:null,
            obligation_identities:[staff?'staff:first':classification==='client_receipt'?'receipt:first':'refund:first'],requires_selection:true}};
        const original=structuredClone(row);
        expect(financeBankReviewPresentation(row)).toEqual({label:'待核對',reason:message,nextStep:message});
        expect(financeImportReviewReason(row)).toBe(message);
        vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({items:[row],pending_count:1,next_before_row_id:null});
        render(<FinanceBankReconciliationWorkspace {...defaultProps}/>);
        const tableRow=within(await screen.findByRole('row',{name:/Sheet1#2/}));
        expect(tableRow.getAllByText(message)).toHaveLength(1);
        expect(tableRow.queryByText('金額不符')).not.toBeInTheDocument();
        expect(tableRow.queryByText('有多個候選款項')).not.toBeInTheDocument();
        fireEvent.click(tableRow.getByRole('button',{name:'核對交易 Sheet1#2'}));
        expect(onReconcile).toHaveBeenLastCalledWith(original);
        fireEvent.click(screen.getByRole('button',{name:'查看交易 finance-import-row:101'}));
        const details=within(screen.getByRole('dialog',{name:'待核對交易明細'}));
        expect(details.getByText(message)).toBeVisible();
        expect(row).toEqual(original);
        cleanup();
      }
    }
  });

  it('does not infer candidate count from an unknown review, or hide a saved concrete cause behind legacy diagnostics',()=>{
    const message='未留存當次未核銷原因，請進入核對確認';
    expect(financeBankReviewPresentation({
      ...sinopac, bank: 'sinopac', direction: 'outgoing', classification_type: 'staff_payout',
      review_reason: 'staff_payout_amount_mismatch', dispatch_reason: 'staff_bank_account_ambiguous',
      recorded_pending_reason: 'staff_bank_account_ambiguous',
    })).toMatchObject({ label: '金額不符' });
    expect(financeBankReviewPresentation({...sinopac,review_reason:'sinopac_client_receipt_shortfall'}))
      .toEqual({label:'待核對',reason:message,nextStep:message});
    expect(financeBankReviewPresentation({...sinopac,recorded_pending_reason:'sinopac_client_receipt_shortfall'}))
      .toMatchObject({label:'金額不符'});
    expect(financeBankReviewPresentation({...sinopac,recorded_client_receipt_review:{reason:'unrecognized_historical_reason',
      candidates:[{obligation_identity:'first',obligation_type:'first',due_date:'2026-10-19'},
                  {obligation_identity:'second',obligation_type:'second',due_date:'2026-10-27'}]}}))
      .toEqual({label:'待核對',reason:message,nextStep:message});
    expect(financeBankReviewPresentation({...sinopac,bank:'sinopac',direction:'outgoing',classification_type:'staff_payout',
      dispatch_reason:'outgoing_staff_payout_target_ambiguous',recorded_pending_reason:'staff_payout_amount_mismatch'}))
      .toMatchObject({label:'金額不符',reason:expect.stringContaining('銀行實付')});
    expect(financeBankReviewPresentation({...sinopac,recorded_pending_reason:'sinopac_valid_virtual_account',
      recorded_client_receipt_review:{reason:'sinopac_client_receipt_multiple_month_candidates',candidates:[]}}))
      .toMatchObject({label:'有多個候選款項'});
  });

  it('uses the preview cause only when no actual cause was saved, without reclassifying old ambiguous targets', () => {
    const preview = {
      row_identity: sinopac.row_identity, canonical_fact_version: 0, amount_ntd: sinopac.amount_ntd,
      classification_type: 'client_receipt', disposition: 'business_pending', target_identities: [],
      evidence: [], available_actions: [], integrity_violations: [], fingerprint_collision: false,
      formal_reference_conflict: false, pending_reason: 'client_receipt_underpaid',
    };
    expect(financeBankReviewPresentation(sinopac, preview)).toMatchObject({ label: '金額不符' });
    expect(financeBankReviewPresentation({ ...sinopac, recorded_pending_reason: 'due_date_missing' }, preview))
      .toMatchObject({ label: '待核對', nextStep: expect.stringContaining('請核對款項日期') });
    expect(financeBankReviewPresentation({ ...sinopac, classification_type: 'client_refund',
      recorded_pending_reason: 'outgoing_client_refund_target_ambiguous' }))
      .toMatchObject({ label: '待核對', reason: '未留存當次未核銷原因，請進入核對確認' });
    expect(financeBankReviewPresentation({ ...sinopac, review_reason: 'sinopac_client_receipt_shortfall' }))
      .toMatchObject({ label: '待核對', nextStep: expect.stringContaining('未留存當次未核銷原因') });
  });

  it('keeps the manual-scheme hint only while purpose remains unconfirmed, below actual posting causes',()=>{
    const original={...sinopac,bank:'taishin' as const,direction:'outgoing' as const,
      classification_type:'non_business_review',review_reason:'taishin_memo_case_requires_manual_scheme'};
    expect(financeBankReviewPresentation(original)).toMatchObject({label:'待人工確認方案'});
    expect(financeBankReviewPresentation({...original,classification_type:'client_subsidy_return',
      dispatch_reason:'outgoing_client_refund_amount_mismatch'})).toMatchObject({label:'金額不符'});
    expect(financeBankReviewPresentation({...original,classification_type:'client_subsidy_return',
      recorded_pending_reason:'outgoing_client_refund_multiple_fee_matches'})).toMatchObject({label:'有多個候選款項'});
  });

  it.each([
    ['unique_staff_payout_name_and_month_matched', null, /未留存當次未核銷原因，請進入核對確認/],
    ['outgoing_staff_payout_month_no_match', null, /未留存當次未核銷原因，請進入核對確認/],
    ['outgoing_client_refund_month_no_match', null, /未留存當次未核銷原因，請進入核對確認/],
    ['sinopac_client_receipt_month_no_match', null, /未留存當次未核銷原因，請進入核對確認/],
    ['outgoing_client_refund_amount_mismatch', 'client_refund_recipient_account_mismatch', /與待退款項的收款帳戶不符/],
    ['sinopac_unique_staff_account_in_transaction_reference', 'staff_bank_account_ambiguous', /唯一有效的月嫂主要帳戶/],
    ['unique_staff_payout_name_and_month_matched', 'staff_memo_recipient_unconfirmed', /備註姓名驗證未通過/],
    ['taishin_client_subsidy_case_suffix_in_memo', 'client_subsidy_memo_recipient_unconfirmed', /銀行備註無法確認本案客戶補助對象/],
    ['sinopac_valid_virtual_account', null, /未留存當次未核銷原因，請進入核對確認/],
    ['unrecognized_historical_reason', null, /未留存當次未核銷原因，請進入核對確認/],
    [null, null, /未留存當次未核銷原因，請進入核對確認/],
  ] as const)('shows the concrete reason in transaction details (%s, %s)', async (review_reason, dispatch_reason, message) => {
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [{ ...sinopac, review_reason, dispatch_reason }],
      pending_count: 1,
      next_before_row_id: null,
    });
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);

    fireEvent.click(await screen.findByRole('button', { name: '查看交易 finance-import-row:101' }));
    const dialog = screen.getByRole('dialog', { name: '待核對交易明細' });
    expect(within(dialog).getByRole('heading', { name: '未自動核銷原因' })).toBeVisible();
    expect(within(dialog).getByText(message)).toBeVisible();
    expect(onReconcile).not.toHaveBeenCalled();
  });

  it('shows recorded same-month candidates and their due dates in the existing reason field', async () => {
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [{ ...sinopac, reconciliation_target: null, recorded_client_receipt_review: {
        reason: 'sinopac_client_receipt_multiple_same_month_exact',
        candidates: [
          { obligation_identity: 'test:first', obligation_type: 'first', due_date: '2026-10-19' },
          { obligation_identity: 'test:second', obligation_type: 'second', due_date: '2026-10-27' },
        ],
      } }], pending_count: 1, next_before_row_id: null,
    });
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);

    const reason = /同月有多筆候選期款.*第一期（到期日 2026-10-19）、第二期（到期日 2026-10-27）/;
    expect(within(await screen.findByRole('row', { name: /Sheet1#2/ })).getByText(reason)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '查看交易 finance-import-row:101' }));
    expect(within(screen.getByRole('dialog', { name: '待核對交易明細' })).getByText(reason)).toBeVisible();
    expect(onReconcile).not.toHaveBeenCalled();
  });

  it('keeps the reconciliation entry for a period with no due date and displays that actual cause',async()=>{
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({items:[{...sinopac,
      recorded_client_receipt_review:{reason:'due_date_missing',candidates:[{obligation_identity:'first',obligation_type:'first',due_date:null}]},
      reconciliation_target:{case_no:'115000001',staff_id:null,obligation_identities:['first'],requires_selection:true},
    }],pending_count:1,next_before_row_id:null});
    render(<FinanceBankReconciliationWorkspace {...defaultProps}/>);
    expect(await screen.findByText(/待收期款缺少原到期日/)).toHaveTextContent('第一期（到期日 未設定）');
    fireEvent.click(screen.getByRole('button',{name:/核對交易/}));
    expect(onReconcile).toHaveBeenCalledWith(expect.objectContaining({
      row_identity:sinopac.row_identity,reconciliation_target:{case_no:'115000001',staff_id:null,obligation_identities:['first'],requires_selection:true},
    }));
  });

  it('reports a failed batch without assigning its failure to an otherwise eligible row', () => {
    const preview = {
      row_identity: sinopac.row_identity, canonical_fact_version: 0, amount_ntd: sinopac.amount_ntd,
      classification_type: 'client_receipt', disposition: 'create', target_identities: ['test:first'],
      evidence: [], available_actions: [], integrity_violations: [], fingerprint_collision: false,
      formal_reference_conflict: false,
    };
    expect(financeImportReviewReason(sinopac, preview, 'apply_failed'))
      .toBe('流水已保存。當次批次核銷未完成。未留存當次阻擋原因。');
  });

  it('posts a government outflow to the selected period refund balance', async () => {
    const period = {
      period: { unit: 'quarter' as const, year: 2026, index: 4 },
      version: 2, label: '測試期間', lines: [], total_ntd: 1000,
      coverage: [{ receipt_id: 17, period: { unit: 'quarter' as const, year: 2026, index: 4 },
        amount_ntd: 1100, recovered_advance_ntd: 0, label: '原款' }],
      blocked_cases: [], recorded_lines: [], changed_cases: [], can_reconcile: false,
      balances: [{ identity: 'government-period:17', root_receipt_id: 17, kind: 'original',
        case_no: null, direction: 'receivable', expected_ntd: 1000, received_ntd: 1100,
        recognized_ntd: 0, returned_ntd: 0, remaining_ntd: 0, refund_due_ntd: 100, settled: false, status: 'pending' }],
    };
    const query = vi.spyOn(subsidyPeriodClient, 'query').mockResolvedValue(period);
    const difference = vi.spyOn(subsidyPeriodClient, 'difference').mockResolvedValue(period);
    try {
      vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
        items: [{ ...taishin, direction: 'outgoing', amount_ntd: 100 }], pending_count: 1, next_before_row_id: null,
      });
      window.location.hash = '#finance?tab=bank';
      render(<FinancePage />);
      fireEvent.click(await screen.findByRole('button', { name: '核對交易 交易明細#3' }));
      const dialog = screen.getByRole('dialog', { name: '核對交易' });
      fireEvent.change(await within(dialog).findByLabelText('款項'), { target: { value: 'government-period:17' } });
      fireEvent.click(within(dialog).getByRole('checkbox', { name: /我已核對/ }));
      fireEvent.click(within(dialog).getByRole('button', { name: '確認記錄本次處理' }));
      expect(difference).toHaveBeenCalledWith(expect.objectContaining({
        action: 'refund', identity: 'government-period:17', bank_row_id: 102,
        expected_version: 2, handling: '',
      }));
    } finally {
      query.mockRestore();
      difference.mockRestore();
      window.location.hash = '';
    }
  });

  it.each([false, true])('opens the shared case drawer with the clicked bank source (manual selection: %s)', async (manual) => {
    window.location.hash = '#finance?tab=bank';
    if (manual) vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [{ ...sinopac, reconciliation_target: { case_no: '115000001', staff_id: null,
        obligation_identities: ['receipt:first', 'receipt:second'], requires_selection: true } }],
      pending_count: 1, next_before_row_id: null,
    });
    const mocks = [
      vi.spyOn(financeAccountingClient, 'query').mockResolvedValue({
        case_no: '115000001', client_name: '測試客戶', receivable_ntd: 20000, received_ntd: 0,
        payable_ntd: 0, paid_ntd: 0, remaining_in_ntd: 20000, remaining_out_ntd: 0,
        pending_warning_count: 0, warnings: [], transactions: [], staff_items: [],
        client_items: [{
          identity: 'receipt:first', direction: 'receivable', label: '第一期', party: '測試客戶',
          expected_ntd: 20000, actual_ntd: 0, remaining_ntd: 20000, has_payment: false, version: '1', due_date: '2026-01-08',
        }, {
          identity: 'receipt:second', direction: 'receivable', label: '第二期', party: '測試客戶',
          expected_ntd: 12000, actual_ntd: 0, remaining_ntd: 12000, has_payment: false, version: '1', due_date: '2026-01-27',
        }],
      }),
      vi.spyOn(clientReceiptQueryClient, 'query').mockResolvedValue({
        case_no: '115000001', account_version: 1,
        bank_facts: [101, 103].map(finance_import_row_id => ({
          finance_import_row_id, transaction_date: '2026-01-09', amount_ntd: 15000, dedup_fingerprint: 'a'.repeat(64),
        })),
        obligations: [
          { obligation_identity: 'receipt:first', payment_stage: 'first', amount_due_ntd: 20000, due_date: '2026-01-08' },
          { obligation_identity: 'receipt:second', payment_stage: 'second', amount_due_ntd: 12000, due_date: '2026-02-08' },
        ],
      }),
      vi.spyOn(ordersQueryClient, 'getOrderDetail').mockRejectedValue(new Error('not needed')),
      vi.spyOn(clientRegistryClient, 'query').mockRejectedValue(new Error('not needed')),
      vi.spyOn(caseVirtualAccountClient, 'query').mockRejectedValue(new Error('not needed')),
      vi.spyOn(paymentOverdueReminderClient, 'case').mockRejectedValue(new Error('not needed')),
    ];
    try {
      render(<FinancePage />);
      fireEvent.change(await screen.findByLabelText('篩選銀行'), { target: { value: 'sinopac' } });
      fireEvent.click(await screen.findByRole('button', { name: '核對交易 Sheet1#2' }));

      const drawer = await screen.findByRole('dialog', { name: '核對交易' });
      expect(await within(drawer).findByRole('heading', { name: '客戶繳款 · 核對交易' })).toBeVisible();
      expect(await within(drawer).findByRole('checkbox', { name: '納入銀行款 101' })).toBeChecked();
      expect(within(drawer).getByRole('checkbox', { name: '納入銀行款 101' })).toBeEnabled();
      expect(within(drawer).getByRole('checkbox', { name: '納入銀行款 103' })).not.toBeChecked();
      if (manual) expect(within(drawer).getByRole('checkbox', { name: /第一期/ })).not.toBeChecked();
      else expect(within(drawer).getByRole('checkbox', { name: /第一期/ })).toBeChecked();
      expect(within(drawer).getByRole('checkbox', { name: /第二期/ })).not.toBeChecked();
      if (manual) {
        fireEvent.click(within(drawer).getByRole('checkbox', { name: /第二期/ }));
        expect(within(drawer).getByRole('checkbox', { name: /第二期/ })).toBeChecked();
        expect(within(drawer).getByRole('checkbox', { name: /第一期/ })).not.toBeChecked();
      }

      fireEvent.keyDown(window, { key: 'Escape' });
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(screen.getByLabelText('篩選銀行')).toHaveValue('sinopac');
    } finally {
      mocks.forEach(mock => mock.mockRestore());
      window.location.hash = '';
    }
  });

  it.each([['staff',1],['staff',2],['refund',1],['refund',2]] as const)('opens same-case %s candidates without preselection and freezes %s selected items during preview', async (kind,count) => {
    window.location.hash = '#finance?tab=bank';
    const ids = [`${kind}:first`, `${kind}:second`];
    const row: FinanceBankTransaction = { ...sinopac, bank: 'taishin', direction: 'outgoing',
      classification_type: kind === 'staff' ? 'staff_payout' : 'client_subsidy_return',
      staff_subsidy_manual_review_allowed: kind === 'staff',
      reconciliation_target: { case_no: '115000001', staff_id: kind === 'staff' ? 7 : null,
        obligation_identities: ids, requires_selection: true } };
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({ items: [row], pending_count: 1, next_before_row_id: null });
    const items = ids.map((identity, index) => ({ identity, direction: 'payable' as const, label: `合成款項${index + 1}`,
      party: '合成對象', expected_ntd: 15000, actual_ntd: 0, remaining_ntd: 15000, has_payment: false,
      version: '1', due_date: '2026-01-15' }));
    const pendingPreview = new Promise<never>(()=>{});
    const staffPreview = vi.spyOn(staffPayoutRemediationClient, 'preview').mockReturnValue(pendingPreview);
    const refundPreview = vi.spyOn(financeImportCorrectionClient, 'preview').mockReturnValue(pendingPreview);
    const mocks = [staffPreview, refundPreview,
      vi.spyOn(staffPayoutRemediationClient, 'query').mockResolvedValue({ staff_id: 7, staff_payables_version: 1, events: [],
        obligations: ids.map(obligation_identity => ({ obligation_identity, case_no: '115000001', amount_due_ntd: 15000,
          due_date: '2026-01-15', net_paid_ntd: 0, balance_ntd: 15000, payout_status: 'payable' })) }),
      vi.spyOn(financeAccountingClient, 'query').mockResolvedValue({ case_no: '115000001', client_name: '合成客戶',
        receivable_ntd: 0, received_ntd: 0, payable_ntd: 30000, paid_ntd: 0, pending_warning_count: 0,
        warnings: [], transactions: [], staff_items: kind === 'staff' ? items : [], client_items: kind === 'refund' ? items : [] }),
      vi.spyOn(ordersQueryClient, 'getOrderDetail').mockRejectedValue(new Error('not needed')),
      vi.spyOn(clientRegistryClient, 'query').mockRejectedValue(new Error('not needed')),
      vi.spyOn(caseVirtualAccountClient, 'query').mockRejectedValue(new Error('not needed')),
      vi.spyOn(paymentOverdueReminderClient, 'case').mockRejectedValue(new Error('not needed')),
    ];
    try {
      render(<FinancePage />);
      fireEvent.click(await screen.findByRole('button', { name: '核對交易 Sheet1#2' }));
      const drawer = await screen.findByRole('dialog', { name: '核對交易' });
      if (kind === 'staff') fireEvent.click(await within(drawer).findByRole('button', { name: '單筆人工核對' }));
      const first = await within(drawer).findByRole('checkbox', { name: `核銷款項 ${ids[0]}` });
      expect(first).not.toBeChecked();
      expect(within(drawer).getByRole('checkbox', { name: `核銷款項 ${ids[1]}` })).not.toBeChecked();
      expect(within(drawer).queryByRole('button', { name: '預覽核銷' })).not.toBeInTheDocument();
      fireEvent.click(within(drawer).getByRole('checkbox', { name: `核銷款項 ${ids[1]}` }));
      const currentFirst=within(drawer).getByRole('checkbox',{name:`核銷款項 ${ids[0]}`});
      expect(currentFirst).not.toBeChecked();
      if(count===2)fireEvent.click(currentFirst);
      const previewButton = await within(drawer).findByRole('button', { name: '預覽核銷' });
      await waitFor(() => expect(previewButton).toBeEnabled());
      fireEvent.click(previewButton);
      await waitFor(() => {
        const selected=count===2?ids:[ids[1]];
        if(kind==='staff'){
          expect(staffPreview).toHaveBeenCalledWith({financeImportRowIds:[101],obligationIdentities:expect.arrayContaining(selected)},expect.anything());
          expect(staffPreview.mock.calls[0][0].obligationIdentities).toHaveLength(count);
        }else{
          expect(refundPreview).toHaveBeenCalledWith(expect.objectContaining({row_identity:row.row_identity,target_obligation_identities:expect.arrayContaining(selected)}));
          expect(refundPreview.mock.calls[0][0].target_obligation_identities).toHaveLength(count);
        }
      });
      for(const id of ids)for(const checkbox of within(drawer).getAllByRole('checkbox',{name:`核銷款項 ${id}`}))expect(checkbox).toBeDisabled();
    } finally {
      mocks.forEach(mock => mock.mockRestore());
      window.location.hash = '';
    }
  });

  it.each([false, true])('reconciles a bank return against the selected original refund (timeout replay: %s)', async timeout => {
    window.location.hash = '#finance?tab=bank';
    const row: FinanceBankTransaction = { ...sinopac, classification_type: 'client_refund_return',
      reconciliation_target: { case_no: '115000001', staff_id: null, obligation_identities: [], requires_selection: true } };
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({ items: [row], pending_count: 1, next_before_row_id: null });
    const original = [51, 52].map(id => ({ id, amount_ntd: 15000, occurred_on: '2026-01-01', reversed_ntd: 0 }));
    let applied = false;
    let attempts = 0;
    const envelope = (data: unknown) => ({ success: true, message: '', data, error: null });
    const get = vi.spyOn(transport, 'get').mockImplementation(async path => {
      expect(path).toBe('/api/v1/orders/115000001/client-finance/refund-reversal');
      return envelope({ case_no: '115000001', account_version: applied ? 4 : 3,
        refund_obligations: [], subsidy_return_obligations: [], refund_bank_facts: [], subsidy_return_bank_facts: [],
        reversal_targets: [], refund_return_targets: applied ? [original[0]] : original }) as never;
    });
    const post = vi.spyOn(transport, 'post').mockImplementation(async (path, _body, _options) => {
      if (path.endsWith('/preview')) return envelope({ account_version: 3, preview_fingerprint: 'b'.repeat(64),
        candidate: { correction_type: 'refund_return', case_no: '115000001', amount: { amount: 15000 },
          entries: [{ identity: 'refund-return:101', entry_type: 'refund_reversal', amount: { amount: 15000 },
            occurred_on: '2026-01-09', reversal_of_entry_identity: '52', finance_import_row_identity: '101' }],
          allocations: [{ entry_identity: 'refund-return:101', obligation_identity: 'refund:second', amount: { amount: 15000 } }],
          affected_obligations: ['refund:second'], reversal_entry_type: 'refund', recovery_amount: { amount: 0 },
          fingerprint: 'c'.repeat(64), transfer_fee: { amount: 0 } } }) as never;
      attempts += 1;
      if (timeout && attempts === 1) throw new ApiTimeoutError(30_000);
      applied = true;
      return envelope({ case_no: '115000001', correction_type: 'refund_return', account_version: 4,
        correction_identity: 'd'.repeat(64), ledger_entry_count: 1, allocation_count: 1, affected_obligations: ['refund:second'] }) as never;
    });
    const mocks = [get, post, vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-session'),
      vi.spyOn(financeAccountingClient, 'query').mockResolvedValue({ case_no: '115000001', client_name: '合成客戶',
        receivable_ntd: 0, received_ntd: 0, payable_ntd: 30000, paid_ntd: 30000, pending_warning_count: 0,
        warnings: [], transactions: [], staff_items: [], client_items: [] }),
      vi.spyOn(ordersQueryClient, 'getOrderDetail').mockRejectedValue(new Error('not needed')),
      vi.spyOn(clientRegistryClient, 'query').mockRejectedValue(new Error('not needed')),
      vi.spyOn(caseVirtualAccountClient, 'query').mockRejectedValue(new Error('not needed')),
      vi.spyOn(paymentOverdueReminderClient, 'case').mockRejectedValue(new Error('not needed')),
    ];
    try {
      render(<FinancePage />);
      fireEvent.click(await screen.findByRole('button', { name: '核對交易 Sheet1#2' }));
      const drawer = await screen.findByRole('dialog', { name: '核對交易' });
      const select = await within(drawer).findByRole('combobox', { name: '原退款' });
      expect(select).toHaveValue('');
      expect(within(drawer).getByRole('button', { name: '預覽退匯核銷' })).toBeDisabled();
      fireEvent.change(select, { target: { value: '52' } });
      fireEvent.click(within(drawer).getByRole('button', { name: '預覽退匯核銷' }));
      fireEvent.click(await within(drawer).findByRole('button', { name: '確認退匯核銷' }));
      if (timeout) {
        const retry = await within(drawer).findByRole('button', { name: '查回原次核銷結果' });
        expect(select).toBeDisabled();
        expect(within(drawer).getByRole('button', { name: '重新查詢原退款' })).toBeDisabled();
        fireEvent.click(retry);
      }
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
      const commands = post.mock.calls.filter(([path]) => path.endsWith('/apply'));
      expect(commands).toHaveLength(timeout ? 2 : 1);
      expect(commands[0][1]).toEqual(expect.objectContaining({ finance_import_row_id: 101, refund_ledger_entry_id: 52,
        expected_account_version: 3, preview_fingerprint: 'b'.repeat(64) }));
      if (timeout) expect(commands[1]).toEqual(commands[0]);
      expect(await get.mock.results.at(-1)!.value).toEqual(expect.objectContaining({
        data:expect.objectContaining({account_version:4,refund_return_targets:[original[0]]}),
      }));
    } finally { mocks.forEach(mock => mock.mockRestore()); window.location.hash = ''; }
  });

  it('shows candidate date estimates and submits only the selected pairing identity', async () => {
    const candidate = { case_no: '115000002', purpose: 'staff_salary' as const, person_id: 12 };
    const bankRow = {
      ...taishin, direction: 'outgoing' as const, classification_type: 'staff_salary', review_reason: 'bank_case_suffix_not_found',
    };
    const source = {
      ...bankRow,
      pairing_candidates: [
        { ...candidate, estimated_subsidy_payment_date: '2026-10-15', estimated_self_funded_staff_due_date: '2026-09-15' },
        { ...candidate, case_no: 'A15000003', estimated_subsidy_payment_date: null, estimated_self_funded_staff_due_date: '2026-08-15' },
        { ...candidate, case_no: '115000004', estimated_subsidy_payment_date: null, estimated_self_funded_staff_due_date: null },
      ],
    };
    const fresh = {
      ...bankRow, cases: [candidate.case_no],
      reconciliation_target: { case_no: candidate.case_no, staff_id: candidate.person_id, obligation_identities: ['staff:1'], requires_selection: true },
    };
    const real = await vi.importActual<typeof import('../../../../../../../api/finance_import/finance_import_query_client')>(
      '../../../../../../../api/finance_import/finance_import_query_client',
    );
    vi.mocked(financeImportQueryClient.listBankTransactions).mockImplementation(real.financeImportQueryClient.listBankTransactions);
    vi.mocked(financeImportQueryClient.pairBankTransaction).mockImplementation(real.financeImportQueryClient.pairBankTransaction);
    const token = vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-test-session');
    const get = vi.spyOn(transport, 'get').mockImplementation(async (_path, options) => ({
      success: true,
      message: '',
      data: { items: [options?.params?.row_id && post.mock.calls.length ? fresh : source], pending_count: 1, next_before_row_id: null },
    }));
    const post = vi.spyOn(transport, 'post').mockResolvedValue({ success: true, message: '', data: { row_id: source.row_id } });
    window.location.hash = '#finance?tab=bank';
    try {
      render(<FinancePage />);
      fireEvent.click(await screen.findByRole('button', { name: `核對交易 ${source.reference}` }));
      const selected = await screen.findByRole('radio', { name: /115000002.*預估補助入帳 2026-10-15.*預估薪資入帳 2026-09-15/ });
      expect(screen.getByRole('radio', { name: /A15000003.*預估補助入帳 —.*預估薪資入帳 2026-08-15/ })).toBeVisible();
      expect(screen.getByRole('radio', { name: /115000004.*預估補助入帳 —.*預估薪資入帳 —/ })).toBeVisible();
      expect(screen.getByRole('button', { name: '確認配對' })).toBeDisabled();
      fireEvent.click(selected);
      fireEvent.click(screen.getByRole('button', { name: '確認配對' }));
      await screen.findByRole('button', { name: '查看本案帳務' });
      expect(financeImportQueryClient.listBankTransactions).toHaveBeenCalledWith(expect.objectContaining({ row_id: source.row_id }), expect.anything());
      expect(post).toHaveBeenCalledWith(`/api/v1/finance-import/bank-transactions/${source.row_id}/pair`, candidate, expect.anything());
    } finally {
      get.mockRestore();
      post.mockRestore();
      token.mockRestore();
      window.location.hash = '';
    }
  });

  it('changes a pending Sinopac payout to a refund and opens the refreshed refund target', async () => {
    const candidate = { case_no: '115000002', purpose: 'client_refund' as const, person_id: 5 };
    const source = {
      ...sinopac, direction: 'outgoing' as const, classification_type: 'staff_payout',
      pairing_memo: 'HC115002 合成備註',
      purpose_review: { classification_version: 2, candidates: [candidate] },
    };
    const fresh = {
      ...source, classification_type: 'client_refund', purpose_review: null,
      reconciliation_target: { case_no: candidate.case_no, staff_id: null, obligation_identities: ['refund:1'] },
    };
    window.location.hash = '#finance?tab=bank';
    let paired = false;
    vi.mocked(financeImportQueryClient.listBankTransactions).mockImplementation(async () => ({ items: [paired ? fresh : source], pending_count: 1, next_before_row_id: null }));
    vi.mocked(financeImportQueryClient.pairBankTransaction).mockImplementationOnce(async () => { paired = true; return source.row_id; });
    const readCase = vi.spyOn(financeAccountingClient, 'query').mockRejectedValue(new Error('synthetic case'));
    try {
      render(<FinancePage />);
      fireEvent.click(await screen.findByRole('button', { name: `核對交易 ${source.reference}` }));
      const drawer = within(screen.getByRole('dialog', { name: '核對交易' }));
      fireEvent.click(await drawer.findByRole('button', { name: '更正出款用途' }));
      expect(drawer.getByText(source.pairing_memo)).toBeVisible();
      const confirm = drawer.getByRole('button', { name: '確認用途' });
      expect(confirm).toBeDisabled();
      fireEvent.click(drawer.getByRole('radio', { name: /115000002.*退款/ }));
      fireEvent.click(confirm);
      expect(financeImportQueryClient.pairBankTransaction).toHaveBeenCalledWith(source.row_id, candidate, 2);
      await waitFor(() => expect(readCase).toHaveBeenCalledWith(candidate.case_no, expect.anything()));
      expect(await drawer.findByText('客戶退款')).toBeVisible();
    } finally { readCase.mockRestore(); window.location.hash = ''; }
  });

  it('keeps details read-only and requires a reason to exclude from the review drawer', async () => {
    window.location.hash = '#finance?tab=bank';
    let excluded = false;
    vi.mocked(financeImportQueryClient.listBankTransactions).mockImplementation(async () => ({
      items: excluded ? [] : [sinopac], pending_count: excluded ? 0 : 1, next_before_row_id: null,
    }));
    vi.mocked(financeImportQueryClient.excludeBankTransaction).mockImplementationOnce(async () => { excluded = true; return sinopac.row_id; });
    const readCase = vi.spyOn(financeAccountingClient, 'query').mockRejectedValue(new Error('synthetic case'));
    try {
      render(<FinancePage />);
      fireEvent.click(await screen.findByRole('button', { name: `查看交易 ${sinopac.row_identity}` }));
      const detail = within(screen.getByRole('dialog', { name: '待核對交易明細' }));
      expect(detail.queryByRole('button', { name: '移除誤匯入明細' })).not.toBeInTheDocument();
      fireEvent.click(detail.getByRole('button', { name: '核對交易' }));
      const review = within(screen.getByRole('dialog', { name: '核對交易' }));
      fireEvent.click(await review.findByRole('button', { name: '移除誤匯入明細' }));
      expect(review.getByRole('button', { name: '確認移除' })).toBeDisabled();
      fireEvent.change(review.getByLabelText('移除原因'), { target: { value: '與案件無關' } });
      fireEvent.click(review.getByRole('button', { name: '確認移除' }));
      await screen.findByText('目前沒有符合條件的銀行交易資料。');
      expect(financeImportQueryClient.excludeBankTransaction).toHaveBeenCalledWith(sinopac.row_id, '與案件無關');
    } finally { readCase.mockRestore(); window.location.hash = ''; }
  });

  it.each([
    [undefined, ['115000001'], '對應款項待確認'],
    ['case_unconfirmed', [], '尚未確認唯一案件。'],
    ['staff_unconfirmed', ['115000001'], '案件已定位，尚未確認這筆出款的月嫂。'],
  ] as const)('shows the precise missing facts for an unresolved transaction (%s)', async (reason, cases, text) => {
    window.location.hash = '#finance?tab=bank';
    const row: FinanceBankTransaction = { ...sinopac, cases: [...cases], reconciliation_target: null,
      reconciliation_unavailable_reason: reason };
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({ items: [row], pending_count: 1, next_before_row_id: null });
    try {
      render(<FinancePage />);
      fireEvent.click(await screen.findByRole('button', { name: `核對交易 ${row.reference}` }));
      const drawer = within(screen.getByRole('dialog', { name: '核對交易' }));
      expect(await drawer.findByText(text)).toBeVisible();
      expect(drawer.getByRole('region', { name: '銀行原始交易事實' })).toHaveTextContent('15,000');
      expect(drawer.queryByRole('button', { name: /確認核銷|選擇案件/ })).not.toBeInTheDocument();
    } finally { window.location.hash = ''; }
  });

  it('passes the selected bank row and obligation to the shared drawer entry', async () => {
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);

    expect(await screen.findByText('Sheet1#2')).toBeInTheDocument();
    expect(screen.getByText('NT$ 15,000')).toBeInTheDocument();
    expect(screen.getByText('林小美')).toBeInTheDocument();
    expect(screen.getByText('新竹市政府')).toBeInTheDocument();
    expect(screen.getByText('整期核銷（待選期間）')).toBeInTheDocument();
    expect(screen.queryByText('待指派案件')).not.toBeInTheDocument();

    // Clicking pending row case button invokes onCase
    fireEvent.click(screen.getByRole('button', { name: '115000001' }));
    expect(onCase).toHaveBeenCalledWith('115000001');

    // Click 核對交易 to open drawer
    const reviewBtn = screen.getByRole('button', { name: '核對交易 Sheet1#2' });
    fireEvent.click(reviewBtn);

    expect(onReconcile).toHaveBeenCalledWith(sinopac);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it.each([
    ['non_business_review', 'taishin_memo_case_requires_manual_scheme'],
    ['staff_payout', 'outgoing_staff_payout_no_open_obligation'],
  ])('keeps the linked case reachable from review without formal payable items (%s)', async (classification_type, review_reason) => {
    window.location.hash = '#finance?tab=bank';
    const row: FinanceBankTransaction = { ...taishin, direction: 'outgoing', classification_type, review_reason,
      cases: ['115000001'], reconciliation_target: null, reconciliation_unavailable_reason: 'purpose_unconfirmed' };
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({ items: [row], pending_count: 1, next_before_row_id: null });
    const scope = vi.spyOn(financeAccountingClient, 'query').mockRejectedValue(new Error('synthetic case'));
    try {
      render(<FinancePage />);
      fireEvent.click(await screen.findByRole('button', { name: `核對交易 ${row.reference}` }));
      const drawer = within(screen.getByRole('dialog', { name: '核對交易' }));
      fireEvent.click(await drawer.findByRole('button', { name: '查看本案帳務' }));
      await waitFor(() => expect(scope).toHaveBeenCalledWith('115000001', expect.anything()));
      fireEvent.click(drawer.getByRole('button', { name: '返回核對交易' }));
      expect(await drawer.findByRole('button', { name: '查看本案帳務' })).toBeVisible();
      expect(drawer.queryByRole('button', { name: '單筆人工核對' })).not.toBeInTheDocument();
    } finally { scope.mockRestore(); window.location.hash = ''; }
  });

  it('shows both banks across all uploads and opens import history independently', async () => {
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);
    expect(await screen.findByRole('button', { name: '核對交易 Sheet1#2' })).toBeVisible();
    expect(screen.getByRole('button', { name: '核對交易 交易明細#3' })).toBeVisible();
    fireEvent.change(screen.getByLabelText('篩選銀行'), { target: { value: 'sinopac' } });
    expect(await screen.findByRole('button', { name: '核對交易 Sheet1#2' })).toBeVisible();
    expect(screen.queryByRole('button', { name: '核對交易 交易明細#3' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '匯入紀錄' }));
    const dialog = await screen.findByRole('dialog', { name: '匯入紀錄' });
    expect(await within(dialog).findByText('statement.xlsx', { exact: false })).toBeInTheDocument();
    expect(within(dialog).getByText('交易指紋已存在，重複列已略過')).toBeVisible();
    expect(screen.getAllByRole('button', { name: '查看交易 finance-import-row:101' })).toHaveLength(1);
    expect(within(dialog).getByText('本次核銷')).toBeInTheDocument();
    expect(screen.getByLabelText('篩選銀行')).toHaveValue('sinopac');
  });

  it('opens excluded bank transactions drawer and displays removal reason and audit details', async () => {
    vi.mocked(financeImportQueryClient.listExcludedBankTransactions).mockResolvedValue({
      items: [
        {
          row_id: 88,
          row_identity: 'bank:88',
          batch_id: 12,
          bank: 'sinopac',
          transaction_date: '2026-11-10',
          direction: 'incoming',
          amount_ntd: 25000,
          summary: '非本會款項',
          memo: '退回款',
          counterparty_name: '張大明',
          source_file: 'sinopac_nov.xlsx',
          sheet_name: 'Sheet1',
          source_row: 10,
          raw_reference: 'TX8888',
          excluded_at: '2026-11-11T10:00:00.000Z',
          excluded_by: 'admin',
          exclusion_reason: '廠商誤匯入非本工會帳款',
        },
      ],
      next_before_row_id: null,
    });

    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);
    const excludedBtn = screen.getByRole('button', { name: '已移除流水紀錄' });
    expect(excludedBtn).toBeVisible();

    fireEvent.click(excludedBtn);
    const dialog = await screen.findByRole('dialog', { name: '已移除流水紀錄' });
    expect(dialog).toBeVisible();
    expect(within(dialog).getByText('廠商誤匯入非本工會帳款')).toBeVisible();
    expect(within(dialog).getByText('admin')).toBeVisible();
    expect(within(dialog).getByText('NT$ 25,000')).toBeVisible();
    expect(within(dialog).getByText('永豐')).toBeVisible();
    expect(within(dialog).getByText('sinopac_nov.xlsx', { exact: false })).toBeInTheDocument();
  });

  it('displays posted bank facts and opens readonly fact drawer', async () => {
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);

    // Switch status filter to 'posted'
    fireEvent.change(screen.getByLabelText('篩選處理狀態'), { target: { value: 'posted' } });

    expect(await screen.findByText('DEMO-POSTED-01')).toBeInTheDocument();
    expect(screen.getByText('NT$ 6,000')).toBeInTheDocument();

    // Clicking case link opens case drawer
    const caseBtn = screen.getByRole('button', { name: 'DEMO-08' });
    fireEvent.click(caseBtn);
    expect(onCase).toHaveBeenCalledWith('DEMO-08');

    // Clicking 查看明細 opens readonly drawer
    const viewBtn = screen.getByRole('button', { name: '查看交易 finance-import-row:100' });
    fireEvent.click(viewBtn);

    const detail = within(await screen.findByRole('dialog', { name: '已核銷交易明細' }));
    expect(detail.getByText(/已核銷 · 唯讀查閱/)).toBeInTheDocument();
    expect(detail.getByText('合成原始備註 ****')).toBeVisible();
    expect(await detail.findByText(/客戶款項核銷 · NT\$ 6,000/)).toBeVisible();
    expect(detail.queryByRole('button', { name: /核對交易|更正出款用途|移除誤匯入明細/ })).not.toBeInTheDocument();
  });

  it('returns from case accounting to the original read-only bank detail and keeps the list search', async () => {
    window.location.hash = '#finance?tab=bank';
    const readCase = vi.spyOn(financeAccountingClient, 'query').mockRejectedValue(new Error('synthetic case'));
    try {
      render(<FinancePage />);
      fireEvent.change(screen.getByLabelText('篩選處理狀態'), { target: { value: 'posted' } });
      fireEvent.change(screen.getByLabelText('搜尋交易'), { target: { value: 'DEMO' } });
      fireEvent.click(await screen.findByRole('button', { name: `查看交易 ${posted.row_identity}` }));
      const detail = within(screen.getByRole('dialog', { name: '已核銷交易明細' }));
      await detail.findByText(/客戶款項核銷/);
      fireEvent.click(detail.getByRole('button', { name: '開啟案件 DEMO-08' }));
      const caseDrawer = within(screen.getByRole('dialog', { name: '案件帳務 · DEMO-08' }));
      await waitFor(() => expect(readCase).toHaveBeenCalledWith('DEMO-08', expect.anything()));
      const reads = vi.mocked(financeImportQueryClient.listBankTransactions).mock.calls.filter(([query]) => query.row_id === posted.row_id).length;
      fireEvent.click(caseDrawer.getAllByRole('button', { name: '返回交易明細' })[0]);
      const returned = within(await screen.findByRole('dialog', { name: '已核銷交易明細' }));
      expect(await returned.findByText(/客戶款項核銷/)).toBeVisible();
      expect(vi.mocked(financeImportQueryClient.listBankTransactions).mock.calls.filter(([query]) => query.row_id === posted.row_id)).toHaveLength(reads + 1);
      expect(screen.getByLabelText('搜尋交易')).toHaveValue('DEMO');
      expect(screen.getByLabelText('篩選處理狀態')).toHaveValue('posted');
    } finally { readCase.mockRestore(); window.location.hash = ''; }
  });

  it('allows single-step import without a reason field', () => {
    render(<FinanceBankReconciliationWorkspace {...defaultProps} financeWorkbook={new File(['test'], 'test.xlsx')} />);
    expect(screen.queryByRole('textbox', { name: /原因/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /匯入銀行交易明細/ })).toBeEnabled();
  });

  const exchangePath = process.env.FI_REVIEW_EXCHANGE;
  (exchangePath ? it : it.skip)('renders same-run source-review MySQL evidence through the typed bank query', async () => {
    const evidence = JSON.parse(readFileSync(exchangePath!, 'utf8'));
    const real = await vi.importActual<typeof import('../../../../../../../api/finance_import/finance_import_query_client')>(
      '../../../../../../../api/finance_import/finance_import_query_client',
    );
    vi.mocked(financeImportQueryClient.listBankTransactions).mockImplementation(real.financeImportQueryClient.listBankTransactions);
    const token = vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-test-session');
    const get = vi.spyOn(transport, 'get').mockResolvedValue(evidence.bank_page);
    try {
      render(<FinanceBankReconciliationWorkspace {...defaultProps} />);
      expect(await screen.findByLabelText('銀行對帳統計摘要')).toHaveTextContent('待核對 1 筆');
      const row = evidence.bank_page.data.items[0];
      expect(screen.getByRole('button', { name: `核對交易 ${row.reference}` })).toBeVisible();
      expect(screen.queryByText(evidence.source_audit.issue_codes[0])).not.toBeInTheDocument();
      expect(get).toHaveBeenCalledWith('/api/v1/finance-import/bank-transactions', expect.anything());
    } finally {
      get.mockRestore();
      token.mockRestore();
    }
  });

  it('keeps undated established staff obligation selectable from bank reconciliation entry', async () => {
    const undatedRow: FinanceBankTransaction = {
      ...sinopac,
      row_id: 205,
      row_identity: 'finance-import-row:205',
      direction: 'outgoing',
      amount_ntd: 47985,
      classification_type: 'staff_salary',
      review_reason: 'due_date_missing',
      counterparty_name: '合成月嫂甲',
      cases: ['115000888'],
      reconciliation_unavailable_reason: 'due_date_missing',
      reconciliation_target: {
        case_no: '115000888',
        staff_id: 7,
        obligation_identities: ['staff-obligation:assignment:1'],
        requires_selection: true,
      },
    };
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [undatedRow],
      pending_count: 1,
      next_before_row_id: null,
    });
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);
    const btn = await screen.findByRole('button', { name: `核對交易 ${undatedRow.reference}` });
    expect(btn).toBeEnabled();
    fireEvent.click(btn);
    expect(onReconcile).toHaveBeenCalledWith(undatedRow);
  });
});
