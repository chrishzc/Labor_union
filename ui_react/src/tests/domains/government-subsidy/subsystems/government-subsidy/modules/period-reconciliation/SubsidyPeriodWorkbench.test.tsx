import { cleanup,fireEvent,render,screen,waitFor,within } from '@testing-library/react';
import { UnsavedChangesProvider } from '../../../../../../../components/UnsavedChanges';
import { afterEach,beforeEach,describe,expect,it,vi } from 'vitest';
import { SubsidyPeriodWorkbench } from '../../../../../../../components/SubsidyPeriodWorkbench';
import { subsidyPeriodClient,type SubsidyPeriod,type SubsidyPeriodView } from '../../../../../../../api/government_subsidy/period_reconciliation_client';
vi.mock('../../../../../../../api/government_subsidy/period_reconciliation_client',()=>({subsidyPeriodClient:{query:vi.fn(),bankRows:vi.fn(),reconcile:vi.fn(),reverse:vi.fn()}}));

function view(period:SubsidyPeriod):SubsidyPeriodView {
  return {period,version:3,label:'測試期間',lines:[{case_no:'CASE-1',service_end_date:`${period.year}-01-20`,amount_ntd:6000,unavailable_reason:null}],
    total_ntd:6000,coverage:[],blocked_cases:[],recorded_lines:[],changed_cases:[],can_reconcile:true};
}
beforeEach(()=>{
  vi.mocked(subsidyPeriodClient.query).mockImplementation(async period=>view(period));
  vi.mocked(subsidyPeriodClient.bankRows).mockResolvedValue([{id:1,paid_on:'2026-06-01',amount_ntd:5999},{id:2,paid_on:'2026-06-01',amount_ntd:6000}]);
  vi.mocked(subsidyPeriodClient.reconcile).mockResolvedValue({receipt_id:1});
});
afterEach(()=>{cleanup();vi.resetAllMocks();});
async function loaded(){await screen.findByText('本期補助總額',{exact:false});}

