import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {FinancePage} from '../../../../../../../pages/FinancePage';
import {FinanceWorkbookSnapshot, financeImportMutationClient, type FinanceImportBatchPreview} from '../../../../../../../api/finance_import/finance_import_mutation_client';
import {financeImportQueryClient} from '../../../../../../../api/finance_import/finance_import_query_client';

vi.mock('../../../../../../../api/finance_import/finance_import_mutation_client', async original => ({
  ...await original<typeof import('../../../../../../../api/finance_import/finance_import_mutation_client')>(),
  financeImportMutationClient: {ingest:vi.fn(), preview:vi.fn(), apply:vi.fn(), queryBatchOutcome:vi.fn()},
}));
vi.mock('../../../../../../../api/finance_import/finance_import_query_client',()=>({financeImportQueryClient:{getManifest:vi.fn(),listReviewRows:vi.fn()}}));
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
  vi.mocked(financeImportQueryClient.getManifest).mockResolvedValue({batch_identity:preview.batch_identity,review_count:0} as Awaited<ReturnType<typeof financeImportQueryClient.getManifest>>);
  vi.mocked(financeImportQueryClient.listReviewRows).mockResolvedValue({batch_identity:preview.batch_identity,items:[],source_reviews:[],next_after_row_id:null,next_after_source_review_id:null});
});

function chooseWorkbook(){
  render(<FinancePage/>);
  fireEvent.change(screen.getByLabelText('選擇銀行交易明細工作簿'),{target:{files:[new File(['fixture'],'statement.xlsx',{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'})]}});
  fireEvent.click(screen.getByRole('button',{name:'匯入銀行交易明細'}));
}

describe('finance import operation identity after an observed result',()=>{
  it('allows a new confirmed submission after known failure, without reusing the failed job key',async()=>{
    chooseWorkbook();
    await screen.findByText('未完成入帳，請查看未入帳明細與原因。');
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
});
