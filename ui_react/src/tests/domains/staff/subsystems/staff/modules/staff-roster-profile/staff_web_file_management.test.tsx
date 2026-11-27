import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { UPLOAD_TIMEOUT_MS } from '../../../../../../../api/shared/transport';
import { StaffWebFileManagement } from '../../../../../../../components/StaffWebFileManagement';

const { get, post, remove } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), remove: vi.fn() }));
vi.mock('../../../../../../../api/shared/transport', () => ({
  transport: { get, post, delete: remove },
  UPLOAD_TIMEOUT_MS: 120000,
}));
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

it.each(['', '/test'])('opens the staff website in the same tab with prefix "%s"', async prefix => {
  vi.stubEnv('VITE_PUBLIC_PATH_PREFIX', prefix);
  const assign = vi.spyOn(window.location, 'assign').mockImplementation(() => {});
  try {
    render(<StaffWebFileManagement staffId={7} staffName="測試月嫂" canWrite />);
    fireEvent.click(screen.getByRole('button', { name: '查看履歷網頁' }));
    expect(assign).toHaveBeenCalledWith(`${prefix}/line-staff-web-profile?staff_id=7&mode=admin`);
    await screen.findByRole('button', { name: '開啟資料夾 生活照' });
  } finally {
    assign.mockRestore();
    vi.unstubAllEnvs();
  }
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

it('shows customer feedback fourth and allows multiple photos without an expiry date', async () => {
  const certificate = { ...photo, template_item_id: 44, name: '專業證照', category: 'certificate' };
  const feedback = { ...photo, template_item_id: 45, name: '客戶反饋', category: 'feedback' };
  get.mockResolvedValueOnce({ data: { items: [feedback, other, certificate, photo] } });
  render(<StaffWebFileManagement staffId={7} staffName="測試月嫂" canWrite />);

  await screen.findByRole('button', { name: '開啟資料夾 客戶反饋' });
  expect(screen.getAllByRole('heading', { level: 4 }).map(heading => heading.textContent))
    .toEqual(['照片', '證照', '其他', '客戶反饋']);
  fireEvent.click(screen.getByRole('button', { name: '代傳照片' }));
  const dialog = await screen.findByRole('dialog', { name: '代傳照片' });
  fireEvent.change(within(dialog).getByLabelText('分類'), { target: { value: 'feedback' } });
  expect(within(dialog).queryByLabelText(/到期日/)).not.toBeInTheDocument();
  const picker = within(dialog).getByLabelText('選擇照片');
  expect(picker).toBeEnabled();
  expect(picker).toHaveAttribute('multiple');
  fireEvent.change(picker, { target: { files: [
    new File(['test'], 'feedback-one.jpeg', { type: 'image/jpeg' }),
    new File(['test'], 'feedback-two.jpeg', { type: 'image/jpeg' }),
  ] } });
  expect(within(dialog).getByText('已選 2 張')).toBeInTheDocument();
  expect(within(dialog).getByRole('button', { name: '確認發布' })).toBeEnabled();
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

it('uploads multi-photo batches with bounded concurrency, preserves order, and skips uploaded files on retry', async () => {
  render(<StaffWebFileManagement staffId={7} staffName="測試月嫂" canWrite />);
  fireEvent.click(await screen.findByRole('button', { name: '代傳照片' }));
  const dialog = await screen.findByRole('dialog', { name: '代傳照片' });
  const picker = within(dialog).getByLabelText('選擇照片');
  const selected = ['p1.jpg', 'p2.jpg', 'p3.jpg', 'p4.jpg'].map(name => new File(['img'], name, { type: 'image/jpeg' }));
  fireEvent.change(picker, { target: { files: selected } });
  expect(dialog.querySelector('img')).toBeNull();

  let inFlight = 0;
  let maxInFlight = 0;
  let failedOnce = false;
  const pendingUploads: { name: string; resolve: () => void; reject: (error: Error) => void }[] = [];
  post.mockImplementation((path: string, body: FormData | Record<string, unknown>, options: { timeoutMs?: number }) => {
    if (path.endsWith('/uploads')) {
      expect(options.timeoutMs).toBe(UPLOAD_TIMEOUT_MS);
      if (!(body instanceof FormData)) {
        throw new Error('Expected the upload body to be FormData');
      }
      const photo = body.get('photograph');
      if (!(photo instanceof File)) {
        throw new Error('Expected a photograph file in FormData');
      }
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      const id = `cf_${String(selected.findIndex(f => f.name === photo.name) + 1).repeat(32)}`;
      return new Promise((resolve, reject) => {
        pendingUploads.push({
          name: photo.name,
          resolve: () => {
            inFlight -= 1;
            resolve({ data: { file_id: id, filename: photo.name } });
          },
          reject: (error: Error) => {
            inFlight -= 1;
            reject(error);
          },
        });
      });
    }
    expect(options.timeoutMs).toBe(UPLOAD_TIMEOUT_MS);
    return Promise.resolve({ data: { files: [1, 2, 3, 4].map(n => ({ entry_id: n, entry_version: 1 })) } });
  });

  fireEvent.click(within(dialog).getByRole('button', { name: '確認發布' }));
  await waitFor(() => expect(pendingUploads).toHaveLength(3));
  expect(maxInFlight).toBe(3);
  if (!failedOnce) {
    failedOnce = true;
    pendingUploads.find(item => item.name === 'p3.jpg')!.reject(new Error('network glitch'));
  }
  await Promise.resolve();
  expect(within(dialog).queryByRole('alert')).not.toBeInTheDocument();

  pendingUploads.find(item => item.name === 'p1.jpg')!.resolve();
  pendingUploads.find(item => item.name === 'p2.jpg')!.resolve();
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('發布結果未確認');
  expect(inFlight).toBe(0);
  pendingUploads.length = 0;

  get.mockResolvedValueOnce({
    data: {
      items: [
        {
          ...photo,
          count: 4,
          files: [1, 2, 3, 4].map(n => ({ entry_id: n, entry_version: 1, filename: `p${n}.jpg`, expiry_date: null })),
        },
        other,
      ],
    },
  });
  fireEvent.click(within(dialog).getByRole('button', { name: '確認發布' }));
  await waitFor(() => expect(pendingUploads.length).toBeGreaterThanOrEqual(1));
  await waitFor(() => {
    while (pendingUploads.length > 0) {
      pendingUploads.shift()!.resolve();
    }
    expect(screen.queryByText('照片已發布。')).toBeInTheDocument();
  });

  const uploadCallsTotal = post.mock.calls.filter(([path]) => path.endsWith('/uploads'));
  expect(uploadCallsTotal).toHaveLength(5);
  expect(maxInFlight).toBe(3);
  const publicationCall = post.mock.calls.find(([path]) => path.endsWith('/publications'));
  expect((publicationCall?.[1] as { files: { file_id: string }[] }).files.map(row => row.file_id)).toEqual([
    `cf_${'1'.repeat(32)}`,
    `cf_${'2'.repeat(32)}`,
    `cf_${'3'.repeat(32)}`,
    `cf_${'4'.repeat(32)}`,
  ]);
});
