import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { StaffWebFileManagement } from '../../../../../../../components/StaffWebFileManagement';

const { get, post, remove } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), remove: vi.fn() }));
vi.mock('../../../../../../../api/shared/transport', () => ({ transport: { get, post, delete: remove } }));
vi.mock('../../../../../../../api/line_notifications/notification_tasks_client', () => ({
  notificationOptions: () => ({ token: 'test-session' }),
}));

const staffPath = '/api/v1/admin/staff-web-profile/7';
const entry = { entry_id: 19, entry_version: 4, filename: 'IMG_0181.jpg', expiry_date: '2026-10-01' };
const other = { template_item_id: 42, template_version: 2, name: '健康檢查', category: 'other', count: 1, files: [entry] };
const photo = { template_item_id: 43, template_version: 1, name: '生活照', category: 'photo', count: 0, files: [] };

beforeEach(() => {
  vi.resetAllMocks();
  get.mockResolvedValue({ data: { items: [photo, other] } });
});

it('shows metadata and an empty folder and removes only the confirmed entry', async () => {
  const view = render(<StaffWebFileManagement staffId={7} staffName="測試月嫂" canWrite />);
  await screen.findByRole('button', { name: '開啟資料夾 生活照' });
  expect(screen.getByText('0 張')).toBeInTheDocument();
  expect(screen.getByText('2026-10-01')).toBeInTheDocument();
  expect(view.container.querySelector('img')).toBeNull();
  expect(get.mock.calls.map(([path]) => path)).toEqual([`${staffPath}/folders`]);

  fireEvent.click(screen.getByRole('button', { name: '開啟資料夾 健康檢查' }));
  const folder = await screen.findByRole('dialog', { name: '健康檢查' });
  expect(within(folder).getByText('IMG_0181.jpg')).toBeInTheDocument();
  expect(folder.querySelector('img')).toBeNull();
  expect(get).toHaveBeenCalledTimes(1);
  const removeButton = within(folder).getByRole('button', { name: '刪除照片 IMG_0181.jpg' });
  fireEvent.click(removeButton);
  fireEvent.click(within(folder).getByRole('button', { name: '取消刪除' }));
  expect(remove).not.toHaveBeenCalled();
  fireEvent.click(removeButton);
  remove.mockResolvedValue({ data: { entry_id: entry.entry_id } });
  get.mockResolvedValueOnce({ data: { items: [photo, { ...other, count: 0, files: [] }] } });
  fireEvent.click(within(folder).getByRole('button', { name: '確認刪除' }));
  expect(await within(folder).findByText('資料夾內沒有已發布照片。')).toBeInTheDocument();
  expect(remove).toHaveBeenCalledWith(`${staffPath}/folders/42/entries/19`,
    expect.objectContaining({ params: { template_version: 2, entry_version: 4 } }));
});

it('uses the selected Other folder version and displays no image while choosing files', async () => {
  render(<StaffWebFileManagement staffId={7} staffName="測試月嫂" canWrite />);
  const open = await screen.findByRole('button', { name: '代傳照片' });
  await waitFor(() => expect(open).toBeEnabled());
  fireEvent.click(open);
  const dialog = await screen.findByRole('dialog', { name: '代傳照片' });
  fireEvent.change(within(dialog).getByLabelText('分類'), { target: { value: 'other' } });
  const picker = within(dialog).getByLabelText('選擇照片');
  expect(picker).toHaveAttribute('accept', 'image/jpeg,image/png,image/webp');
  expect(picker).not.toHaveAttribute('multiple');
  fireEvent.change(picker, { target: { files: [new File(['test'], 'phone.jpeg', { type: 'image/jpeg' })] } });
  expect(within(dialog).getByText('phone.jpeg')).toBeInTheDocument();
  expect(within(dialog).getByText('已選 1 張')).toBeInTheDocument();
  expect(dialog.querySelector('img')).toBeNull();
  expect(post).not.toHaveBeenCalled();
  fireEvent.change(within(dialog).getByLabelText('到期日（必填）'), { target: { value: '2027-04-15' } });
  const fileId = 'cf_' + 'f'.repeat(32);
  post.mockResolvedValueOnce({ data: { file_id: fileId, filename: 'phone.jpeg' } });
  post.mockResolvedValueOnce({ data: { files: [{ entry_id: 19, entry_version: 5 }] } });
  get.mockResolvedValueOnce({ data: { items: [photo, {
    ...other, files: [{ ...entry, entry_version: 5, filename: 'phone.jpeg', expiry_date: '2027-04-15' }],
  }] } });
  fireEvent.click(within(dialog).getByRole('button', { name: '確認發布' }));
  expect(await screen.findByText('照片已發布。')).toBeInTheDocument();
  expect(post).toHaveBeenNthCalledWith(2, `${staffPath}/publications`, expect.objectContaining({
    template_item_id: 42,
    template_version: 2,
    files: [{ file_id: fileId, expiry_date: '2027-04-15' }],
    expected_current: { entry_id: 19, entry_version: 4 },
  }), expect.anything());
});
