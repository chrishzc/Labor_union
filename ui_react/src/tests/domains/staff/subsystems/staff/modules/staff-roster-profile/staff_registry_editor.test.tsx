import { UnsavedChangesProvider, useUnsavedNavigation } from '../../../../../../../components/UnsavedChanges';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StaffRegistryEditor } from '../../../../../../../components/StaffRegistryEditor';
import { STAFF_PROFILE } from './fixtures/staff_profile_contract_fixtures';

const mocks = vi.hoisted(() => ({
  previewProfile: vi.fn(), applyProfile: vi.fn(), previewBank: vi.fn(), applyBank: vi.fn(),
  currentResume: vi.fn(), uploadResume: vi.fn(), downloadResume: vi.fn(), previewResume: vi.fn(), settings: vi.fn(),
}));
vi.mock('../../../../../../../api/staff_registry/staff_registry_client', () => ({ staffRegistryClient: mocks }));
vi.mock('../../../../../../../api/staff_profile/staff_resume_client', () => ({ fileSizeLabel: (bytes: number) => `${(bytes / 1048576).toFixed(2)} MiB`, staffResumeClient: {
  current: mocks.currentResume,
  upload: mocks.uploadResume,
  download: mocks.downloadResume,
  preview: mocks.previewResume,
  settings: mocks.settings,
} }));

function LeaveProbe({ leave }: { leave: () => void }) {
  const { requestLeave } = useUnsavedNavigation();
  return <button type="button" onClick={() => requestLeave(leave)}>離開名冊</button>;
}

