/**
 * File: finance_reminder_content_location.test.tsx
 * Description: 驗證帳務範本回到 LINE 通知與發送，以及原帳務深連結相容。
 */
import { fireEvent,render,screen,waitFor } from '@testing-library/react';
import { describe,it,expect,vi } from 'vitest';
import { FinanceWarningWorkspace } from '../../../../../../../components/FinanceWarningWorkspace';
import { LineManagementPage } from '../../../../../../../pages/LineManagementPage';

vi.mock('../../../../../../../components/LineNotificationWorkbench', () => ({
  LineNotificationWorkbench: ({ selectedEntryId }: { selectedEntryId: string }) => (
    <section aria-label="通知內容工作台"><p>{selectedEntryId}</p></section>
  ),
}));
vi.mock('../../../../../../../components/FinanceCaseAccounting',()=>({FinanceAccountingWarnings:()=> <p>原有帳務警示</p>}));
vi.mock('../../../../../../../components/PaymentReminderSchedulePanel',()=>({PaymentReminderSchedulePanel:()=> <p>正式提醒排程設定</p>}));
vi.mock('../../../../../../../components/PaymentOverdueReminderWorkbench',()=>({PaymentOverdueReminderWorkbench:()=> <p>正式逾期款項清單</p>}));
vi.mock('../../../../../../../components/LineMessageFlow',()=>({LineMessageFlow:()=>null}));

describe('帳務範本集中於通知與發送',()=>{
  it('舊逾期深連結保留實際逾期清單，新入口也能查閱',()=>{
    window.history.replaceState(null,'','#finance?tab=receipts&view=overdue');
    render(<FinanceWarningWorkspace onCase={()=>{}}/>);
    expect(screen.getByRole('tab',{name:'逾期款項'})).toHaveAttribute('aria-selected','true');
    expect(screen.getByText('正式逾期款項清單')).toBeInTheDocument();
  });
  it('原警示保留，同頁可切換排程',()=>{
    window.history.replaceState(null,'','#finance?tab=accounting-warnings');
    render(<FinanceWarningWorkspace onCase={()=>{}}/>);
    expect(screen.getByText('原有帳務警示')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab',{name:'提醒排程'}));expect(screen.getByText('正式提醒排程設定')).toBeInTheDocument();
    expect(screen.queryByRole('tab',{name:'提醒內容'})).not.toBeInTheDocument();
  });
  it('其他通知編輯入口仍在 LINE，不導向帳務',()=>{
    window.history.replaceState(null,'','#line-management?tab=push_queue&message=service-start-inquiry');
    render(<LineManagementPage scope="notifications"/>);
    expect(screen.getByRole('region',{name:'通知內容工作台'})).toHaveTextContent('service-start-inquiry');
    expect(window.location.hash).toBe('#line-notifications?tab=push_queue&message=service-start-inquiry');
    expect(screen.getByRole('button',{name:'通知與發送'})).toBeInTheDocument();
  });
  it('原帳務網址開啟 LINE 內同一則範本', async () => {
    window.history.replaceState(null, '', '#finance?tab=accounting-warnings&view=reminder-content&message=payment-overdue-first');
    render(<FinanceWarningWorkspace onCase={() => {}} />);
    await waitFor(() => expect(window.location.hash).toBe('#line-notifications?tab=push_queue&message=payment-overdue-first&category=accounting'));
  });
  it('LINE 帳務範本深連結在同一工作台開啟', () => {
    window.history.replaceState(null, '', '#line-notifications?tab=push_queue&message=payment-first-greeting');
    render(<LineManagementPage scope="notifications" />);
    expect(screen.getByRole('region', { name: '通知內容工作台' })).toHaveTextContent('payment-first-greeting');
    expect(window.location.hash).toContain('#line-notifications?');
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
