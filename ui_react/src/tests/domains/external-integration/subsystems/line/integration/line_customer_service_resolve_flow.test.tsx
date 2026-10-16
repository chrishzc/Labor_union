/** Desktop reminder retirement guard; legacy mobile/API commands remain independent. */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { LineManagementPage } from '../../../../../../pages/LineManagementPage';
import { CUSTOMER_SERVICE_REMINDER_PAGE_FIXTURE } from './fixtures/customer_service_reminder_fixtures';

it('點選客服提醒內容不開操作頁，也不執行舊回覆或結案流程', async () => {
  const client = {
    listReminders: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_REMINDER_PAGE_FIXTURE),
    getTicketDetail: vi.fn(), previewResolve: vi.fn(), applyResolve: vi.fn(),
    previewReply: vi.fn(), applyReply: vi.fn(),
  };
  render(<LineManagementPage customerService={client} />);
  fireEvent.click(await screen.findByText('測試客戶'));
  const workspace = screen.getByRole('region', { name: '客服案件提醒' });
  expect(within(workspace).queryByRole('textbox', { name: /回覆|備註|結案/ })).not.toBeInTheDocument();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  for (const action of [client.getTicketDetail, client.previewResolve, client.applyResolve, client.previewReply, client.applyReply]) expect(action).not.toHaveBeenCalled();
});