describe('whole-period subsidy workbench',()=>{
  it('saves the original selected period before applying a newly typed year',async()=>{
    render(<UnsavedChangesProvider><SubsidyPeriodWorkbench onOpenCase={()=>{}}/></UnsavedChangesProvider>);await loaded();
    const originalYear=new Date().getFullYear();
    fireEvent.change(screen.getByLabelText('政府銀行款項'),{target:{value:'2'}});
    fireEvent.change(screen.getByLabelText('年度'),{target:{value:'203'}});
    fireEvent.change(screen.getByLabelText('年度'),{target:{value:'2031'}});
    const dialog=await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button',{name:'儲存變更並離開'}));
    await waitFor(()=>expect(vi.mocked(subsidyPeriodClient.query).mock.lastCall?.[0].year).toBe(2031));
    expect(vi.mocked(subsidyPeriodClient.reconcile).mock.calls[0][0].period.year).toBe(originalYear);
    expect(subsidyPeriodClient.reconcile).toHaveBeenCalledTimes(1);
  });
  it('shows invalid scheduling as unknown and blocks receipt without claiming a bank amount mismatch',async()=>{
    vi.mocked(subsidyPeriodClient.query).mockImplementation(async period=>({...view(period),total_ntd:null,can_reconcile:false,
      lines:[{case_no:'CASE-1',service_end_date:'2026-01-20',amount_ntd:null,unavailable_reason:'scheduling_effective_generation_invalid'}]}));
    render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();
    expect(screen.getByText('排班資料待確認')).toBeVisible();
    fireEvent.change(screen.getByLabelText('政府銀行款項'),{target:{value:'2'}});
    expect(screen.getByRole('button',{name:'核銷本期入款'})).toBeDisabled();
    expect(screen.queryByText('銀行金額與所選期間總額不一致，不能核銷。')).toBeNull();
    expect(subsidyPeriodClient.reconcile).not.toHaveBeenCalled();
  });
  it('allows a year to be typed digit by digit and prevents saving an incomplete year',async()=>{
    render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();
    fireEvent.change(screen.getByLabelText('政府銀行款項'),{target:{value:'2'}});
    fireEvent.change(screen.getByLabelText('年度'),{target:{value:'2'}});
    expect(screen.getByLabelText('年度')).toHaveValue(2);
    expect(screen.getByRole('button',{name:'核銷本期入款'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('年度'),{target:{value:'2031'}});await loaded();
    expect(vi.mocked(subsidyPeriodClient.query).mock.lastCall?.[0].year).toBe(2031);
  });
  it('selects month,quarter,year through one source and never exposes claim approval actions',async()=>{
    render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();
    expect(screen.queryByRole('button',{name:'送件'})).toBeNull();
    fireEvent.change(screen.getByLabelText('彙總單位'),{target:{value:'month'}});await loaded();
    expect(vi.mocked(subsidyPeriodClient.query).mock.lastCall?.[0].unit).toBe('month');
    fireEvent.change(screen.getByLabelText('月份'),{target:{value:'2'}});await loaded();
    expect(vi.mocked(subsidyPeriodClient.query).mock.lastCall?.[0].index).toBe(2);
    fireEvent.change(screen.getByLabelText('彙總單位'),{target:{value:'year'}});await loaded();
    expect(vi.mocked(subsidyPeriodClient.query).mock.lastCall?.[0]).toEqual({unit:'year',year:new Date().getFullYear(),index:1});
  });
  it('blocks mismatched bank amount and sends only the selected whole period',async()=>{
    render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();
    const button=screen.getByRole('button',{name:'核銷本期入款'});
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByLabelText('政府銀行款項'),{target:{value:'1'}});
    expect(button).toBeDisabled();expect(screen.getByRole('alert')).toHaveTextContent('金額與所選期間總額不一致');
    fireEvent.change(screen.getByLabelText('政府銀行款項'),{target:{value:'2'}});fireEvent.click(button);
    await waitFor(()=>expect(subsidyPeriodClient.reconcile).toHaveBeenCalledTimes(1));
    expect(vi.mocked(subsidyPeriodClient.reconcile).mock.calls[0][1]).toBe(2);
    expect(vi.mocked(subsidyPeriodClient.reconcile).mock.calls[0][0].period.unit).toBe('quarter');
    await screen.findByText('整期入款已核銷，代墊回收已同步記錄。');
  });
  it('displays covering quarter without inventing month cash and blocks another receipt',async()=>{
    vi.mocked(subsidyPeriodClient.query).mockImplementation(async period=>({...view(period),can_reconcile:false,
      coverage:[{receipt_id:9,period:{unit:'quarter',year:2026,index:1},label:'2026 年 第 1 季',amount_ntd:18000,recovered_advance_ntd:6000}]}));
    render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();
    expect(screen.getByText(/本期已由「2026 年 第 1 季」核銷涵蓋/)).toHaveTextContent('18,000');
    fireEvent.change(screen.getByLabelText('政府銀行款項'),{target:{value:'2'}});
    expect(screen.getByRole('button',{name:'核銷本期入款'})).toBeDisabled();
  });
  it('reuses the command key when a network failure leaves the save result unknown',async()=>{
    vi.mocked(subsidyPeriodClient.reconcile).mockRejectedValueOnce(new Error('network'));
    render(<SubsidyPeriodWorkbench onOpenCase={()=>{}}/>);await loaded();
    fireEvent.change(screen.getByLabelText('政府銀行款項'),{target:{value:'2'}});
    fireEvent.click(screen.getByRole('button',{name:'核銷本期入款'}));
    await screen.findByText('尚未確認儲存結果，請用相同選擇重試。');
    fireEvent.click(screen.getByRole('button',{name:'核銷本期入款'}));
    await waitFor(()=>expect(subsidyPeriodClient.reconcile).toHaveBeenCalledTimes(2));
    const calls=vi.mocked(subsidyPeriodClient.reconcile).mock.calls;
    expect(calls[0][2]).toBe(calls[1][2]);
  });
});
