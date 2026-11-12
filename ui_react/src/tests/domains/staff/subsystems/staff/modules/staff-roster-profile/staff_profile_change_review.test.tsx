import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { StaffProfileChangeReview } from '../../../../../../../components/StaffProfileChangeReview';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('../../../../../../../api/shared/transport', () => ({ transport: { get, post } }));
vi.mock('../../../../../../../api/line_notifications/notification_tasks_client', () => ({
  notificationOptions: () => ({ token: 'test-session' }),
}));

it('requires a fresh read after an approval error and hides actions on a terminal conflict', async () => {
  get.mockResolvedValueOnce({ data: {
    id: 3, staff_id: 7, version: 1, status: 'pending',
    changes: { bank: { before: { account_last4: '0001' }, after: { account_last4: '0002' } } },
  } }).mockResolvedValueOnce({ data: {
    id: 3, staff_id: 7, version: 3, status: 'conflict', changes: null,
  } });
  post.mockRejectedValueOnce(new Error('資料或申請已更新，請重新讀取。'));

  render(<StaffProfileChangeReview requestId={3} />);
  expect(await screen.findByText('0002')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '核准整張申請' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('請重新讀取');
  expect(screen.getByRole('button', { name: '核准整張申請' })).toBeDisabled();
  expect(screen.getByRole('button', { name: '退回整張申請' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: '重新讀取' }));
  expect(await screen.findByText(/正式資料已變更/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '核准整張申請' })).not.toBeInTheDocument();
  expect(screen.getByRole('link', { name: '返回通知事項' })).toHaveAttribute('href', '#notifications');
});
