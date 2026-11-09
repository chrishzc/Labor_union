/**
 * File: receipt_reconciliation.test.tsx
 * Description: 驗證本案客戶入款核銷面板之期款選取過濾、餘額試算與阻擋訊息。
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ClientReceiptReconciliationPanel } from '../../../../../../../components/ClientReceiptReconciliationPanel';
import { clientReceiptQueryClient } from '../../../../../../../api/client_finance/client_receipt_query_client';
import { clientReceiptReconciliationClient, type ReceiptPreview } from '../../../../../../../api/client_finance/client_receipt_reconciliation_client';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import { ClientReceiptQuerySchema } from '../../../../../../../api/client_finance/client_receipt_query_schemas';
import type { ClientReceiptQuery } from '../../../../../../../api/client_finance/client_receipt_query_schemas';
import { financeAccountingClient, type CaseAccounting } from '../../../../../../../api/finance_import/finance_accounting_client';
vi.mock('../../../../../../../api/finance_import/finance_accounting_client',()=>({financeAccountingClient:{query:vi.fn()}}));
vi.mock('../../../../../../../api/client_finance/client_receipt_query_client',()=>({clientReceiptQueryClient:{query:vi.fn()}}));
vi.mock('../../../../../../../api/client_finance/client_receipt_reconciliation_client',()=>({clientReceiptReconciliationClient:{preview:vi.fn(),apply:vi.fn()}}));
const facts={case_no:'CASE',account_version:1,bank_facts:[{finance_import_row_id:9,amount_ntd:9000,transaction_date:'2026-10-01',dedup_fingerprint:'a'.repeat(64)},{finance_import_row_id:10,amount_ntd:1000,transaction_date:'2026-10-02',dedup_fingerprint:'b'.repeat(64)}],obligations:[{obligation_identity:'first',payment_stage:'first' as const,amount_due_ntd:5000,due_date:'2026-09-01'},{obligation_identity:'second',payment_stage:'second' as const,amount_due_ntd:5000,due_date:'2026-10-01'}]};
function preview(status:ReceiptPreview['candidate']['status']='exact'):ReceiptPreview{return{account_version:1,preview_fingerprint:'c'.repeat(64),candidate:{status,payment_stage:null,bank_total:{amount:status==='partial'||status==='review_required'?9000:10000},obligation_total:{amount:10000},overage_amount:{amount:0},allocations:[],blockers:status==='review_required'?['client_receipt_underpaid']:[],settlement_identity:'d'.repeat(64)}};}
function accounting(current:ClientReceiptQuery,initial:ClientReceiptQuery=current):CaseAccounting{
  const items=[...new Map([...initial.obligations,...current.obligations].map(item=>[item.obligation_identity,item])).values()];
  return {case_no:current.case_no,client_name:'測試客戶',receivable_ntd:10000,received_ntd:0,payable_ntd:null,paid_ntd:null,
    pending_warning_count:0,staff_items:[],transactions:[],warnings:[],customer_amount_ntd:10000,customer_fully_received:current.obligations.length===0,
    client_items:items.map(item=>({identity:item.obligation_identity,direction:'receivable',label:item.payment_stage,party:'測試客戶',
      expected_ntd:item.amount_due_ntd,actual_ntd:0,has_payment:false,version:`${current.account_version}:1:0`,due_date:item.due_date,
      remaining_ntd:current.obligations.find(row=>row.obligation_identity===item.obligation_identity)?.amount_due_ntd??0}))};
}
beforeEach(()=>{
  vi.clearAllMocks();vi.mocked(clientReceiptQueryClient.query).mockResolvedValue(facts);vi.mocked(clientReceiptReconciliationClient.preview).mockResolvedValue(preview());
  vi.mocked(financeAccountingClient.query).mockImplementation(async()=>accounting(
    await vi.mocked(clientReceiptQueryClient.query).mock.results.at(-1)!.value,
    await vi.mocked(clientReceiptQueryClient.query).mock.results[0].value));
});
describe('本案客戶入款核銷',()=>{
  it.each(['bank_transaction_date_missing','bank_currency_not_twd'])('shows the same actual source rejection for preview and confirmation: %s',async code=>{
    const message=code==='bank_transaction_date_missing'?'原銀行流水缺少交易日':'原銀行流水幣別不是新臺幣';
    vi.mocked(clientReceiptReconciliationClient.preview).mockRejectedValueOnce(new ApiHttpError(422,code,'source invalid'));
    render(<ClientReceiptReconciliationPanel caseNo="CASE" onChanged={vi.fn()}/>);
    fireEvent.click(await screen.findByRole('button',{name:'核對本案入款'}));
    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(clientReceiptReconciliationClient.apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'核對本案入款'}));
    vi.mocked(clientReceiptReconciliationClient.apply).mockRejectedValueOnce(new ApiHttpError(422,code,'source invalid'));
    fireEvent.click(await screen.findByRole('button',{name:'確認核銷本次收款'}));
    expect(await screen.findByRole('alert')).toHaveTextContent(message);
  });

  it('allows explicit reconciliation of two same-case sources when the original period date is missing',async()=>{
    vi.mocked(clientReceiptQueryClient.query).mockResolvedValue({...facts,obligations:[{...facts.obligations[0],amount_due_ntd:10000,due_date:null}]});
    vi.mocked(clientReceiptReconciliationClient.preview).mockResolvedValue({...preview(),candidate:{...preview().candidate,allocations:[
      {bank_fact_identity:'9',obligation_identity:'first',amount:{amount:9000}},
      {bank_fact_identity:'10',obligation_identity:'first',amount:{amount:1000}},
    ]}});
    vi.mocked(clientReceiptReconciliationClient.apply).mockResolvedValue({case_no:'CASE',account_version:2,status:'exact',settlement_identity:'d'.repeat(64),ledger_entry_count:2,allocation_count:2,blockers:[]});
    render(<ClientReceiptReconciliationPanel caseNo="CASE" onChanged={vi.fn()}/>);
    fireEvent.click(await screen.findByRole('button',{name:'核對本案入款'}));
    expect(await screen.findByRole('table',{name:'本次期款核銷明細'})).toHaveTextContent('NT$ 10,000');
    fireEvent.click(screen.getByRole('button',{name:'確認核銷本次收款'}));
    await waitFor(()=>expect(clientReceiptReconciliationClient.apply).toHaveBeenCalledOnce());
    expect(clientReceiptReconciliationClient.apply).toHaveBeenCalledWith('CASE',expect.objectContaining({selection:{payment_stage:null,finance_import_row_ids:[9,10],obligation_identities:['first']}}));
    expect(screen.queryByText(/疑似重複/)).not.toBeInTheDocument();
  });
  it.each([
    {mode:'exact',cash:12000,selected:['first'],allocated:12000,selectedRemaining:0,otherRemaining:6000},
    {mode:'exact',cash:18000,selected:['deposit','first'],allocated:18000,selectedRemaining:0,otherRemaining:0},
    {mode:'partial',cash:9000,selected:['first'],allocated:9000,selectedRemaining:3000,otherRemaining:6000},
    {mode:'overage',cash:12500,selected:['first'],allocated:12000,selectedRemaining:0,otherRemaining:6000},
  ] as const)('shows selected periods and the whole-case remainder before $mode confirmation ($cash)',async scenario=>{
    const original={...facts,bank_facts:[{...facts.bank_facts[0],amount_ntd:scenario.cash}],obligations:[
      {obligation_identity:'deposit',payment_stage:'deposit' as const,amount_due_ntd:6000,due_date:'2026-06-26'},
      {obligation_identity:'first',payment_stage:'first' as const,amount_due_ntd:12000,due_date:'2026-10-19'},
    ]};
    const selected=original.obligations.filter(item=>(scenario.selected as readonly string[]).includes(item.obligation_identity));
    let remainingCash=scenario.allocated;
    const allocations=selected.map(item=>{const amount=Math.min(item.amount_due_ntd,remainingCash);remainingCash-=amount;return{bank_fact_identity:'9',obligation_identity:item.obligation_identity,amount:{amount}};});
    const candidate={...preview().candidate,status:scenario.mode,bank_total:{amount:scenario.cash},obligation_total:{amount:selected.reduce((sum,item)=>sum+item.amount_due_ntd,0)},overage_amount:{amount:scenario.mode==='overage'?500:0},allocations};
    const after={...original,account_version:2,bank_facts:[],obligations:original.obligations.map(item=>({...item,amount_due_ntd:item.amount_due_ntd-(allocations.find(row=>row.obligation_identity===item.obligation_identity)?.amount.amount??0)})).filter(item=>item.amount_due_ntd>0)};
    vi.mocked(clientReceiptQueryClient.query).mockImplementation(async()=>vi.mocked(clientReceiptReconciliationClient.apply).mock.calls.length?after:original);
    vi.mocked(clientReceiptReconciliationClient.preview).mockResolvedValueOnce({...preview(),candidate:{...candidate,status:scenario.mode==='exact'?'exact':'review_required',allocations:scenario.mode==='exact'?allocations:[]}});
    if(scenario.mode!=='exact')vi.mocked(clientReceiptReconciliationClient.preview).mockResolvedValueOnce({...preview(),candidate});
    vi.mocked(clientReceiptReconciliationClient.apply).mockResolvedValue({case_no:'CASE',account_version:2,status:scenario.mode,settlement_identity:'d'.repeat(64),ledger_entry_count:1,allocation_count:allocations.length,blockers:[]});
    render(<ClientReceiptReconciliationPanel caseNo="CASE" requiredBankRowId={9} onChanged={vi.fn()}/>);
    await screen.findByRole('checkbox',{name:'納入銀行款 9'});
    const boxes=screen.getAllByRole('checkbox');
    for(const item of selected)fireEvent.click(boxes[original.obligations.indexOf(item)+1]);
    expect(screen.queryByText(/全額銷帳結清|案件已結清/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'核對本案入款'}));
    if(scenario.mode!=='exact')fireEvent.change(await screen.findByRole('combobox',{name:'選擇差額處理'}),{target:{value:scenario.mode}});
    const table=await screen.findByRole('table',{name:'本次期款核銷明細'});
    expect(within(table).getAllByRole('row')).toHaveLength(selected.length+1);
    for(const item of selected){
      const row=within(table).getByText(item.payment_stage==='deposit'?'訂金期款':'第一期期款').closest('tr')!;
      const amount=allocations.find(allocation=>allocation.obligation_identity===item.obligation_identity)!.amount.amount;
      expect(within(row).getAllByRole('cell').map(cell=>cell.textContent)).toEqual([item.payment_stage==='deposit'?'訂金期款':'第一期期款',item.due_date,`NT$ ${amount.toLocaleString()}`,`NT$ ${(item.amount_due_ntd-amount).toLocaleString()}`]);
    }
    const summary=screen.getByLabelText('本次核銷後餘額');
    for(const [label,amount] of [['本次核銷合計',scenario.allocated],['本次選取期款剩餘待收',scenario.selectedRemaining],['其他未選期款待收',scenario.otherRemaining],['核銷後案件全部應收餘額',scenario.selectedRemaining+scenario.otherRemaining]] as const){
      expect(within(summary).getByText(label).nextElementSibling).toHaveTextContent(`NT$ ${amount.toLocaleString()}`);
    }
    expect(screen.queryByText(/案件已結清/)).not.toBeInTheDocument();
    expect(clientReceiptReconciliationClient.apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'確認核銷本次收款'}));
    if(scenario.selectedRemaining+scenario.otherRemaining===0)expect(await screen.findByText(/已核銷本次收款。 案件已結清。/)).toBeInTheDocument();
    else{
      expect(await screen.findByText(new RegExp(`案件尚有待收 NT\\$ ${(scenario.selectedRemaining+scenario.otherRemaining).toLocaleString()}。`))).toBeInTheDocument();
      expect(screen.queryByText(/案件已結清/)).not.toBeInTheDocument();
    }
  });

  it('does not offer confirmation when the case query and preview have different versions',async()=>{
    vi.mocked(clientReceiptReconciliationClient.preview).mockResolvedValue({...preview(),account_version:2});
    render(<ClientReceiptReconciliationPanel caseNo="CASE" onChanged={vi.fn()}/>);
    fireEvent.click(await screen.findByRole('button',{name:'核對本案入款'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('核對失敗，資料可能已變更');
    expect(screen.queryByRole('button',{name:'確認核銷本次收款'})).not.toBeInTheDocument();
    expect(screen.queryByText(/案件已結清/)).not.toBeInTheDocument();
  });

  it('does not claim settlement from an older readback even when no obligations are returned',async()=>{
    vi.mocked(clientReceiptReconciliationClient.apply).mockResolvedValue({case_no:'CASE',account_version:2,status:'exact',settlement_identity:'d'.repeat(64),ledger_entry_count:2,allocation_count:2,blockers:[]});
    vi.mocked(clientReceiptQueryClient.query).mockImplementation(async()=>vi.mocked(clientReceiptReconciliationClient.apply).mock.calls.length?{...facts,obligations:[]}:facts);
    render(<ClientReceiptReconciliationPanel caseNo="CASE" onChanged={vi.fn()}/>);
    fireEvent.click(await screen.findByRole('button',{name:'核對本案入款'}));
    fireEvent.click(await screen.findByRole('button',{name:'確認核銷本次收款'}));
    expect(await screen.findByText(/案件餘額尚待重新查詢確認/)).toBeInTheDocument();
    expect(screen.queryByText(/案件已結清/)).not.toBeInTheDocument();
  });

  it.each(['missing terms','unknown balance','missing rows','old version','wrong case','unavailable'] as const)(
    'does not infer whole-case zero from an empty open-period list when accounting has %s',async condition=>{
      vi.mocked(clientReceiptReconciliationClient.preview).mockResolvedValue({...preview(),candidate:{...preview().candidate,allocations:[
        {bank_fact_identity:'9',obligation_identity:'first',amount:{amount:5000}},
        {bank_fact_identity:'9',obligation_identity:'second',amount:{amount:4000}},
        {bank_fact_identity:'10',obligation_identity:'second',amount:{amount:1000}},
      ]}});
      vi.mocked(clientReceiptReconciliationClient.apply).mockResolvedValue({case_no:'CASE',account_version:2,status:'exact',settlement_identity:'d'.repeat(64),ledger_entry_count:2,allocation_count:2,blockers:[]});
      vi.mocked(clientReceiptQueryClient.query).mockImplementation(async()=>vi.mocked(clientReceiptReconciliationClient.apply).mock.calls.length?{...facts,account_version:2,bank_facts:[],obligations:[]}:facts);
      vi.mocked(financeAccountingClient.query).mockImplementation(async()=>{
        if(condition==='unavailable')throw new Error('accounting unavailable');
        const current=await vi.mocked(clientReceiptQueryClient.query).mock.results.at(-1)!.value;
        const value=accounting(current,facts);
        if(condition==='missing terms')value.customer_amount_ntd=null;
        if(condition==='unknown balance')value.client_items[0].remaining_ntd=null;
        if(condition==='missing rows')value.client_items=[];
        if(condition==='old version')value.client_items[0].version='0:1:0';
        if(condition==='wrong case')value.case_no='OTHER';
        return value;
      });
      render(<ClientReceiptReconciliationPanel caseNo="CASE" onChanged={vi.fn()}/>);
      fireEvent.click(await screen.findByRole('button',{name:'核對本案入款'}));
      const summary=await screen.findByLabelText('本次核銷後餘額');
      expect(within(summary).getByText('核銷後案件全部應收餘額').nextElementSibling).toHaveTextContent('待確認');
      expect(screen.queryByText(/案件所有應收餘額將歸零/)).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole('button',{name:'確認核銷本次收款'}));
      expect(await screen.findByText(/已核銷本次收款。 案件餘額尚待重新查詢確認。/)).toBeInTheDocument();
      expect(screen.queryByText(/案件已結清/)).not.toBeInTheDocument();
    });

  it('clears a confirmed settlement label when switching cases or refreshing without a successful readback',async()=>{
    vi.mocked(clientReceiptReconciliationClient.apply).mockResolvedValue({case_no:'CASE',account_version:2,status:'exact',settlement_identity:'d'.repeat(64),ledger_entry_count:2,allocation_count:2,blockers:[]});
    vi.mocked(clientReceiptQueryClient.query).mockImplementation(async()=>vi.mocked(clientReceiptReconciliationClient.apply).mock.calls.length?{...facts,account_version:2,bank_facts:[],obligations:[]}:facts);
    const view=render(<ClientReceiptReconciliationPanel caseNo="CASE" onChanged={vi.fn()}/>);
    fireEvent.click(await screen.findByRole('button',{name:'核對本案入款'}));
    fireEvent.click(await screen.findByRole('button',{name:'確認核銷本次收款'}));
    await screen.findByText(/案件已結清/);
    vi.mocked(clientReceiptQueryClient.query).mockRejectedValueOnce(new Error('readback unavailable'));
    fireEvent.click(screen.getByRole('button',{name:'重新查詢'}));
    await screen.findByRole('alert');
    expect(screen.queryByText(/案件已結清/)).not.toBeInTheDocument();
    vi.mocked(clientReceiptQueryClient.query).mockResolvedValue({...facts,case_no:'OTHER'});
    view.rerender(<ClientReceiptReconciliationPanel caseNo="OTHER" onChanged={vi.fn()}/>);
    await screen.findByRole('checkbox',{name:'納入銀行款 9'});
    expect(screen.queryByText(/案件已結清|已核銷本次收款/)).not.toBeInTheDocument();
  });

  it('keeps an undated adjustment in the whole-case balance without adding staff or refund settlement gates',async()=>{
    const original={...facts,bank_facts:[{...facts.bank_facts[0],amount_ntd:10000}],obligations:[
      {...facts.obligations[0],amount_due_ntd:10000},
      {obligation_identity:'historical-service:CASE:revision:1:client:receivable_from_client',payment_stage:'adjustment' as const,amount_due_ntd:8000,due_date:null},
    ]};
    const after={...original,account_version:2,bank_facts:[],obligations:[original.obligations[1]]};
    vi.mocked(clientReceiptQueryClient.query).mockImplementation(async()=>vi.mocked(clientReceiptReconciliationClient.apply).mock.calls.length?after:original);
    vi.mocked(financeAccountingClient.query).mockImplementation(async()=>{
      const current=await vi.mocked(clientReceiptQueryClient.query).mock.results.at(-1)!.value;
      const value=accounting(current,original);
      value.staff_items=[{identity:'staff',direction:'payable',label:'月嫂款',party:'測試月嫂',expected_ntd:9000,actual_ntd:0,
        has_payment:false,version:'staff:1',due_date:null,remaining_ntd:9000}];
      value.client_items.push({...value.client_items[0],identity:'refund',direction:'payable',remaining_ntd:500});
      return value;
    });
    vi.mocked(clientReceiptReconciliationClient.preview).mockResolvedValue({...preview(),candidate:{...preview().candidate,allocations:[
      {bank_fact_identity:'9',obligation_identity:'first',amount:{amount:10000}},
    ]}});
    vi.mocked(clientReceiptReconciliationClient.apply).mockResolvedValue({case_no:'CASE',account_version:2,status:'exact',settlement_identity:'d'.repeat(64),ledger_entry_count:1,allocation_count:1,blockers:[]});
    render(<ClientReceiptReconciliationPanel caseNo="CASE" requiredBankRowId={9} initialObligationId="first" onChanged={vi.fn()}/>);
    const inspectButton=await screen.findByRole('button',{name:'核對本案入款'});
    expect(screen.queryByText('調整應收款')).not.toBeInTheDocument();
    expect(screen.queryByText('historical-service:CASE:revision:1:client:receivable_from_client')).not.toBeInTheDocument();
    fireEvent.click(inspectButton);
    const summary=await screen.findByLabelText('本次核銷後餘額');
    expect(within(summary).getByText('其他未選期款待收').nextElementSibling).toHaveTextContent('NT$ 8,000');
    expect(within(summary).getByText('核銷後案件全部應收餘額').nextElementSibling).toHaveTextContent('NT$ 8,000');
    fireEvent.click(screen.getByRole('button',{name:'確認核銷本次收款'}));
    expect(await screen.findByText(/已核銷本次收款。 案件尚有待收 NT\$ 8,000。/)).toBeInTheDocument();
  });

  it('does not claim settlement if a previously observed period disappears from the full readback',async()=>{
    vi.mocked(clientReceiptReconciliationClient.apply).mockResolvedValue({case_no:'CASE',account_version:2,status:'exact',settlement_identity:'d'.repeat(64),ledger_entry_count:2,allocation_count:2,blockers:[]});
    vi.mocked(clientReceiptQueryClient.query).mockImplementation(async()=>vi.mocked(clientReceiptReconciliationClient.apply).mock.calls.length?{...facts,account_version:2,bank_facts:[],obligations:[]}:facts);
    vi.mocked(financeAccountingClient.query).mockImplementation(async()=>{
      const current=await vi.mocked(clientReceiptQueryClient.query).mock.results.at(-1)!.value;
      const value=accounting(current,facts);
      if(current.account_version===2)value.client_items.shift();
      return value;
    });
    render(<ClientReceiptReconciliationPanel caseNo="CASE" onChanged={vi.fn()}/>);
    fireEvent.click(await screen.findByRole('button',{name:'核對本案入款'}));
    fireEvent.click(await screen.findByRole('button',{name:'確認核銷本次收款'}));
    expect(await screen.findByText(/案件餘額尚待重新查詢確認/)).toBeInTheDocument();
    expect(screen.queryByText(/案件已結清/)).not.toBeInTheDocument();
  });

  it.each([true, false])('does not calculate overage or promise settlement without selected periods (no open periods: %s)', async noOpen => {
    vi.mocked(clientReceiptQueryClient.query).mockResolvedValue({ ...facts, obligations: noOpen ? [] : facts.obligations });
    render(<ClientReceiptReconciliationPanel caseNo="CASE" requiredBankRowId={9} onChanged={vi.fn()} />);
    await screen.findByRole('checkbox', { name: '納入銀行款 9' });
    expect(await screen.findByText(noOpen ? '本案目前沒有未清期款，無款項可核銷。請回案件帳務查核。'
      : '請先選擇本次要核銷的期款，再核對金額。')).toBeInTheDocument();
    expect(screen.getByText('尚未核對')).toBeInTheDocument();
    expect(screen.queryByText(/超收|全額銷帳結清|確認後期款全額結清|待退款|金額相符/)).not.toBeInTheDocument();
    const inspect = screen.getByRole('button', { name: '核對本案入款' });
    expect(inspect).toBeDisabled(); fireEvent.click(inspect);
    expect(clientReceiptReconciliationClient.preview).not.toHaveBeenCalled();
    expect(clientReceiptReconciliationClient.apply).not.toHaveBeenCalled();
  });

  it('clears a prior result and amount comparison when all periods are deselected', async () => {
    render(<ClientReceiptReconciliationPanel caseNo="CASE" onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: '核對本案入款' }));
    await screen.findByRole('button', { name: '確認核銷本次收款' });
    for (const box of screen.getAllByRole('checkbox').slice(2)) fireEvent.click(box);
    expect(screen.getByText('請先選擇本次要核銷的期款，再核對金額。')).toBeInTheDocument();
    expect(screen.queryByText(/超收|合計相符|全額銷帳結清|確認後期款全額結清|待退款|金額相符/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '確認核銷本次收款' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '核對本案入款' })).toBeDisabled();
    expect(clientReceiptReconciliationClient.apply).not.toHaveBeenCalled();
  });

  it('does not promise receipt or settlement when all bank sources are deselected', async () => {
    render(<ClientReceiptReconciliationPanel caseNo="CASE" onChanged={vi.fn()} />);
    await screen.findByRole('checkbox', { name: '納入銀行款 9' });
    fireEvent.click(screen.getByRole('checkbox', { name: '納入銀行款 9' }));
    fireEvent.click(screen.getByRole('checkbox', { name: '納入銀行款 10' }));
    expect(screen.getByText('請先選擇本次要核銷的銀行入款，再核對金額。')).toBeInTheDocument();
    expect(screen.queryByText(/短少|超收|全額銷帳結清|確認後期款全額結清|金額相符/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '核對本案入款' })).toBeDisabled();
  });

  it('resumes the actual comparison after a period is selected', async () => {
    render(<ClientReceiptReconciliationPanel caseNo="CASE" requiredBankRowId={9} onChanged={vi.fn()} />);
    await screen.findByRole('checkbox', { name: '納入銀行款 9' });
    expect(screen.queryByText(/超收/)).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('checkbox')[2]);
    expect(screen.getByText('超收 NT$ 4,000')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '核對本案入款' })).toBeEnabled();
    expect(screen.queryByText('尚未核對')).not.toBeInTheDocument();
  });
  it.each([
    [['bank_transaction_date_missing'], '原銀行流水缺少交易日，無法核銷客戶入款，請先查核來源資料。'],
    [['bank_currency_not_twd'], '原銀行流水幣別不是新臺幣，無法核銷客戶入款，請先查核來源資料。'],
    [['bank_transaction_date_missing', 'bank_currency_not_twd'], '原銀行流水缺少交易日，無法核銷客戶入款，請先查核來源資料。 原銀行流水幣別不是新臺幣，無法核銷客戶入款，請先查核來源資料。'],
  ])('shows authoritative source causes instead of claiming that the case is unidentified: %j', async (codes, message) => {
    vi.mocked(clientReceiptQueryClient.query).mockResolvedValue(ClientReceiptQuerySchema.parse({ ...facts,
      bank_facts: [facts.bank_facts[1]], bank_fact_blockers: [{ finance_import_row_id: 9, codes }],
    }));
    const changed = vi.fn();
    render(<ClientReceiptReconciliationPanel caseNo="CASE" requiredBankRowId={9} onChanged={changed} />);
    expect(await screen.findByRole('alert')).toHaveTextContent(message as string);
    expect(screen.queryByText(/此筆交易尚未辨識為本案入款/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '核對本案入款' })).not.toBeInTheDocument();
    expect(clientReceiptReconciliationClient.preview).not.toHaveBeenCalled();
    expect(clientReceiptReconciliationClient.apply).not.toHaveBeenCalled();
    expect(changed).not.toHaveBeenCalled();
  });

  it('does not use another source rejection to explain an unrecognized source', async () => {
    vi.mocked(clientReceiptQueryClient.query).mockResolvedValue({ ...facts, bank_facts: [],
      bank_fact_blockers: [{ finance_import_row_id: 10, codes: ['bank_currency_not_twd'] }],
    });
    render(<ClientReceiptReconciliationPanel caseNo="CASE" requiredBankRowId={9} onChanged={vi.fn()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('此筆交易尚未辨識為本案入款');
    expect(screen.queryByText(/幣別不是新臺幣/)).not.toBeInTheDocument();
  });

  it('keeps unrelated rejected sources out of the normal receipt selection', async () => {
    vi.mocked(clientReceiptQueryClient.query).mockResolvedValue({ ...facts,
      bank_fact_blockers: [{ finance_import_row_id: 11, codes: ['bank_transaction_date_missing'] }],
    });
    render(<ClientReceiptReconciliationPanel caseNo="CASE" requiredBankRowId={9} onChanged={vi.fn()} />);
    expect(await screen.findByRole('checkbox', { name: '納入銀行款 9' })).toBeChecked();
    expect(screen.queryByRole('checkbox', { name: '納入銀行款 11' })).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('rejects undeclared or unsafe source-diagnostic fields', () => {
    for (const item of [
      { finance_import_row_id: 9, codes: ['invented_reason'] },
      { finance_import_row_id: 9, codes: [] },
      { finance_import_row_id: 9, codes: ['bank_currency_not_twd'], raw_account: 'private' },
    ]) expect(ClientReceiptQuerySchema.safeParse({ ...facts, bank_fact_blockers: [item] }).success).toBe(false);
  });
  it('blocks an overage preview with the actual missing-refund-account reason and offers no confirmation',async()=>{
    vi.mocked(clientReceiptReconciliationClient.preview).mockResolvedValueOnce({...preview('review_required'),candidate:{...preview('review_required').candidate,bank_total:{amount:11000}}})
      .mockRejectedValueOnce(new ApiHttpError(422,'client_refund_recipient_snapshot_missing','validation'));
    const changed=vi.fn();render(<ClientReceiptReconciliationPanel caseNo="CASE" onChanged={changed}/>);
    fireEvent.click(await screen.findByRole('button',{name:'核對本案入款'}));
    fireEvent.change(await screen.findByRole('combobox',{name:'選擇差額處理'}),{target:{value:'overage'}});
    expect(await screen.findByRole('alert')).toHaveTextContent('報名資料缺少客戶退款帳戶，本次未核銷。請先補齊退款帳戶資料，再回本案核對。');
    expect(screen.queryByRole('button',{name:'確認核銷本次收款'})).not.toBeInTheDocument();
    expect(screen.queryByText(/合計相符|案件已結清/)).not.toBeInTheDocument();
    expect(clientReceiptReconciliationClient.apply).not.toHaveBeenCalled();
    expect(changed).not.toHaveBeenCalled();
  });

  it('shows the same missing-refund-account reason if the account disappears after preview',async()=>{
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
    fireEvent.click(screen.getByRole('button',{name:'確認核銷本次收款'}));expect(await screen.findByText(/^已核銷本次收款。/)).toBeInTheDocument();expect(changed).toHaveBeenCalledOnce();
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
    expect(await screen.findByText(/^已記錄實際收款，剩餘款項繼續待收。/)).toBeInTheDocument();
  });
  it('starts from the selected bank transaction and only includes explicitly selected related rows and periods', async () => {
    render(<ClientReceiptReconciliationPanel caseNo="CASE" requiredBankRowId={9} onChanged={vi.fn()} />);
    const source = await screen.findByRole('checkbox', { name: '納入銀行款 9' });
    const related = screen.getByRole('checkbox', { name: '納入銀行款 10' });
    expect(source).toBeChecked();
    expect(source).toBeEnabled();
    expect(related).not.toBeChecked();
    const periods = screen.getAllByRole('checkbox').slice(2);
    for (const period of periods) expect(period).not.toBeChecked();
    fireEvent.click(related);
    for (const period of periods) fireEvent.click(period);
    fireEvent.click(screen.getByRole('button', { name: '核對本案入款' }));
    await waitFor(() => expect(clientReceiptReconciliationClient.preview).toHaveBeenCalledWith(
      'CASE', { payment_stage: null, finance_import_row_ids: [9, 10], obligation_identities: ['first', 'second'] }, 'exact',
    ));
    expect(clientReceiptReconciliationClient.apply).not.toHaveBeenCalled();
  });
  it('replaces the entry source with another same-case receipt and requires a fresh preview before applying', async () => {
    const original={...facts,bank_facts:facts.bank_facts.map(row=>({...row,amount_ntd:12000})),obligations:[
      {obligation_identity:'deposit',payment_stage:'deposit' as const,amount_due_ntd:12000,due_date:'2026-03-13'},
      {obligation_identity:'first',payment_stage:'first' as const,amount_due_ntd:24000,due_date:'2026-06-03'},
    ]};
    vi.mocked(clientReceiptQueryClient.query).mockResolvedValue(original);
    vi.mocked(clientReceiptReconciliationClient.preview).mockResolvedValue({...preview(),candidate:{...preview().candidate,
      bank_total:{amount:12000},obligation_total:{amount:12000},
      allocations:[{bank_fact_identity:'10',obligation_identity:'deposit',amount:{amount:12000}}],
    }});
    vi.mocked(clientReceiptReconciliationClient.apply).mockResolvedValue({case_no:'CASE',account_version:2,status:'exact',settlement_identity:'d'.repeat(64),ledger_entry_count:1,allocation_count:1,blockers:[]});
    render(<ClientReceiptReconciliationPanel caseNo="CASE" requiredBankRowId={10} initialObligationId="deposit" onChanged={vi.fn()} />);
    const entry=await screen.findByRole('checkbox',{name:'納入銀行款 10'});
    const other=screen.getByRole('checkbox',{name:'納入銀行款 9'});
    expect(entry).toBeChecked();expect(entry).toBeEnabled();expect(other).not.toBeChecked();
    fireEvent.click(screen.getByRole('button',{name:'核對本案入款'}));
    await screen.findByRole('button',{name:'確認核銷本次收款'});
    fireEvent.click(entry);
    expect(screen.queryByRole('button',{name:'確認核銷本次收款'})).not.toBeInTheDocument();
    expect(screen.getByRole('button',{name:'核對本案入款'})).toBeDisabled();
    expect(screen.getByText('尚未核對')).toBeInTheDocument();
    fireEvent.click(other);
    expect(entry).not.toBeChecked();expect(other).toBeChecked();
    expect(clientReceiptReconciliationClient.apply).not.toHaveBeenCalled();
    vi.mocked(clientReceiptReconciliationClient.preview).mockResolvedValue({...preview(),candidate:{...preview().candidate,
      bank_total:{amount:12000},obligation_total:{amount:12000},
      allocations:[{bank_fact_identity:'9',obligation_identity:'deposit',amount:{amount:12000}}],
    }});
    fireEvent.click(screen.getByRole('button',{name:'核對本案入款'}));
    await screen.findByRole('button',{name:'確認核銷本次收款'});
    expect(clientReceiptReconciliationClient.preview).toHaveBeenLastCalledWith('CASE',
      {payment_stage:null,finance_import_row_ids:[9],obligation_identities:['deposit']},'exact');
    fireEvent.click(screen.getByRole('button',{name:'確認核銷本次收款'}));
    await waitFor(()=>expect(clientReceiptReconciliationClient.apply).toHaveBeenCalledWith('CASE',expect.objectContaining({
      selection:{payment_stage:null,finance_import_row_ids:[9],obligation_identities:['deposit']},
    })));
  });
});
