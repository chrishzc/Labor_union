import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ClientReceiptReconciliationPanel } from '../../../../../../../components/ClientReceiptReconciliationPanel';
import { clientReceiptQueryClient } from '../../../../../../../api/client_finance/client_receipt_query_client';
import { clientReceiptReconciliationClient, type ReceiptPreview } from '../../../../../../../api/client_finance/client_receipt_reconciliation_client';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
vi.mock('../../../../../../../api/client_finance/client_receipt_query_client',()=>({clientReceiptQueryClient:{query:vi.fn()}}));
vi.mock('../../../../../../../api/client_finance/client_receipt_reconciliation_client',()=>({clientReceiptReconciliationClient:{preview:vi.fn(),apply:vi.fn()}}));
const facts={case_no:'CASE',account_version:1,bank_facts:[{finance_import_row_id:9,amount_ntd:9000,transaction_date:'2026-10-01',dedup_fingerprint:'a'.repeat(64)},{finance_import_row_id:10,amount_ntd:1000,transaction_date:'2026-10-02',dedup_fingerprint:'b'.repeat(64)}],obligations:[{obligation_identity:'first',payment_stage:'first' as const,amount_due_ntd:5000,due_date:'2026-09-01'},{obligation_identity:'second',payment_stage:'second' as const,amount_due_ntd:5000,due_date:'2026-10-01'}]};
function preview(status:ReceiptPreview['candidate']['status']='exact'):ReceiptPreview{return{account_version:1,preview_fingerprint:'c'.repeat(64),candidate:{status,payment_stage:null,bank_total:{amount:status==='partial'||status==='review_required'?9000:10000},obligation_total:{amount:10000},overage_amount:{amount:0},allocations:[],blockers:status==='review_required'?['client_receipt_underpaid']:[],settlement_identity:'d'.repeat(64)}};}
beforeEach(()=>{vi.clearAllMocks();vi.mocked(clientReceiptQueryClient.query).mockResolvedValue(facts);vi.mocked(clientReceiptReconciliationClient.preview).mockResolvedValue(preview());});
describe('本案客戶入款核銷',()=>{
  it('explains missing refund-account validation without claiming settlement or offering an unavailable editor',async()=>{
    vi.mocked(clientReceiptReconciliationClient.preview).mockResolvedValue(preview('overage'));
    vi.mocked(clientReceiptReconciliationClient.apply).mockRejectedValue(new ApiHttpError(422,'client_refund_recipient_snapshot_missing','validation'));
    const changed=vi.fn();render(<ClientReceiptReconciliationPanel caseNo="CASE" onChanged={changed}/>);
    fireEvent.click(await screen.findByRole('button',{name:'核對本案入款'}));
    fireEvent.click(await screen.findByRole('button',{name:'確認核銷本次收款'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('報名資料缺少客戶退款帳戶，本次未核銷。');
    expect(screen.queryByRole('link',{name:/客戶名冊/})).not.toBeInTheDocument();
    expect(screen.queryByRole('button',{name:'確認原操作結果'})).not.toBeInTheDocument();
    expect(changed).not.toHaveBeenCalled();
  });
  it('shows both bank sources and reconciles the total across stages without a phase picker',async()=>{
    vi.mocked(clientReceiptReconciliationClient.apply).mockResolvedValue({case_no:'CASE',account_version:2,status:'exact',settlement_identity:'d'.repeat(64),ledger_entry_count:2,allocation_count:3,blockers:[]});
    const changed=vi.fn();render(<ClientReceiptReconciliationPanel caseNo="CASE" onChanged={changed}/>);
    await screen.findByText('bank:9');expect(screen.getByText('bank:10')).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();fireEvent.click(screen.getByRole('button',{name:'核對本案入款'}));
    expect(await screen.findByText('合計相符，可直接核銷。')).toBeInTheDocument();
    expect(clientReceiptReconciliationClient.preview).toHaveBeenCalledWith('CASE',{payment_stage:null,finance_import_row_ids:[9,10],obligation_identities:['first','second']},'exact');
    fireEvent.click(screen.getByRole('button',{name:'確認核銷本次收款'}));expect(await screen.findByText('已核銷本次收款。')).toBeInTheDocument();expect(changed).toHaveBeenCalledOnce();
  });
  it('does not preselect partial handling and reuses the same command when the result is unknown',async()=>{
    vi.mocked(clientReceiptReconciliationClient.preview).mockResolvedValueOnce(preview('review_required')).mockResolvedValueOnce(preview('partial'));
    vi.mocked(clientReceiptReconciliationClient.apply).mockRejectedValueOnce(new Error('timeout')).mockResolvedValueOnce({case_no:'CASE',account_version:2,status:'partial',settlement_identity:'d'.repeat(64),ledger_entry_count:2,allocation_count:2,blockers:[]});
    const changed=vi.fn();const rendered=render(<ClientReceiptReconciliationPanel caseNo="CASE" onChanged={changed} refreshVersion={0}/>);fireEvent.click(await screen.findByRole('button',{name:'核對本案入款'}));
    const choice=await screen.findByRole('combobox',{name:'選擇差額處理'});expect(choice).toHaveValue('');expect(screen.queryByRole('button',{name:'確認核銷本次收款'})).not.toBeInTheDocument();
    fireEvent.change(choice,{target:{value:'partial'}});fireEvent.click(await screen.findByRole('button',{name:'確認核銷本次收款'}));
    await screen.findByRole('button',{name:'確認原操作結果'});rendered.rerender(<ClientReceiptReconciliationPanel caseNo="CASE" onChanged={changed} refreshVersion={1}/>);
    fireEvent.click(await screen.findByRole('button',{name:'確認原操作結果'}));await waitFor(()=>expect(clientReceiptReconciliationClient.apply).toHaveBeenCalledTimes(2));
    expect(vi.mocked(clientReceiptReconciliationClient.apply).mock.calls[0]).toEqual(vi.mocked(clientReceiptReconciliationClient.apply).mock.calls[1]);
    expect(await screen.findByText('已記錄實際收款，剩餘款項繼續待收。')).toBeInTheDocument();
  });
});
