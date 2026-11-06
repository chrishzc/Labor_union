import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {FinancePage} from '../../../../../../../pages/FinancePage';
import {FinanceWorkbookSnapshot, financeImportMutationClient, type FinanceImportBatchPreview} from '../../../../../../../api/finance_import/finance_import_mutation_client';
import {financeImportQueryClient} from '../../../../../../../api/finance_import/finance_import_query_client';

vi.mock('../../../../../../../api/finance_import/finance_import_mutation_client', async original => ({
  ...await original<typeof import('../../../../../../../api/finance_import/finance_import_mutation_client')>(),
  financeImportMutationClient: {ingest:vi.fn(), preview:vi.fn(), apply:vi.fn(), queryBatchOutcome:vi.fn(), queryIngestionOutcome:vi.fn()},
}));
vi.mock('../../../../../../../api/finance_import/finance_import_query_client',()=>({financeImportQueryClient:{listBankTransactions:vi.fn(),listImportHistory:vi.fn()}}));
vi.mock('../../../../../../../components/UnsavedChanges',()=>({useUnsavedDraft:vi.fn(),useUnsavedNavigation:()=>({requestLeave:(action:()=>void)=>action()})}));
vi.mock('../../../../../../../components/FinanceStatementArchive',()=>({FinanceStatementArchive:()=>null}));
const staffDirectory=vi.hoisted(()=>({status:'ready',people:new Map(),refresh:vi.fn(),labels:{label:()=>'',compare:()=>0}}));
vi.mock('../../../../../../../components/StaffIdentityProvider',()=>({useStaffIdentityDirectory:()=>staffDirectory,useStaffIdentityLabels:()=>staffDirectory.labels}));

const fingerprint='a'.repeat(64);
const preview={batch_identity:'finance-import-batch:32',batch_version:0,preview_fingerprint:fingerprint,
  source_content_digest:'b'.repeat(64),classifier_version:'finance-transaction-classifier-v4',fingerprint_version:'v1',
  counts:{source_rows:1,canonical_created:1,duplicate_occurrences:0,ready_dispatch:1,existing:0,manual_review:0,business_pending:0,blocked:0},
  dispatch_summaries:[],rows:[],blocking_codes:[],apply_allowed:true} as FinanceImportBatchPreview;

beforeEach(()=>{
  vi.clearAllMocks();window.history.replaceState(null,'','#finance?tab=finance-import');
  vi.spyOn(FinanceWorkbookSnapshot,'fromFile').mockResolvedValue({sha256:'b'.repeat(64)} as FinanceWorkbookSnapshot);
  vi.mocked(financeImportMutationClient.ingest).mockResolvedValue({batch_identity:preview.batch_identity} as Awaited<ReturnType<typeof financeImportMutationClient.ingest>>);
  vi.mocked(financeImportMutationClient.preview).mockResolvedValue(preview);
  vi.mocked(financeImportMutationClient.apply).mockResolvedValue({job_id:'job-1',status_url:'/api/v1/jobs/job-1',replayed:false});
  vi.mocked(financeImportMutationClient.queryBatchOutcome).mockResolvedValue({job_id:'job-1',status:'failed',attempt_count:1,max_attempts:3,result_reference:null,receipt:null});
  vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({items:[],pending_count:0,next_before_row_id:null});
});

function chooseWorkbook(){
  render(<FinancePage/>);
  fireEvent.change(screen.getByLabelText('選擇銀行交易明細工作簿'),{target:{files:[new File(['fixture'],'statement.xlsx',{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})]}});
  fireEvent.click(screen.getByRole('button',{name:'匯入銀行交易明細'}));
}

describe('finance import operation identity after an observed result',()=>{
  it('allows a new confirmed submission after known failure, without reusing the failed job key',async()=>{
    chooseWorkbook();
    await screen.findByText('未完成銷帳，請查看未銷帳明細與原因。');
    const button=screen.getByRole('button',{name:'匯入銀行交易明細'});
    expect(button).toBeEnabled();
    fireEvent.click(button);
    await waitFor(()=>expect(financeImportMutationClient.apply).toHaveBeenCalledTimes(2));
    const [first,second]=vi.mocked(financeImportMutationClient.apply).mock.calls;
    expect(first[0].preview_fingerprint).toBe(second[0].preview_fingerprint);
    expect(first[2].idempotencyKey).not.toBe(second[2].idempotencyKey);
    expect(financeImportMutationClient.preview).toHaveBeenCalledTimes(2);
  });

  it('keeps the original command identity when acceptance is still unknown',async()=>{
    vi.mocked(financeImportMutationClient.apply).mockRejectedValueOnce(new Error('connection unavailable'));
    chooseWorkbook();
    fireEvent.click(await screen.findByRole('button',{name:'以原操作確認匯入結果'}));
    await waitFor(()=>expect(financeImportMutationClient.apply).toHaveBeenCalledTimes(2));
    const [first,second]=vi.mocked(financeImportMutationClient.apply).mock.calls;
    expect(second[2].idempotencyKey).toBe(first[2].idempotencyKey);
    expect(second[2].correlationId).toBe(first[2].correlationId);
    expect(second[1]).toBe(first[1]);
    expect(financeImportMutationClient.preview).toHaveBeenCalledTimes(1);
  });

  it('looks up a failed upload with the original key before allowing another upload', async () => {
    vi.mocked(financeImportMutationClient.ingest).mockRejectedValueOnce(new Error('response lost'));
    vi.mocked(financeImportMutationClient.queryIngestionOutcome).mockResolvedValue({
      status: 'rolled_back', receipt: null, source_content_digest: 'b'.repeat(64),
      error_code: 'finance_import_processing_failed', phase: 'staging',
    });
    chooseWorkbook();
    const lookup = await screen.findByRole('button', { name: '查詢原次匯入結果' });
    expect(screen.getByRole('button', { name: '匯入銀行交易明細' })).toBeDisabled();
    fireEvent.click(lookup);
    await screen.findByText('已確認原次匯入失敗，流水未保存。');
    expect(financeImportMutationClient.queryIngestionOutcome).toHaveBeenCalledWith(
      vi.mocked(financeImportMutationClient.ingest).mock.calls[0][1],
    );
    expect(financeImportMutationClient.ingest).toHaveBeenCalledOnce();
    expect(financeImportMutationClient.preview).not.toHaveBeenCalled();
  });

  it('resends the same upload with its original key when no result is recorded', async () => {
    vi.mocked(financeImportMutationClient.ingest).mockRejectedValueOnce(new Error('request lost'));
    vi.mocked(financeImportMutationClient.queryIngestionOutcome).mockResolvedValue({
      status: 'unknown', receipt: null, source_content_digest: null, error_code: null, phase: null,
    });
    chooseWorkbook();
    fireEvent.click(await screen.findByRole('button', { name: '查詢原次匯入結果' }));
    fireEvent.click(await screen.findByRole('button', { name: '以原操作重送同一檔案' }));
    await waitFor(() => expect(financeImportMutationClient.ingest).toHaveBeenCalledTimes(2));
    const [first, retry] = vi.mocked(financeImportMutationClient.ingest).mock.calls;
    expect(retry[1]).toEqual(first[1]);
  });
});
