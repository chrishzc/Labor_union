/**
 * File: bank_reconciliation_workspace.test.tsx
 * Description: 銀行對帳工作台（WF-03/04）單元驗收測試，驗證雙行排版、KPI膠囊、篩選與核對抽屜。
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FinanceBankReconciliationWorkspace } from '../../../../../../../components/FinanceBankReconciliationWorkspace';
import { monthlyAccountingClient } from '../../../../../../../api/finance_import/monthly_accounting_client';

vi.mock('../../../../../../../api/finance_import/monthly_accounting_client', () => ({
  monthlyAccountingClient: { query: vi.fn() },
}));
vi.mock('../../../../../../../components/FinanceStatementArchive', () => ({
  FinanceStatementArchive: ({ compact: _compact }: { compact?: boolean }) => (
    <div data-testid="statement-archive">
      <button type="button">匯出 Excel</button>
      <button type="button">新增人工明細</button>
    </div>
  ),
}));
vi.mock('../../../../../../../components/FinanceImportCorrectionForm', () => ({
  FinanceImportCorrectionForm: ({ onPosted }: { onPosted?: () => void }) => (
    <div data-testid="correction-form">
      <span>核銷校正表單</span>
      <button type="button" onClick={onPosted}>完成核銷</button>
    </div>
  ),
}));

describe('FinanceBankReconciliationWorkspace (WF-03 / WF-04)', () => {
  const onCase = vi.fn();
  const onPostedManual = vi.fn();
  const onSelectBatch = vi.fn();
  const onReloadSourceReview = vi.fn();
  const onWorkbookChange = vi.fn();
  const onApplyReasonChange = vi.fn();
  const onIngest = vi.fn();
  const onApply = vi.fn();
  const onObserveApplyOutcome = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(monthlyAccountingClient.query).mockResolvedValue({
      start_month: '2026-11',
      end_month: '2026-11',
      category: 'all',
      as_of: '2026-11-05T00:00:00Z',
      excluded_cases: [],
      undated_item_count: 0,
      rows: [
        {
          month: '2026-11',
          expected_in_ntd: 6000,
          received_ntd: 6000,
          remaining_in_ntd: 0,
          expected_out_ntd: 0,
          paid_ntd: 0,
          remaining_out_ntd: 0,
          cash_in_ntd: 6000,
          cash_out_ntd: 0,
          other_in_ntd: 0,
          other_out_ntd: 0,
          cash_by_flow: { C: 6000, G: 0, PS: 0, PT: 0, RS: 0, RT: 0 },
          items: [],
          bank_facts: [
            {
              occurred_on: '2026-11-03',
              identity: 'DEMO-POSTED-01',
              bank: 'sinopac',
              direction: 'in',
              amount_ntd: 6000,
              cash_flow: 'C',
              cases: ['DEMO-08'],
            },
          ],
        },
      ],
    });
  });

  const defaultProps = {
    onCase,
    revision: 0,
    staff: [{ id: 1, label: '測試月嫂' }],
    batches: [
      {
        batch_id: 2,
        batch_identity: 'batch:2',
        format_id: 'taishin',
        source_file: 'taishin.xlsx',
        row_count: 1,
        status: 'ready',
        batch_version: 1,
        architecture_ready: true,
        created_at: '2026-11-05T00:00:00Z',
      },
    ],
    selectedBatchIdentity: 'batch:2',
    onSelectBatch,
    sourceReview: {
      kind: 'ready' as const,
      data: {
        batchIdentity: 'batch:2',
        reviewCount: 1,
        sourceReviews: [],
        items: [
          {
            row_id: 101,
            row_identity: 'row:101',
            transaction_date: '2026-11-05',
            direction: 'incoming',
            amount_ntd: 15000,
            classification_type: 'client_receipt',
            bank_type: 'receivable' as const,
            disposition: 'review_required',
            reconciliation_status: 'pending',
            source_sheet: 'Sheet1',
            source_row: 2,
            occurrence_count: 1,
            available_actions: ['preview_manual_correction'],
            created_at: '2026-11-05T00:00:00Z',
          },
        ],
      },
    },
    onReloadSourceReview,
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
    onPostedManual,
    postingStopped: false,
    manuallyPostedRows: new Set<string>(),
    confirmedImportReceipt: null,
  };

  it('renders the WF-03 banner, KPI summary pills, and integrated filters', async () => {
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);

    expect(screen.getByText('兩家銀行，一處核對')).toBeInTheDocument();
    expect(screen.getByText('先辨識來源，再確認款項交給誰。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '匯入永豐對帳單' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '匯入台新對帳單' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '匯出 Excel' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '新增人工明細' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '匯入紀錄' })).not.toBeInTheDocument();

    // KPI pills
    expect(screen.queryByText(/對象／案件待確認/)).not.toBeInTheDocument();
    expect(screen.getAllByText('待核對').length).toBeGreaterThan(0);
    expect(screen.getAllByText('已核銷').length).toBeGreaterThan(0);

    // Filters
    expect(screen.getByLabelText('篩選銀行')).toBeInTheDocument();
    expect(screen.getByLabelText('篩選方向')).toBeInTheDocument();
    expect(screen.getByLabelText('篩選處理狀態')).toBeInTheDocument();
    expect(screen.getByLabelText('交易起日')).toBeInTheDocument();
    expect(screen.getByLabelText('交易迄日')).toBeInTheDocument();
    expect(screen.getByLabelText('搜尋交易')).toBeInTheDocument();
  });

  it('displays pending transaction with double-line layout and opens WF-04 drawer on click', async () => {
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);

    expect(screen.getByText('2026-11-05')).toBeInTheDocument();
    expect(screen.getByText('Sheet1#2')).toBeInTheDocument();
    expect(screen.getByText('NT$ 15,000')).toBeInTheDocument();

    // Click 核對交易 to open drawer
    const reviewBtn = screen.getByRole('button', { name: '核對交易 Sheet1#2' });
    fireEvent.click(reviewBtn);

    // Verify WF-04 Drawer opens
    expect(screen.getByText('WF-04 · 逐筆核對抽屜')).toBeInTheDocument();
    expect(screen.getByText('銀行原始交易事實')).toBeInTheDocument();
    expect(screen.getByTestId('correction-form')).toBeInTheDocument();

    // Finish review
    fireEvent.click(screen.getByRole('button', { name: '完成核銷' }));
    expect(onPostedManual).toHaveBeenCalledWith('row:101');
  });

  it.each(['sinopac', 'taishin'])('keeps historical %s review visible and counts reimport once', (bank) => {
    const sourceReview = {
      ...defaultProps.sourceReview,
      data: {
        ...defaultProps.sourceReview.data,
        items: defaultProps.sourceReview.data.items.map(row => ({ ...row, transaction_date: '2026-01-09' })),
      },
    };
    render(<FinanceBankReconciliationWorkspace
      {...defaultProps}
      batches={[{ ...defaultProps.batches[0], format_id: bank }]}
      sourceReview={sourceReview}
      financeWorkbook={new File(['test'], 'test.xlsx')}
      ingestion={{ kind: 'ready', data: {
        batch_identity: 'batch:2', source_content_digest: 'a'.repeat(64), source_row_count: 2,
        canonical_created_count: 0, duplicate_occurrence_count: 2,
        source_warning_count: 0, source_warning_created_count: 0, replayed: false,
      } }}
    />);
    expect(screen.getByText(/本次自動核銷 0 筆.*新增流水 0 筆.*重複來源列 2 筆.*仍待核對 1 筆/)).toBeVisible();
    fireEvent.change(screen.getByLabelText('篩選銀行'), { target: { value: bank } });
    expect(screen.getByRole('button', { name: '核對交易 Sheet1#2' })).toBeVisible();
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
    const viewBtn = screen.getByRole('button', { name: '查看交易 DEMO-POSTED-01' });
    fireEvent.click(viewBtn);

    expect(await screen.findByText('已核銷交易明細')).toBeInTheDocument();
    expect(screen.getByText(/已核銷 · 唯讀查閱/)).toBeInTheDocument();
  });

  it('does not render formal reconciliation reason input in import panel', () => {
    render(<FinanceBankReconciliationWorkspace {...defaultProps} financeWorkbook={new File(['test'], 'test.xlsx')} />);

    expect(screen.queryByText(/正式銷帳原因/)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText('輸入銷帳說明')).not.toBeInTheDocument();
  });
});
