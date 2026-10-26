import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ServiceDayLogReminderWorkbench } from '../../../../../../../components/ServiceDayLogReminderWorkbench';
import type { ServiceDayLogReminderClient } from '../../../../../../../api/line_order_groups/service_day_log_reminder_client';
import { adaptLineNotificationRulesCatalog } from '../../../../../../../adapters/line_configuration/line_configuration_query_adapter';

const item={case_no:'CASE-1',staff_id:1,missing_from:'2032-05-04',missing_through:'2032-05-07',
  consecutive_days:4,group_label:'案件 CASE-1 群組',can_send:true};
function client():ServiceDayLogReminderClient {return {
  list:vi.fn().mockResolvedValue({items:[item],total:1,page:1,page_size:25}),
  send:vi.fn().mockResolvedValue({task_id:88,status:'pending'}),
};}
describe('服務日誌人工提醒',()=>{
  it('hides the retired automatic private rule even in an older active configuration',()=>{
    const model=adaptLineNotificationRulesCatalog({revision:5,definition:{rules:[{
      id:'LINE-SERVICE-DAY-LOG-REMINDER-RULE-V1',event_code:'service_time_checkpoint',recipient_selector:'assigned_caregiver',
      template_id:'LINE-SERVICE-DAY-LOG-REMINDER-TEXT-V1',enabled:true,schedule:{kind:'service_end'},
      frequency:{kind:'once'},predicates:['baby_log_missing'],
    }]}});
    expect(model.rules).toEqual([]);expect(model.isEmpty).toBe(true);
  });
  it('shows case group and consecutive count; viewing never sends',async()=>{
    const api=client();render(<ServiceDayLogReminderWorkbench client={api}/>);
    await screen.findByText('案件 CASE-1 群組');
    expect(screen.getByText('連續 4 日')).toBeInTheDocument();
    expect(api.send).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'發送提醒'}));
    await screen.findByText('已建立案件群組提醒寄送工作。');
    expect(api.send).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button',{name:'已建立寄送工作'})).toBeDisabled();
  });
  it('keeps the same operation key after uncertain send failure',async()=>{
    const api=client();vi.mocked(api.send).mockRejectedValueOnce(new Error('連線中斷')).mockResolvedValueOnce({task_id:88,status:'pending'});
    render(<ServiceDayLogReminderWorkbench client={api}/>);
    fireEvent.click(await screen.findByRole('button',{name:'發送提醒'}));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button',{name:'發送提醒'}));
    await screen.findByText('已建立案件群組提醒寄送工作。');
    expect(vi.mocked(api.send).mock.calls[0][1]).toBe(vi.mocked(api.send).mock.calls[1][1]);
  });
  it('retains internal reminder without a usable case group',async()=>{
    const api=client();vi.mocked(api.list).mockResolvedValue({items:[{...item,can_send:false}],total:1,page:1,page_size:25});
    render(<ServiceDayLogReminderWorkbench client={api}/>);
    await screen.findByText('尚無可用案件群組');
    expect(screen.getByRole('button',{name:'發送提醒'})).toBeDisabled();
    expect(api.send).not.toHaveBeenCalled();
  });
  it('refresh reflects diary completion without creating tasks',async()=>{
    const api=client();render(<ServiceDayLogReminderWorkbench client={api}/>);
    await screen.findByText('案件 CASE-1 群組');
    vi.mocked(api.list).mockResolvedValue({items:[],total:0,page:1,page_size:25});
    fireEvent.click(screen.getByRole('button',{name:'重新整理日誌提醒'}));
    await screen.findByText('目前沒有連續超過 3 日未填的服務日誌。');
    await waitFor(()=>expect(api.list).toHaveBeenCalledTimes(2));
    expect(api.send).not.toHaveBeenCalled();
  });
});
