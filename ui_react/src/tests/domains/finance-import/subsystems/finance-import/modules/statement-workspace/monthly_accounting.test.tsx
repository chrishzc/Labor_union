import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FinanceMonthlyAccounting } from '../../../../../../../components/FinanceMonthlyAccounting';
import { FinanceReceivableItems } from '../../../../../../../components/FinanceReceivableItems';
import { monthlyAccountingClient, type MonthlyAccountingReport } from '../../../../../../../api/finance_import/monthly_accounting_client';
vi.mock('../../../../../../../api/finance_import/monthly_accounting_client', () => ({ monthlyAccountingClient: { query:vi.fn(), receivables:vi.fn(), download:vi.fn(), marker:vi.fn(), mark:vi.fn() } }));

function report(): MonthlyAccountingReport {
  return {start_month:'2026-09',end_month:'2026-10',category:'subsidy',as_of:'2026-10-30',excluded_cases:['H1'],undated_item_count:1,rows:[
    {month:'2026-09',expected_in_ntd:10000,received_ntd:10000,remaining_in_ntd:0,expected_out_ntd:0,paid_ntd:0,remaining_out_ntd:0,other_in_ntd:0,other_out_ntd:0,cash_in_ntd:0,cash_out_ntd:0,items:[{case_no:'S1',client_name:'client',identity:'first',direction:'receivable',label:'第一期',party:'client',due_date:'2026-09-20',expected_ntd:10000,actual_ntd:10000,noncash_ntd:0,remaining_ntd:0}],bank_facts:[]},
    {month:'2026-10',expected_in_ntd:0,received_ntd:0,remaining_in_ntd:0,expected_out_ntd:0,paid_ntd:0,remaining_out_ntd:0,other_in_ntd:0,other_out_ntd:0,cash_in_ntd:100000,cash_out_ntd:0,items:[],bank_facts:[{identity:'b1',occurred_on:'2026-10-10',direction:'in',amount_ntd:9000,cases:['S1']},{identity:'b2',occurred_on:'2026-10-12',direction:'in',amount_ntd:1000,cases:['S1']},{identity:'government',occurred_on:'2026-10-15',direction:'in',amount_ntd:90000,cases:['S1','S2']}]},
  ]};
}
beforeEach(()=>{vi.clearAllMocks();vi.mocked(monthlyAccountingClient.query).mockResolvedValue(report());});
describe('每月帳務',()=>{
  it('queries receivables by month and keeps undated receivables in the pending view',async()=>{
    const due=report().rows[0].items;
    vi.mocked(monthlyAccountingClient.receivables).mockResolvedValue({due_month:'2026-09',category:'subsidy',items:due,undated_count:1});
    const open=vi.fn(),filters=vi.fn();
    const view=render(<FinanceReceivableItems initialFilters={{month:'2026-09',category:'subsidy',status:'all',search:''}} onCase={open} onFiltersChange={filters}/>);
    fireEvent.click(await screen.findByRole('button',{name:'查看案件'}));expect(open).toHaveBeenCalledWith('S1');
    fireEvent.change(screen.getByLabelText('到期月份'),{target:{value:'2026-10'}});fireEvent.click(screen.getByRole('button',{name:'查詢'}));
    await waitFor(()=>expect(monthlyAccountingClient.receivables).toHaveBeenLastCalledWith('2026-10','subsidy',false,expect.any(AbortSignal)));
    expect(filters).toHaveBeenLastCalledWith(expect.objectContaining({month:'2026-10'}));
    view.unmount();
    vi.mocked(monthlyAccountingClient.receivables).mockResolvedValue({due_month:null,category:'subsidy',items:[{...due[0],due_date:null}],undated_count:1});
    render(<FinanceReceivableItems undatedOnly onCase={open}/>);
    expect(await screen.findByRole('heading',{name:'未定到期日的應收款'})).toBeInTheDocument();
    await waitFor(()=>expect(monthlyAccountingClient.receivables).toHaveBeenLastCalledWith(null,'subsidy',true,expect.any(AbortSignal)));
    expect(screen.queryByLabelText('到期月份')).not.toBeInTheDocument();
  });
  it('keeps due progress available when a shared bank source cannot be split across the selected scope',async()=>{
    const data={...report(),cash_unavailable_reason:'mixed_accounting_bank_scope' as const,rows:report().rows.map(row=>({...row,cash_in_ntd:null,cash_out_ntd:null,bank_facts:[]}))};
    vi.mocked(monthlyAccountingClient.query).mockResolvedValue(data);
    render(<FinanceMonthlyAccounting initialRange={{start_month:'2026-09',end_month:'2026-10',category:'subsidy'}} onCase={vi.fn()}/>);
    expect(await screen.findByText('每月到期款進度')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab',{name:'已核銷收付款'}));
    expect(screen.getByRole('status')).toHaveTextContent('無法正確拆分已核銷收付款');
    expect(screen.getByRole('button',{name:'下載每月摘要 Excel'})).toBeDisabled();
    expect(screen.queryByText('已核銷入款')).not.toBeInTheDocument();
  });
  it('shows monthly rows, switches cash basis and expands individual bank sources',async()=>{
    render(<FinanceMonthlyAccounting initialRange={{start_month:'2026-09',end_month:'2026-10',category:'subsidy'}} onCase={vi.fn()}/>);
    expect(await screen.findByText('每月到期款進度')).toBeInTheDocument();
    expect(screen.getByText(/歷史人工核銷案件 1 案/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab',{name:'已核銷收付款'}));
    fireEvent.click(screen.getAllByRole('button',{name:'展開明細'})[1]);
    const details=screen.getByRole('region',{name:'2026-10明細'});
    expect(within(details).getByText('b1')).toBeInTheDocument();expect(within(details).getByText('b2')).toBeInTheDocument();
    expect(within(details).getAllByText('government')).toHaveLength(1);
    fireEvent.keyDown(screen.getByRole('tab',{name:'已核銷收付款'}),{key:'ArrowLeft'});
    expect(screen.getByRole('tab',{name:'到期款進度'})).toHaveAttribute('aria-selected','true');
  });
  it('hides old results for an invalid range and disables download when empty',async()=>{
    render(<FinanceMonthlyAccounting initialRange={{start_month:'2026-09',end_month:'2026-10',category:'subsidy'}} onCase={vi.fn()}/>);
    await screen.findByText('每月到期款進度');fireEvent.change(screen.getByLabelText('起始月份'),{target:{value:'2026-11'}});fireEvent.click(screen.getByRole('button',{name:'查詢'}));
    expect(screen.getByRole('alert')).toHaveTextContent('起始月份不可晚於');expect(screen.queryByText('每月到期款進度')).not.toBeInTheDocument();
    vi.mocked(monthlyAccountingClient.query).mockResolvedValue({...report(),rows:[]});
    fireEvent.change(screen.getByLabelText('結束月份'),{target:{value:'2026-12'}});fireEvent.click(screen.getByRole('button',{name:'查詢'}));
    expect(await screen.findByText('所選月份沒有資料，請調整月份或案件類別。')).toBeInTheDocument();expect(screen.getByRole('button',{name:'下載每月摘要 Excel'})).toBeDisabled();
  });
});

it('retains each monthly mode expansion across mode switches and refreshes',async()=>{
 const open=vi.fn(),range={start_month:'2026-09',end_month:'2026-10',category:'subsidy' as const};
 const view=render(<FinanceMonthlyAccounting initialRange={range} onCase={open}/>);
 await screen.findByText('每月到期款進度');
 fireEvent.click(screen.getAllByRole('button',{name:'展開明細'})[0]);
 fireEvent.click(within(screen.getByRole('region',{name:'2026-09明細'})).getByRole('button',{name:'處理案件'}));expect(open).toHaveBeenCalledWith('S1');
 fireEvent.click(screen.getByRole('tab',{name:'已核銷收付款'}));
 fireEvent.click(screen.getAllByRole('button',{name:'展開明細'})[1]);
 fireEvent.click(within(screen.getByRole('region',{name:'2026-10明細'})).getAllByRole('button',{name:'S1'})[0]);expect(open).toHaveBeenLastCalledWith('S1');
 fireEvent.click(screen.getByRole('tab',{name:'到期款進度'}));expect(screen.getByRole('region',{name:'2026-09明細'})).toBeInTheDocument();
 view.rerender(<FinanceMonthlyAccounting initialRange={range} onCase={open} revision={1}/>);
 await waitFor(()=>expect(monthlyAccountingClient.query).toHaveBeenCalledTimes(2));
 expect(screen.getByRole('region',{name:'2026-09明細'})).toBeInTheDocument();
 fireEvent.click(screen.getByRole('tab',{name:'已核銷收付款'}));expect(screen.getByRole('region',{name:'2026-10明細'})).toBeInTheDocument();
});
