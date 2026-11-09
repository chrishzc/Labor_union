/**
 * File: bank_reconciliation_workspace.test.tsx
 * Description: 銀行對帳工作台（WF-03/04）單元驗收測試，驗證雙行排版、KPI膠囊、篩選與核對抽屜。
 */

import { readFileSync } from 'node:fs';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
import { caseVirtualAccountClient } from '../../../../../../../api/client_finance/case_virtual_account_client';
import { clientRegistryClient } from '../../../../../../../api/client_registry/client_registry_client';
import { ordersQueryClient } from '../../../../../../../api/orders/order_query_client';
import { paymentOverdueReminderClient } from '../../../../../../../api/line_order_groups/payment_overdue_reminder_client';
import { transport } from '../../../../../../../api/shared/transport';
import { ApiTimeoutError } from '../../../../../../../api/shared/typed_errors';
import { staffPayoutRemediationClient } from '../../../../../../../api/staff_payables/staff_payout_remediation_client';
import { staffPayoutBlockerMessage } from '../../../../../../../api/staff_payables/staff_payout_remediation_errors';
import { financeImportCorrectionClient } from '../../../../../../../api/finance_import/finance_import_correction_client';

vi.mock('../../../../../../../api/finance_import/finance_import_query_client', () => ({
  financeImportQueryClient: { listBankTransactions: vi.fn(), listImportHistory: vi.fn() },
}));
vi.mock('../../../../../../../components/FinanceStatementArchive', () => ({
  FinanceStatementArchive: ({ compact: _compact }: { compact?: boolean }) => (
    <div data-testid="statement-archive">
      <button type="button">匯出 Excel</button>
      <button type="button">匯出歷史備查</button>
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
      label: '待核對', reason: /未留存當次阻擋原因/, nextStep: /未留存當次未核銷原因，請進入核對確認/ },
    { name: 'old unknown cause', patch: { review_reason: 'unrecognized_historical_reason' },
      label: '待核對', reason: /未留存當次阻擋原因/, nextStep: /未留存當次未核銷原因，請進入核對確認/ },
    { name: 'no saved cause', patch: { review_reason: null },
      label: '待核對', reason: /未留存當次阻擋原因/, nextStep: /未留存當次未核銷原因，請進入核對確認/ },
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
      .toMatchObject({ label: '待核對', reason: expect.stringContaining('未留存實際是金額不符或有多個有效配對') });
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
    ['unique_staff_payout_name_and_month_matched', null, /月嫂姓名與同月款項已辨識，未留存當次阻擋原因/],
    ['outgoing_staff_payout_month_no_match', null, /預計撥款日同月/],
    ['outgoing_client_refund_month_no_match', null, /預計退款日同月/],
    ['sinopac_client_receipt_month_no_match', null, /原到期日同月/],
    ['outgoing_client_refund_amount_mismatch', 'client_refund_recipient_account_mismatch', /與待退款項的收款帳戶不符/],
    ['sinopac_unique_staff_account_in_transaction_reference', 'staff_bank_account_ambiguous', /唯一有效的月嫂主要帳戶/],
    ['unique_staff_payout_name_and_month_matched', 'staff_memo_recipient_unconfirmed', /備註姓名驗證未通過/],
    ['taishin_client_subsidy_case_suffix_in_memo', 'client_subsidy_memo_recipient_unconfirmed', /銀行備註無法確認本案客戶補助對象/],
    ['sinopac_valid_virtual_account', null, /已由虛擬帳號定位案件，未留存當次阻擋原因/],
    ['unrecognized_historical_reason', null, /未留存當次阻擋原因/],
    [null, null, /未留存當次阻擋原因/],
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

      const drawer = await screen.findByRole('dialog', { name: '案件帳務 · 115000001' });
      expect(await within(drawer).findByRole('heading', { name: '客戶繳款 · 核對交易' })).toBeVisible();
      expect(await within(drawer).findByRole('checkbox', { name: '納入銀行款 101' })).toBeChecked();
      expect(within(drawer).getByRole('checkbox', { name: '納入銀行款 101' })).toBeDisabled();
      expect(within(drawer).getByRole('checkbox', { name: '納入銀行款 103' })).not.toBeChecked();
      if (manual) expect(within(drawer).getByRole('checkbox', { name: /receipt:first/ })).not.toBeChecked();
      else expect(within(drawer).getByRole('checkbox', { name: /receipt:first/ })).toBeChecked();
      expect(within(drawer).getByRole('checkbox', { name: /receipt:second/ })).not.toBeChecked();
      if (manual) {
        fireEvent.click(within(drawer).getByRole('checkbox', { name: /receipt:second/ }));
        expect(within(drawer).getByRole('checkbox', { name: /receipt:second/ })).toBeChecked();
        expect(within(drawer).getByRole('checkbox', { name: /receipt:first/ })).not.toBeChecked();
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
      const drawer = await screen.findByRole('dialog', { name: '案件帳務 · 115000001' });
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
      const drawer = await screen.findByRole('dialog', { name: '案件帳務 · 115000001' });
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
      expect(get).toHaveBeenCalledTimes(2);
    } finally { mocks.forEach(mock => mock.mockRestore()); window.location.hash = ''; }
  });

  it('keeps an unresolved row visible without opening an arbitrary case', async () => {
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [{ ...sinopac, reconciliation_target: null }], pending_count: 1, next_before_row_id: null,
    });
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);
    expect(await screen.findByText('對應款項待確認')).toBeVisible();
    expect(screen.queryByRole('button', { name: '核對交易 Sheet1#2' })).not.toBeInTheDocument();
  });

  it('labels an already stored unassigned row without offering case selection or reconciliation', async () => {
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [{ ...sinopac, cases: [], reconciliation_target: null, reconciliation_unavailable_reason: 'case_unconfirmed' }],
      pending_count: 1, next_before_row_id: null,
    });
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);
    expect(await screen.findByText('尚未確認唯一案件。')).toBeVisible();
    expect(screen.queryByRole('button', { name: /核對交易|選擇案件/ })).not.toBeInTheDocument();
  });

  it('shows the missing payee on a Taishin row with an identified case', async () => {
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [{ ...taishin, direction: 'outgoing', classification_type: 'staff_salary', cases: ['115000001'],
        reconciliation_target: null, reconciliation_unavailable_reason: 'staff_unconfirmed' }], pending_count: 1, next_before_row_id: null,
    });
    render(<FinanceBankReconciliationWorkspace {...defaultProps} />);
    expect(await screen.findByText('案件已定位，尚未確認這筆出款的月嫂。')).toBeVisible();
    expect(screen.queryByRole('button', { name: /核對交易|選擇案件/ })).not.toBeInTheDocument();
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
    expect(within(dialog).getByText('交易指紋已存在，重複列已略過')).toBeVisible();
    expect(screen.getAllByRole('button', { name: '查看交易 finance-import-row:101' })).toHaveLength(1);
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
