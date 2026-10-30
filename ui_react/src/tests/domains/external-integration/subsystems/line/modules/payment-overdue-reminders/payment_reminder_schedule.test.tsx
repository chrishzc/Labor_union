import { fireEvent,render,screen,waitFor } from '@testing-library/react';
import { describe,it,expect,vi } from 'vitest';
import { PaymentReminderSchedulePanel,paymentReminderPreview } from '../../../../../../../components/PaymentReminderSchedulePanel';
import type { PaymentReminderScheduleClient,PaymentReminderSettings } from '../../../../../../../api/line_order_groups/payment_reminder_schedule_client';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';

const initial:PaymentReminderSettings={revision:2,timezone:'Asia/Taipei',followup_after_hours:24,followup_limit:1,
  schedule:{deposit_mode:'immediate',deposit_time:'09:00',first_time:'09:00',second_time:'09:00',overdue_time:'10:00'}};
function api():PaymentReminderScheduleClient{return {get:vi.fn().mockResolvedValue(structuredClone(initial)),save:vi.fn().mockImplementation(async body=>({...initial,revision:3,schedule:body.schedule}))};}

describe('帳務繳款提醒排程',()=>{
  it('讀取不儲存，調整時間後沿目前版本儲存',async()=>{
    const client=api();render(<PaymentReminderSchedulePanel client={client}/>);
    const field=await screen.findByLabelText('第一期寄送時間');
    expect(client.save).not.toHaveBeenCalled();expect(screen.getByRole('button',{name:'儲存提醒排程'})).toBeDisabled();
    fireEvent.change(field,{target:{value:'14:00'}});
    fireEvent.click(screen.getByRole('button',{name:'儲存提醒排程'}));
    await screen.findByText('提醒排程已儲存，新建的提醒會套用這組時間。');
    expect(client.save).toHaveBeenCalledExactlyOnceWith({expected_revision:2,idempotency_key:expect.any(String),schedule:{...initial.schedule,first_time:'14:00'}});
    expect(field).toHaveValue('14:00');expect(screen.getByRole('button',{name:'儲存提醒排程'})).toBeDisabled();
  });
  it.each(['message','button'])('任何客戶回覆 %s 都停止補寄，仍顯示未核銷待辦',async reply=>{
    render(<PaymentReminderSchedulePanel client={api()}/>);
    fireEvent.change(await screen.findByLabelText('模擬客戶狀態'),{target:{value:reply}});
    expect(screen.getByText('改由人員手動提醒')).toBeInTheDocument();
    expect(screen.getByText('未核銷款項保留待辦')).toBeInTheDocument();
    expect(screen.queryByText('預計自動補寄')).not.toBeInTheDocument();
  });
  it('排程衝突保留草稿，不顯示後端細節或自動覆寫',async()=>{
    const client=api();vi.mocked(client.save).mockRejectedValue(new ApiHttpError(409,'stale','private SQL detail',false));
    render(<PaymentReminderSchedulePanel client={client}/>);
    const field=await screen.findByLabelText('第一期寄送時間');fireEvent.change(field,{target:{value:'11:30'}});
    fireEvent.click(screen.getByRole('button',{name:'儲存提醒排程'}));
    await screen.findByRole('alert');expect(field).toHaveValue('11:30');expect(document.body).not.toHaveTextContent('private SQL');
    expect(client.save).toHaveBeenCalledTimes(1);
  });
  it('無效時間不送出，訂金可改為下一個固定時段',async()=>{
    const client=api();render(<PaymentReminderSchedulePanel client={client}/>);
    fireEvent.change(await screen.findByLabelText('訂金提醒時機'),{target:{value:'daily'}});
    expect(screen.getByLabelText('訂金寄送時間')).toBeEnabled();
    fireEvent.change(screen.getByLabelText('逾期補寄檢查時間'),{target:{value:''}});
    expect(screen.getByRole('button',{name:'儲存提醒排程'})).toBeDisabled();
    expect(client.save).not.toHaveBeenCalled();
  });
  it('儲存結果不明重試沿用同一操作識別',async()=>{
    const client=api();vi.mocked(client.save).mockRejectedValueOnce(new Error('network'));
    render(<PaymentReminderSchedulePanel client={client}/>);
    fireEvent.change(await screen.findByLabelText('第一期寄送時間'),{target:{value:'13:00'}});
    fireEvent.click(screen.getByRole('button',{name:'儲存提醒排程'}));await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button',{name:'儲存提醒排程'}));
    await waitFor(()=>expect(client.save).toHaveBeenCalledTimes(2));
    expect(vi.mocked(client.save).mock.calls[0][0]).toEqual(vi.mocked(client.save).mock.calls[1][0]);
  });
  it('試算不能在原提醒滿 24 小時前補寄，已錯過的固定時段順延',()=>{
    const result=paymentReminderPreview('2026-11-05','2026-11-05','14:00','10:00');
    expect(new Date(result.earliest).toISOString()).toBe('2026-11-06T14:00:00.000Z');
    expect(new Date(result.next).toISOString()).toBe('2026-11-07T10:00:00.000Z');
  });
});
