import { fireEvent,render,screen,waitFor } from '@testing-library/react';
import { describe,it,expect,vi } from 'vitest';
import { FinanceWarningWorkspace } from '../../../../../../../components/FinanceWarningWorkspace';
import { LineManagementPage } from '../../../../../../../pages/LineManagementPage';

vi.mock('../../../../../../../components/LineNotificationWorkbench',()=>({PAYMENT_REMINDER_MESSAGE_IDS:['deposit-reminder','payment-first-reminder','payment-first-greeting','payment-second-reminder','payment-overdue-deposit','payment-overdue-first','payment-overdue-second','deposit-settled'],LineNotificationWorkbench:({scope,selectedEntryId,onSelectedEntryChange}:{scope?:string;selectedEntryId:string;onSelectedEntryChange:(id:string)=>void})=><section aria-label={scope==='payment-reminders'?'繳款提醒編輯':'原通知內容工作台'}><p>{selectedEntryId}</p><button onClick={()=>onSelectedEntryChange('payment-overdue-first')}>編輯第一期逾期內容</button></section>}));
vi.mock('../../../../../../../components/FinanceCaseAccounting',()=>({FinanceAccountingWarnings:()=> <p>原有帳務警示</p>}));
vi.mock('../../../../../../../components/PaymentReminderSchedulePanel',()=>({PaymentReminderSchedulePanel:()=> <p>正式提醒排程設定</p>}));
vi.mock('../../../../../../../components/LineMessageFlow',()=>({LineMessageFlow:()=>null}));

describe('提醒內容搬移至帳務頁',()=>{
  it('原警示保留，同頁可切換排程與繳款提醒內容',()=>{
    window.history.replaceState(null,'','#finance?tab=accounting-warnings');
    render(<FinanceWarningWorkspace onCase={()=>{}}/>);
    expect(screen.getByText('原有帳務警示')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab',{name:'提醒排程'}));expect(screen.getByText('正式提醒排程設定')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab',{name:'提醒內容'}));expect(screen.getByRole('region',{name:'繳款提醒編輯'})).toBeInTheDocument();
    expect(screen.queryByRole('region',{name:'原通知內容工作台'})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'編輯第一期逾期內容'}));
    expect(window.location.hash).toContain('message=payment-overdue-first');
  });
  it('其他通知編輯入口仍在 LINE，不導向帳務',()=>{
    window.history.replaceState(null,'','#line-management?tab=push_queue&message=service-start-inquiry');
    render(<LineManagementPage/>);
    expect(screen.getByRole('region',{name:'原通知內容工作台'})).toBeInTheDocument();
    expect(window.location.hash).toContain('#line-management?');
    expect(window.location.hash).toContain('message=service-start-inquiry');
    expect(screen.getByRole('button',{name:'通知與發送'})).toBeInTheDocument();
  });
  it.each(['deposit-reminder','payment-first-reminder','payment-first-greeting','payment-second-reminder','payment-overdue-deposit','payment-overdue-first','payment-overdue-second','deposit-settled'])('繳款提醒 %s 深連結移轉至同一則帳務內容',async(id)=>{
    window.history.replaceState(null,'','#line-management?tab=push_queue&message='+id);
    render(<LineManagementPage/>);
    await waitFor(()=>expect(window.location.hash).toContain('#finance?tab=accounting-warnings&view=reminder-content'));
    expect(window.location.hash).toContain('message='+id);
    expect(screen.queryByRole('region',{name:'原通知內容工作台'})).not.toBeInTheDocument();
  });
  it('方向鍵切換功能並將焦點保留在對應頁籤',()=>{
    window.history.replaceState(null,'','#finance?tab=accounting-warnings');
    render(<FinanceWarningWorkspace onCase={()=>{}}/>);
    fireEvent.keyDown(screen.getByRole('tab',{name:'待處理警示'}),{key:'ArrowRight'});
    const tab=screen.getByRole('tab',{name:'提醒排程'});
    expect(tab).toHaveFocus();expect(tab).toHaveAttribute('aria-selected','true');
    expect(document.getElementById(tab.getAttribute('aria-controls')!)).toBeVisible();
  });
});
