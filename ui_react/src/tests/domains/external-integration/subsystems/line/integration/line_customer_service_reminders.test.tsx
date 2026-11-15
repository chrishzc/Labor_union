/** Historical customer-service records remain read-only after retirement. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LineCustomerServiceReminderWorkbench } from '../../../../../../components/LineCustomerServiceReminderWorkbench';
import { LineManagementPage } from '../../../../../../pages/LineManagementPage';
import type { CustomerServiceDetail, CustomerServicePage } from '../../../../../../api/customer_service/customer_service_schemas';

const detail: CustomerServiceDetail = {
  ticket: { ticket_id: 31, line_user_id: 'U_SYNTHETIC', case_no: 'DEMO-018', category: 'other', status: 'resolved', version: 2, created_at: '2026-10-15T01:00:00Z' },
  events: [{ id: 1, actor_id: 'fixture', event_type: 'customer_message', message_text: '歷史留言', created_at: '2026-10-15T01:00:00Z' }],
};
const page: CustomerServicePage = { items: [detail.ticket], total: 1, page: 1, page_size: 25 };

afterEach(() => { vi.restoreAllMocks(); window.history.replaceState(null, '', '/'); });

describe('歷史客服紀錄', () => {
  it('舊工作入口僅能按需查閱歷史，無提醒、接手、回覆及結案控制', async () => {
    window.location.hash = '#line-management?tab=tickets';
    const listTickets = vi.fn().mockResolvedValue(page);
    const getTicketDetail = vi.fn().mockResolvedValue(detail);
    render(<LineManagementPage customerService={{ listTickets, getTicketDetail }} />);
    const history = await screen.findByRole('region', { name: '歷史客服紀錄' });
    const ticket = await within(history).findByRole('button', { name: '#31' });
    expect(listTickets).toHaveBeenCalledWith({ status: 'resolved', page: 1, page_size: 25 }, expect.any(Object));
    expect(getTicketDetail).not.toHaveBeenCalled();
    fireEvent.click(ticket);
    expect(await within(history).findByText('歷史留言')).toBeInTheDocument();
    expect(getTicketDetail).toHaveBeenCalledWith(31, expect.any(Object));
    expect(within(history).queryByRole('button', { name: /接手|回覆|結案/ })).not.toBeInTheDocument();
    expect(within(history).queryByText('U_SYNTHETIC')).not.toBeInTheDocument();
  });

  it('切換篩選時取消先前查詢，晚到的結果不覆蓋新結果', async () => {
    let finish!: (value: CustomerServicePage) => void;
    const listTickets = vi.fn().mockReturnValueOnce(new Promise(resolve => { finish = resolve; }))
      .mockResolvedValue({ ...page, items: [{ ...detail.ticket, ticket_id: 32, status: 'waiting' }] });
    render(<LineCustomerServiceReminderWorkbench client={{ listTickets }} />);
    await waitFor(() => expect(listTickets).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByRole('combobox', { name: '原工單狀態' }), { target: { value: 'waiting' } });
    await screen.findByRole('button', { name: '#32' });
    finish(page);
    expect(screen.queryByRole('button', { name: '#31' })).not.toBeInTheDocument();
  });
});
