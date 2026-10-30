import { fireEvent,render,screen,waitFor } from '@testing-library/react';
import { describe,it,expect,vi } from 'vitest';
import { FinanceWarningWorkspace } from '../../../../../../../components/FinanceWarningWorkspace';
import { LineManagementPage } from '../../../../../../../pages/LineManagementPage';

vi.mock('../../../../../../../components/LineNotificationWorkbench',()=>({LineNotificationWorkbench:({selectedEntryId,onSelectedEntryChange}:{selectedEntryId:string;onSelectedEntryChange:(id:string)=>void})=><section aria-label="原通知內容工作台"><p>{selectedEntryId}</p><button onClick={()=>onSelectedEntryChange('deposit-reminder')}>編輯訂金內容</button></section>}));
vi.mock('../../../../../../../components/FinanceCaseAccounting',()=>({FinanceAccountingWarnings:()=> <p>原有帳務警示</p>}));
vi.mock('../../../../../../../components/PaymentReminderSchedulePanel',()=>({PaymentReminderSchedulePanel:()=> <p>正式提醒排程設定</p>}));
vi.mock('../../../../../../../components/LineMessageFlow',()=>({LineMessageFlow:()=>null}));

describe('提醒內容搬移至帳務頁',()=>{
  it('原警示保留，同頁可切換提醒排程與既有內容工作台',()=>{
    window.history.replaceState(null,'','#finance?tab=accounting-warnings');
    render(<FinanceWarningWorkspace onCase={()=>{}}/>);
    expect(screen.getByText('原有帳務警示')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab',{name:'提醒排程'}));expect(screen.getByText('正式提醒排程設定')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab',{name:'提醒內容'}));expect(screen.getByRole('region',{name:'原通知內容工作台'})).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'編輯訂金內容'}));
    expect(window.location.hash).toContain('message=deposit-reminder');
  });
  it('既有通知編輯深連結移轉至同一則帳務內容',async()=>{
    window.history.replaceState(null,'','#line-management?tab=push_queue&message=payment-overdue-first');
    render(<LineManagementPage/>);
    await waitFor(()=>expect(window.location.hash).toContain('#finance?tab=accounting-warnings&view=reminder-content'));
    expect(window.location.hash).toContain('message=payment-overdue-first');
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