describe('Staff registry owner editing', () => {
  beforeEach(() => {
    vi.spyOn(window, 'alert').mockImplementation(() => undefined);
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.currentResume.mockResolvedValue(null);
    mocks.settings.mockResolvedValue({ photo_max_bytes: 10485760, resume_max_bytes: 20971520, timeout_seconds: 300 });
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:resume-preview');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    mocks.previewBank.mockResolvedValue({ staff_id: STAFF_PROFILE.staff_id, current_version: STAFF_PROFILE.bank_accounts_version, operation: 'add', before: null, after: { account_id: null, bank_code: '812', branch_code: '0012', account_last4: '7890', is_primary: false, is_active: true }, preview_fingerprint: 'b'.repeat(64) });
  });
  afterEach(() => vi.restoreAllMocks());

  it('saves profile changes directly from the warning without a separate preview click', async () => {
    mocks.previewProfile.mockResolvedValue({ staff_id: 11, current_version: 2,
      before: { union_no: 'A001' }, after: { union_no: 'Ab0007' }, preview_fingerprint: 'a'.repeat(64) });
    mocks.applyProfile.mockResolvedValue({});
    let finishReadback!: () => void;
    const readback = new Promise<void>(resolve => { finishReadback = resolve; });
    const leave = vi.fn();
    function Harness() {
      const [profile, setProfile] = useState(STAFF_PROFILE);
      return <><StaffRegistryEditor profile={profile} showResume={false} onUpdated={async () => {
        await readback;
        setProfile({ ...STAFF_PROFILE, union_no: 'Ab0007', profile_version: 3 });
      }} /><LeaveProbe leave={leave} /></>;
    }
    render(<UnsavedChangesProvider><Harness /></UnsavedChangesProvider>);
    fireEvent.change(screen.getByLabelText('公會編號'), { target: { value: 'Ab0007' } });
    fireEvent.click(screen.getByRole('button', { name: '離開名冊' }));
    const warning = screen.getByRole('dialog', { name: '尚有未儲存的變更' });
    const save = within(warning).getByRole('button', { name: '儲存變更並離開' });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() => expect(mocks.applyProfile).toHaveBeenCalledOnce());
    expect(mocks.previewProfile).toHaveBeenCalledWith(11, { union_no: 'Ab0007' }, 2);
    expect(mocks.applyProfile).toHaveBeenCalledWith(11, { union_no: 'Ab0007' }, 2, 'a'.repeat(64), '', expect.any(String));
    expect(leave).not.toHaveBeenCalled();
    await act(async () => { finishReadback(); await readback; });
    await waitFor(() => expect(leave).toHaveBeenCalledOnce());
    expect(screen.getByLabelText('公會編號')).toHaveValue('Ab0007');
  });

  it.each(['', '   ', '設定公會編號'])('saves the profile in one click with optional notes %j', async (note) => {
    mocks.previewProfile.mockResolvedValue({ staff_id: 11, current_version: 2, before: { union_no: 'A001' }, after: { union_no: 'Ab0007' }, preview_fingerprint: 'a'.repeat(64) });
    mocks.applyProfile.mockResolvedValue({});
    const onUpdated = vi.fn();
    render(<StaffRegistryEditor profile={STAFF_PROFILE} onUpdated={onUpdated} />);
    const section = screen.getByRole('heading', { name: /編輯個人與聯絡資料/ }).closest('section')!;
    const save = within(section).getByRole('button', { name: '儲存' });
    expect(save).toBeDisabled();
    fireEvent.change(within(section).getByLabelText('公會編號'), { target: { value: 'Ab0007' } });
    const notes = within(section).getByLabelText('個人資料備註（選填）');
    expect(notes).not.toHaveAttribute('aria-required');
    fireEvent.change(notes, { target: { value: note } });
    expect(within(section).queryByRole('button', { name: '預覽變更' })).not.toBeInTheDocument();
    expect(mocks.applyProfile).not.toHaveBeenCalled();
    fireEvent.click(save);
    await within(section).findByText('個人資料已儲存。');
    expect(mocks.previewProfile).toHaveBeenCalledOnce();
    expect(mocks.applyProfile).toHaveBeenCalledWith(11, { union_no: 'Ab0007' }, 2, 'a'.repeat(64), note.trim(), expect.any(String));
    expect(window.alert).not.toHaveBeenCalled();
    expect(onUpdated).toHaveBeenCalledOnce();
  });

  it('keeps the draft and prevents apply when the union number is duplicated', async () => {
    mocks.previewProfile.mockRejectedValue(new Error('此公會編號已被使用，請輸入其他編號。'));
    render(<StaffRegistryEditor profile={STAFF_PROFILE} onUpdated={vi.fn()} />);
    const section = screen.getByRole('heading', { name: /編輯個人與聯絡資料/ }).closest('section')!;
    fireEvent.change(within(section).getByLabelText('公會編號'), { target: { value: 'B002' } });
    fireEvent.click(within(section).getByRole('button', { name: '儲存' }));
    await within(section).findByText('此公會編號已被使用，請輸入其他編號。');
    expect(within(section).getByLabelText('公會編號')).toHaveValue('B002');
    expect(within(section).getByRole('button', { name: '儲存' })).toBeEnabled();
    expect(mocks.applyProfile).not.toHaveBeenCalled();
  });

  it.each(['', '   ', '本人提供新帳戶'])('saves the bank in one click with optional notes %j and keeps business fields required', async (note) => {
    mocks.applyBank.mockResolvedValue({});
    const updated = vi.fn();
    render(<StaffRegistryEditor profile={STAFF_PROFILE} onUpdated={updated} showResume={false} />);
    const bank = screen.getByRole('heading', { name: /管理銀行帳戶/ }).closest('section')!;
    const save = within(bank).getByRole('button', { name: '儲存' });
    expect(save).toBeDisabled();
    expect(mocks.previewBank).not.toHaveBeenCalled();
    fireEvent.change(within(bank).getByLabelText('銀行代碼'), { target: { value: '812' } });
    fireEvent.change(within(bank).getByLabelText('分行代碼'), { target: { value: '0012' } });
    fireEvent.change(within(bank).getByLabelText('完整新帳號'), { target: { value: '1234567890' } });
    fireEvent.change(within(bank).getByLabelText('備註（選填）'), { target: { value: note } });
    expect(save).toBeEnabled();
    expect(within(bank).queryByRole('button', { name: '預覽變更' })).not.toBeInTheDocument();
    fireEvent.click(save);
    await waitFor(() => expect(mocks.applyBank).toHaveBeenCalledOnce());
    expect(mocks.applyBank.mock.calls[0][4]).toBe(note.trim());
    expect(mocks.previewBank).toHaveBeenCalledOnce();
    expect(updated).toHaveBeenCalledOnce();
    expect(window.alert).not.toHaveBeenCalled();
    expect(mocks.currentResume).not.toHaveBeenCalled();
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
    fireEvent.change(within(bank).getByLabelText('備註（選填）'), { target: { value: '本人提供新帳戶' } });
    const apply = within(bank).getByRole('button', { name: '儲存' });
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

  it('previews selected and saved PDFs and releases the preview on close', async () => {
    mocks.currentResume.mockResolvedValue({ file_id: 'cf_' + '1'.repeat(32), filename: 'resume.pdf', version: 1 });
    mocks.previewResume.mockResolvedValue(new Blob(['%PDF-saved'], { type: 'application/pdf' }));
    render(<StaffRegistryEditor profile={STAFF_PROFILE} onUpdated={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: '預覽目前履歷' }));
    expect(await screen.findByLabelText('履歷 PDF 預覽')).toHaveAttribute('data', 'blob:resume-preview');
    expect(mocks.previewResume).toHaveBeenCalledWith('cf_' + '1'.repeat(32));
    fireEvent.click(screen.getByRole('button', { name: '關閉履歷預覽' }));
    await waitFor(() => expect(screen.queryByLabelText('履歷 PDF 預覽')).not.toBeInTheDocument());
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:resume-preview');
    const file = new File(['%PDF-selected'], 'selected.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('選擇 PDF'), { target: { files: [file] } });
    expect(await screen.findByLabelText('履歷 PDF 預覽')).toBeInTheDocument();
    expect(mocks.uploadResume).not.toHaveBeenCalled();
  });

  it('uses configured capacity and shows an actionable error without uploading', async () => {
    mocks.settings.mockResolvedValue({ photo_max_bytes: 50, resume_max_bytes: 8, timeout_seconds: 600 });
    render(<StaffRegistryEditor profile={STAFF_PROFILE} onUpdated={vi.fn()} />);
    await screen.findByText('尚未上傳月嫂履歷 PDF');
    fireEvent.change(screen.getByLabelText('選擇 PDF'), { target: { files: [new File(['%PDF-too-large'], 'large.pdf', { type: 'application/pdf' })] } });
    expect(screen.getByRole('alert')).toHaveTextContent('超過目前上限');
    expect(screen.getByRole('alert')).toHaveTextContent('本次未上傳');
    expect(screen.getByRole('button', { name: '上傳履歷' })).toBeDisabled();
    expect(mocks.uploadResume).not.toHaveBeenCalled();
  });

  it('does not report an empty resume while loading or after a failed read', async () => {
    mocks.currentResume.mockRejectedValueOnce(new Error('儲存服務暫不可用'));
    render(<StaffRegistryEditor profile={STAFF_PROFILE} onUpdated={vi.fn()} />);
    expect(screen.queryByText('尚未上傳月嫂履歷 PDF')).not.toBeInTheDocument();
    expect(await screen.findByRole('alert')).toHaveTextContent('儲存服務暫不可用');
    expect(screen.queryByText('尚未上傳月嫂履歷 PDF')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新讀取履歷' }));
    expect(await screen.findByText('尚未上傳月嫂履歷 PDF')).toBeInTheDocument();
  });

  it('displays full bank account number in account selection when available', async () => {
    const profileWithAccountNo = {
      ...STAFF_PROFILE,
      bank_accounts: [
        { account_id: 3, bank_code: '812', branch_code: '0012', account_no: '81230011223344', account_last4: '3344', is_primary: true, is_active: true },
      ],
    };
    render(<StaffRegistryEditor profile={profileWithAccountNo} onUpdated={vi.fn()} />);
    await screen.findByText('尚未上傳月嫂履歷 PDF');
    const bankSection = screen.getByRole('heading', { name: /管理銀行帳戶/ }).closest('section') as HTMLElement;
    fireEvent.change(within(bankSection).getByLabelText('動作'), { target: { value: 'replace' } });
    expect(within(bankSection).getByRole('combobox', { name: '帳戶' })).toHaveTextContent('帳號 81230011223344');
  });
  it('shows real profile changes while keeping complete bank input out of the leave warning', async () => {
    const leave = vi.fn();
    render(<UnsavedChangesProvider><StaffRegistryEditor profile={STAFF_PROFILE} onUpdated={vi.fn()} showResume={false} /><LeaveProbe leave={leave} /></UnsavedChangesProvider>);
    fireEvent.change(screen.getByLabelText('姓名'), { target: { value: '合成人員' } });
    const account = '0000111122223333';
    fireEvent.change(screen.getByLabelText('完整新帳號'), { target: { value: account } });
    fireEvent.click(screen.getByRole('button', { name: '離開名冊' }));
    const warning = screen.getByRole('dialog', { name: '尚有未儲存的變更' });
    expect(within(warning).getByRole('cell', { name: STAFF_PROFILE.name! })).toBeInTheDocument();
    expect(within(warning).getByRole('cell', { name: '合成人員' })).toBeInTheDocument();
    expect(warning).toHaveTextContent('新帳號已輸入（不顯示內容）');
    expect(warning).not.toHaveTextContent(account);
    expect(mocks.applyProfile).not.toHaveBeenCalled(); expect(mocks.applyBank).not.toHaveBeenCalled();
    fireEvent.click(within(warning).getByRole('button', { name: '繼續編輯' }));
    expect(screen.getByLabelText('完整新帳號')).toHaveValue(account);
    expect(leave).not.toHaveBeenCalled();
  });

});
