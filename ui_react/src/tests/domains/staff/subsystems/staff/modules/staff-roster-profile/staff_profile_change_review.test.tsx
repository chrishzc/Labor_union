import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { StaffProfileChangeReview } from '../../../../../../../components/StaffProfileChangeReview';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('../../../../../../../api/shared/transport', () => ({ transport: { get, post } }));
vi.mock('../../../../../../../api/line_notifications/notification_tasks_client', () => ({
  notificationOptions: () => ({ token: 'test-session' }),
  notifyNotificationTasksChanged: vi.fn(),
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

it('requests the published receipt after approving a web photo and waits for confirmation', async () => {
  const file = 'cf_' + 'a'.repeat(32);
  const photo = {
    template_item_id: 2, template_version: 1, original_file_id: file,
    crop_file_id: null, expiry_date: '2027-03-01', entry_id: null, entry_version: null,
  };
  const pending = {
    id: 3, staff_id: 7, version: 1, status: 'pending', changes: { web_contents: [photo] },
  };
  const approved = { ...pending, version: 3, status: 'approved', changes: null };
  let lookup: { data: unknown } = { data: pending };
  get.mockImplementation(async path => {
    if (path.endsWith('/templates')) return { data: [{
      item_id: 2, version: 1, name: '健康檢查', category: 'other', display_order: 1,
      reminder_enabled: true, reminder_lead: { months: 1, days: 0 },
    }] };
    if (path.includes('/web-photos/')) return new Blob(['photo'], { type: 'image/png' });
    return lookup;
  });
  post.mockResolvedValueOnce({ data: approved });
  const url = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:review-photo');
  const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});

  const view = render(<StaffProfileChangeReview requestId={3} />);
  try {
    expect(await screen.findByRole('heading', { name: '健康檢查 · 第 1 張' })).toBeInTheDocument();
    expect(screen.getByText('到期日 2027-03-01')).toBeInTheDocument();
    lookup = { data: approved };
    fireEvent.click(screen.getByRole('button', { name: '核准整張申請並發布照片' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('尚未確認');
    expect(screen.queryByText('整張申請已核准，照片已發布', { exact: false })).not.toBeInTheDocument();

    const confirmed = { ...approved, publications: [{ entry_id: 9, version: 1, template_item_id: 2, file_id: file }] };
    lookup = { data: confirmed };
    fireEvent.click(screen.getByRole('button', { name: '重新讀取' }));
    await waitFor(() => expect(screen.getByText('整張申請已核准，照片已發布', { exact: false })).toBeInTheDocument());
  } finally {
    view.unmount();
    url.mockRestore();
    revoke.mockRestore();
  }
});
