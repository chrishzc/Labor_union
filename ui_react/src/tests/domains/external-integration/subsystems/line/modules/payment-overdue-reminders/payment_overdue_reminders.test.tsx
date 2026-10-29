import { fireEvent,render,screen,within,waitFor } from '@testing-library/react';
import { describe,it,expect,vi } from 'vitest';
import { PaymentOverdueReminderWorkbench } from '../../../../../../../components/PaymentOverdueReminderWorkbench';
import type { PaymentOverdueReminderClient,PaymentOverdueTodo } from '../../../../../../../api/line_order_groups/payment_overdue_reminder_client';
import { FinanceReceiptsWorkspace } from '../../../../../../../components/FinanceReceiptsWorkspace';
import { LineManagementPage } from '../../../../../../../pages/LineManagementPage';
import { paymentOverdueReminderClient } from '../../../../../../../api/line_order_groups/payment_overdue_reminder_client';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';

const item=(stage:'deposit'|'first'|'second',amount:number):PaymentOverdueTodo=>({payment:{case_no:'CASE-1',payment_stage:stage,
  obligation_identity:'CASE-1:'+stage,projection_version:3,obligation_event_id:7,due_date:'2032-05-10',remaining_amount_ntd:amount},
  overdue_days:1,recipient_label:stage==='deposit'?'客戶私人聊天室':'案件 CASE-1 群組',can_send:true,unavailable_reason:null,last_reminder:null});
function client(items=[item('deposit',18000),item('first',42000),item('second',60000)]):PaymentOverdueReminderClient {
  return {list:vi.fn().mockResolvedValue({items,total:items.length,page:1,page_size:25}),send:vi.fn().mockResolvedValue({task_id:8,status:'pending'})};
}

describe('各期繳款逾期待辦',()=>{
  it('分期列出金額及收件位置，查詢不發送，點擊只傳所選期別',async()=>{
    const api=client();render(<PaymentOverdueReminderWorkbench client={api}/>);
    const first=await screen.findByRole('cell',{name:/第一期款/});
    const row=first.closest('tr')!;
    expect(within(row).getByText('NT$ 42,000')).toBeInTheDocument();
    expect(within(row).getByText('案件 CASE-1 群組')).toBeInTheDocument();
    expect(screen.getByText('客戶私人聊天室')).toBeInTheDocument();expect(api.send).not.toHaveBeenCalled();
    vi.mocked(api.list).mockResolvedValue({items:[{...item('first',42000),last_reminder:{requested_at:'2032-05-10T16:00:00Z',status:'pending'}}],total:1,page:1,page_size:25});
    fireEvent.click(within(row).getByRole('button',{name:'發送提醒'}));
    await screen.findByText('CASE-1 第一期款提醒已建立寄送工作；待辦會保留至核銷清償。');
    expect(api.send).toHaveBeenCalledExactlyOnceWith(item('first',42000),expect.any(String));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(await screen.findByRole('button',{name:'已建立寄送工作'})).toBeDisabled();
    expect(screen.getByRole('link',{name:'核對銀行入款'})).toHaveAttribute('href','#finance?tab=finance-import&case_no=CASE-1');
  });
  it('缺少對象保留待辦並禁用提醒，不替換收件位置',async()=>{
    const api=client([{...item('deposit',18000),can_send:false,unavailable_reason:'尚未綁定客戶 LINE'},
      {...item('second',60000),can_send:false,unavailable_reason:'尚無可用案件群組'}]);
    render(<PaymentOverdueReminderWorkbench client={api}/>);
    await screen.findByText('尚未綁定客戶 LINE');await screen.findByText('尚無可用案件群組');
    for(const button of screen.getAllByRole('button',{name:'發送提醒'}))expect(button).toBeDisabled();
    expect(api.send).not.toHaveBeenCalled();
  });
  it('連線結果不明保留同一操作鍵，避免重複建立',async()=>{
    const api=client([item('deposit',18000)]);vi.mocked(api.send).mockRejectedValueOnce(new Error('synthetic network failure'));
    render(<PaymentOverdueReminderWorkbench client={api}/>);
    fireEvent.click(await screen.findByRole('button',{name:'發送提醒'}));await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button',{name:'確認原操作結果'}));
    await waitFor(()=>expect(api.send).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.send).mock.calls[0][1]).toBe(vi.mocked(api.send).mock.calls[1][1]);
    expect(document.body).not.toHaveTextContent('synthetic network');
  });
  it('金額已變更回衝突後重查，不自動發送新金額',async()=>{
    const api=client([item('first',42000)]);
    vi.mocked(api.send).mockRejectedValueOnce(new ApiHttpError(409,'changed','private SQL detail',false));
    render(<PaymentOverdueReminderWorkbench client={api}/>);
    const button=await screen.findByRole('button',{name:'發送提醒'});
    vi.mocked(api.list).mockResolvedValue({items:[],total:0,page:1,page_size:25});fireEvent.click(button);
    await screen.findByText('目前沒有符合提醒資格的逾期款。');expect(api.send).toHaveBeenCalledTimes(1);
    expect(document.body).not.toHaveTextContent('private SQL');
  });
  it('查詢失敗不當成零筆成功，也不發送',async()=>{
    const api=client();vi.mocked(api.list).mockRejectedValueOnce(new Error('raw database'));
    render(<PaymentOverdueReminderWorkbench client={api}/>);await screen.findByRole('alert');
    expect(screen.queryByText('目前沒有符合提醒資格的逾期款。')).not.toBeInTheDocument();expect(api.send).not.toHaveBeenCalled();
  });
  it('帳務收款直接承接逾期提醒，舊 LINE 連結導向新位置',async()=>{
    const api=client([item('deposit',18000)]);
    const spy=vi.spyOn(paymentOverdueReminderClient,'list').mockImplementation(api.list);
    window.history.replaceState(null,'','#finance?tab=receipts&view=overdue');
    const view=render(<FinanceReceiptsWorkspace revision={0} initialView="overdue" onOpenCase={()=>{}} onOpenSubsidy={()=>{}}/>);
    expect(await screen.findByRole('heading',{name:'逾期提醒'})).toBeInTheDocument();
    expect(screen.getByRole('button',{name:'逾期提醒'})).toHaveAttribute('aria-pressed','true');
    await screen.findByText('客戶私人聊天室');view.unmount();
    window.history.replaceState(null,'','#line-management?tab=payment_overdue');
    render(<LineManagementPage/>);
    await waitFor(()=>expect(window.location.hash).toBe('#finance?tab=receipts&view=overdue'));
    expect(screen.queryByRole('button',{name:'繳款逾期'})).not.toBeInTheDocument();spy.mockRestore();window.history.replaceState(null,'','/');
  });
});
