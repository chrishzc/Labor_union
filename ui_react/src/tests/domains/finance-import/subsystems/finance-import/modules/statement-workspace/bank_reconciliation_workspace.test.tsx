/**
 * File: bank_reconciliation_workspace.test.tsx
 * Description: 銀行對帳工作台（WF-03/04）單元驗收測試，驗證雙行排版、KPI膠囊、篩選與核對抽屜。
 */

import { readFileSync } from 'node:fs';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FinanceBankReconciliationWorkspace } from '../../../../../../../components/FinanceBankReconciliationWorkspace';
import { financeImportQueryClient } from '../../../../../../../api/finance_import/finance_import_query_client';
import type { FinanceBankTransaction } from '../../../../../../../api/finance_import/finance_import_query_schemas';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { subsidyPeriodClient } from '../../../../../../../api/government_subsidy/period_reconciliation_client';
import { FinancePage } from '../../../../../../../pages/FinancePage';
import { financeAccountingClient } from '../../../../../../../api/finance_import/finance_accounting_client';
import { clientReceiptQueryClient } from '../../../../../../../api/client_finance/client_receipt_query_client';
import { caseVirtualAccountClient } from '../../../../../../../api/client_finance/case_virtual_account_client';
import { clientRegistryClient } from '../../../../../../../api/client_registry/client_registry_client';
import { ordersQueryClient } from '../../../../../../../api/orders/order_query_client';
import { paymentOverdueReminderClient } from '../../../../../../../api/line_order_groups/payment_overdue_reminder_client';
import { transport } from '../../../../../../../api/shared/transport';

vi.mock('../../../../../../../api/finance_import/finance_import_query_client', () => ({
  financeImportQueryClient: { listBankTransactions: vi.fn(), listImportHistory: vi.fn() },
}));
vi.mock('../../../../../../../components/FinanceStatementArchive', () => ({
  FinanceStatementArchive: ({ compact: _compact, showManual = false }: { compact?: boolean; showManual?: boolean }) => (
    <div data-testid="statement-archive">
      <button type="button">匯出 Excel</button>
      {showManual && <button type="button">新增人工明細</button>}
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
    reference: 'DEMO-POSTED-01', cases: ['DEMO-08'],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(financeImportQueryClient.listBankTransactions).mockImplementation(async query => ({
      items: query.transaction_status === 'posted' ? [posted] : [taishin, sinopac].filter(row => !query.bank || row.bank === query.bank),
      pending_count: query.transaction_status === 'posted' ? null : query.bank ? 1 : 2,
      next_before_row_id: null,
    }));
    vi.mocked(financeImportQueryClient.listImportHistory).mockResolvedValue({
      items: [{ identity: 'attempt:2', started_at: '2026-01-10T00:00:00Z', bank: 'sinopac', source_file: 'statement.xlsx',
        status: 'saved', new_count: 0, duplicate_count: 3, reconciled_count: 0, pending_count: 2,
        source_warning_count: 0, error_code: null }],
      next_before: null,
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

  it('renders the WF-03 banner, KPI summary pills, and integrated filters', async () => {
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);

    expect(screen.getByText('兩家銀行，一處核對')).toBeInTheDocument();
    expect(screen.getByText('先辨識來源，再確認款項交給誰。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '匯入永豐對帳單' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '匯入台新對帳單' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '匯出 Excel' })).toBeInTheDocument();
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

  it('marks a known difference separately from government period selection', async () => {
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [{ ...sinopac, review_reason: 'sinopac_client_receipt_shortfall' }, taishin],
      pending_count: 2,
      next_before_row_id: null,
    });

    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);

    expect(within(await screen.findByRole('row', { name: /Sheet1#2/ })).getByText('差額待核對')).toBeVisible();
    expect(within(screen.getByRole('row', { name: /交易明細#3/ })).getByText('待核對')).toBeVisible();
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
      const dialog = screen.getByRole('dialog', { name: '政府整期核對' });
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

  it('opens the shared case drawer with the clicked bank source and matched obligation already selected', async () => {
    window.location.hash = '#finance?tab=bank';
    const mocks = [
      vi.spyOn(financeAccountingClient, 'query').mockResolvedValue({
        case_no: '115000001', client_name: '測試客戶', receivable_ntd: 20000, received_ntd: 0,
        payable_ntd: 0, paid_ntd: 0, remaining_in_ntd: 20000, remaining_out_ntd: 0,
        pending_warning_count: 0, warnings: [], transactions: [], staff_items: [],
        client_items: [{
          identity: 'receipt:first', direction: 'receivable', label: '第一期', party: '測試客戶',
          expected_ntd: 20000, actual_ntd: 0, remaining_ntd: 20000, has_payment: false, version: '1', due_date: '2026-01-08',
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

      const drawer = await screen.findByRole('dialog', { name: '案件帳務 · 115000001' });
      expect(await within(drawer).findByRole('heading', { name: '客戶繳款 · 核對交易' })).toBeVisible();
      expect(await within(drawer).findByRole('checkbox', { name: '納入銀行款 101' })).toBeChecked();
      expect(within(drawer).getByRole('checkbox', { name: '納入銀行款 101' })).toBeDisabled();
      expect(within(drawer).getByRole('checkbox', { name: '納入銀行款 103' })).not.toBeChecked();
      expect(within(drawer).getByRole('checkbox', { name: /receipt:first/ })).toBeChecked();
      expect(within(drawer).getByRole('checkbox', { name: /receipt:second/ })).not.toBeChecked();

      fireEvent.keyDown(window, { key: 'Escape' });
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(screen.getByLabelText('篩選銀行')).toHaveValue('sinopac');
    } finally {
      mocks.forEach(mock => mock.mockRestore());
      window.location.hash = '';
    }
  });

  it('keeps an unresolved row visible without opening an arbitrary case', async () => {
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [{ ...sinopac, reconciliation_target: null }], pending_count: 1, next_before_row_id: null,
    });
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);
    expect(await screen.findByText('對應款項待確認')).toBeVisible();
    expect(screen.queryByRole('button', { name: '核對交易 Sheet1#2' })).not.toBeInTheDocument();
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
    expect(within(dialog).getByText('本次核銷')).toBeInTheDocument();
    expect(screen.getByLabelText('篩選銀行')).toHaveValue('sinopac');
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

    expect(await screen.findByText('已核銷交易明細')).toBeInTheDocument();
    expect(screen.getByText(/已核銷 · 唯讀查閱/)).toBeInTheDocument();
  });

  it('does not render formal reconciliation reason input in import panel', () => {
    render(<FinanceBankReconciliationWorkspace {...defaultProps} financeWorkbook={new File(['test'], 'test.xlsx')} />);

    expect(screen.queryByText(/正式銷帳原因/)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText('輸入銷帳說明')).not.toBeInTheDocument();
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
      if (row.reconciliation_target || row.classification_type === 'government_subsidy') {
        expect(screen.getByRole('button', { name: `核對交易 ${row.reference}` })).toBeVisible();
      } else {
        expect(screen.getByText('對應款項待確認')).toBeVisible();
      }
      expect(screen.queryByText(evidence.source_audit.issue_codes[0])).not.toBeInTheDocument();
      expect(get).toHaveBeenCalledWith('/api/v1/finance-import/bank-transactions', expect.anything());
    } finally {
      get.mockRestore();
      token.mockRestore();
    }
  });
});
