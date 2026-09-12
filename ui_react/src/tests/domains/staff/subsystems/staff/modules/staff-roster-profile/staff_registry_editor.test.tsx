import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { StaffRegistryEditor } from '../../../../../../../components/StaffRegistryEditor';
import { STAFF_PROFILE } from './fixtures/staff_profile_contract_fixtures';

const mocks = vi.hoisted(() => ({
  previewProfile: vi.fn(), applyProfile: vi.fn(), previewBank: vi.fn(), applyBank: vi.fn(),
  currentResume: vi.fn(), uploadResume: vi.fn(), downloadResume: vi.fn(),
}));
vi.mock('../../../../../../../api/staff_registry/staff_registry_client', () => ({ staffRegistryClient: mocks }));
vi.mock('../../../../../../../api/staff_profile/staff_resume_client', () => ({ staffResumeClient: {
  current: mocks.currentResume,
  upload: mocks.uploadResume,
  download: mocks.downloadResume,
} }));

describe('Staff registry owner editing', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.currentResume.mockResolvedValue(null);
    mocks.previewBank.mockResolvedValue({ staff_id: STAFF_PROFILE.staff_id, current_version: STAFF_PROFILE.bank_accounts_version, operation: 'add', before: null, after: { account_id: null, bank_code: '812', branch_code: '0012', account_last4: '7890', is_primary: false, is_active: true }, preview_fingerprint: 'b'.repeat(64) });
  });

  it('clears the complete bank account after an uncertain result and prevents duplicate in-flight apply', async () => {
    let rejectApply: (error: Error) => void = () => undefined;
    mocks.applyBank.mockImplementation(() => new Promise((_, reject) => { rejectApply = reject; }));
    const onUpdated = vi.fn().mockResolvedValue(undefined);
    render(<StaffRegistryEditor profile={STAFF_PROFILE} onUpdated={onUpdated} />);
    const bank = screen.getByRole('heading', { name: /管理銀行帳戶/ }).closest('section') as HTMLElement;

    fireEvent.change(within(bank).getByLabelText('銀行代碼'), { target: { value: '812' } });
    fireEvent.change(within(bank).getByLabelText('分行代碼'), { target: { value: '0012' } });
    const account = within(bank).getByLabelText('完整新帳號');
    fireEvent.change(account, { target: { value: '1234567890' } });
    fireEvent.click(within(bank).getByRole('button', { name: '預覽變更' }));
    await within(bank).findByText(/末四碼 7890/);
    fireEvent.change(within(bank).getByLabelText('異動原因'), { target: { value: '本人提供新帳戶' } });
    const apply = within(bank).getByRole('button', { name: '確認儲存' });
    fireEvent.click(apply);
    fireEvent.click(apply);
    await waitFor(() => expect(mocks.applyBank).toHaveBeenCalledTimes(1));
    expect(mocks.applyBank.mock.calls[0][5]).toMatch(/^staff-bank-/);
    rejectApply(new Error('連線中斷，結果未知'));
    await waitFor(() => expect(account).toHaveValue(''));
    expect(onUpdated).toHaveBeenCalledTimes(1);
    expect(screen.queryByDisplayValue('1234567890')).not.toBeInTheDocument();
  });

  it('shows the current resume and uploads a new PDF version with one stable operation identity', async () => {
    mocks.currentResume.mockResolvedValue({ file_id: 'cf_11111111111111111111111111111111', filename: 'resume-v2.pdf', version: 2 });
    mocks.uploadResume.mockResolvedValue({ file_id: 'cf_22222222222222222222222222222222', filename: 'resume-v3.pdf', version: 3 });
    render(<StaffRegistryEditor profile={STAFF_PROFILE} onUpdated={vi.fn()} />);

    expect(await screen.findByText('目前履歷：resume-v2.pdf')).toBeInTheDocument();
    expect(screen.getByText('版本：2')).toBeInTheDocument();
    const file = new File(['%PDF-1.7\nresume'], 'resume-v3.pdf', { type: 'application/pdf', lastModified: 1 });
    fireEvent.change(screen.getByLabelText('選擇 PDF'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: '上傳新版履歷' }));

    expect(await screen.findByText('目前履歷：resume-v3.pdf')).toBeInTheDocument();
    expect(mocks.uploadResume).toHaveBeenCalledWith(
      STAFF_PROFILE.staff_id,
      file,
      expect.stringMatching(new RegExp(`^staff-resume-${STAFF_PROFILE.staff_id}-`)),
    );
    expect(screen.getByText('月嫂履歷已完成受控上傳。')).toBeInTheDocument();
  });

  it('downloads only the current resume identity', async () => {
    mocks.currentResume.mockResolvedValue({ file_id: 'cf_11111111111111111111111111111111', filename: 'resume.pdf', version: 4 });
    mocks.downloadResume.mockResolvedValue(undefined);
    render(<StaffRegistryEditor profile={STAFF_PROFILE} onUpdated={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: '下載目前履歷' }));

    await waitFor(() => expect(mocks.downloadResume).toHaveBeenCalledWith(
      'cf_11111111111111111111111111111111',
      'resume.pdf',
    ));
  });

  it('reuses the same resume operation identity after an uncertain upload result', async () => {
    mocks.uploadResume
      .mockRejectedValueOnce(new Error('連線中斷，結果尚未確認。'))
      .mockResolvedValueOnce({ file_id: 'cf_22222222222222222222222222222222', filename: 'resume.pdf', version: 1 });
    render(<StaffRegistryEditor profile={STAFF_PROFILE} onUpdated={vi.fn()} />);
    await screen.findByText('尚未上傳月嫂履歷 PDF');
    const file = new File(['%PDF-1.7\nresume'], 'resume.pdf', { type: 'application/pdf', lastModified: 1 });
    fireEvent.change(screen.getByLabelText('選擇 PDF'), { target: { files: [file] } });

    const upload = screen.getByRole('button', { name: '上傳履歷' });
    fireEvent.click(upload);
    await screen.findByText('連線中斷，結果尚未確認。');
    fireEvent.click(upload);
    await screen.findByText('月嫂履歷已完成受控上傳。');

    expect(mocks.uploadResume).toHaveBeenCalledTimes(2);
    expect(mocks.uploadResume.mock.calls[1][2]).toBe(mocks.uploadResume.mock.calls[0][2]);
  });
});
