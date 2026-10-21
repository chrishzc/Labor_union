import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FileSettingsPage } from '../../../../../../../pages/FileSettingsPage';
import { fileSettingsClient, type FileSettings } from '../../../../../../../api/system/file_settings_client';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import { UnsavedChangesProvider, useUnsavedNavigation } from '../../../../../../../components/UnsavedChanges';

const current: FileSettings = { version: 2, photo_max_bytes: 10485760, resume_max_bytes: 20971520,
  timeout_seconds: 60, container_root: '/data/controlled-files' };

describe('NAS file settings', () => {
  beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(fileSettingsClient, 'read').mockResolvedValue(current); });

  function LeaveButton({ onLeave }: { onLeave: () => void }) {
    const { requestLeave } = useUnsavedNavigation();
    return <button onClick={() => requestLeave(onLeave)}>離開設定</button>;
  }

  it('提醒視窗呼叫原設定 API，等成功回應後才離開，重新掛載讀取已儲存值', async () => {
    let acknowledge!: (value: FileSettings) => void;
    const response = new Promise<FileSettings>(resolve => { acknowledge = resolve; });
    const save = vi.spyOn(fileSettingsClient, 'save').mockReturnValue(response);
    const leave = vi.fn();
    const result = render(<UnsavedChangesProvider><FileSettingsPage /><LeaveButton onLeave={leave} /></UnsavedChangesProvider>);
    const timeout = await screen.findByLabelText('檔案操作等待時間（秒）');
    fireEvent.change(timeout, { target: { value: '120' } });
    fireEvent.click(screen.getByRole('button', { name: '離開設定' }));
    const warning = () => screen.getByRole('dialog', { name: '尚有未儲存的變更' });
    expect(within(warning()).getByRole('button', { name: '儲存變更並離開' })).toBeEnabled();
    expect(save).not.toHaveBeenCalled();
    fireEvent.click(within(warning()).getByRole('button', { name: '儲存變更並離開' }));
    expect(save).toHaveBeenCalledWith({ photo_max_bytes: current.photo_max_bytes,
      resume_max_bytes: current.resume_max_bytes, timeout_seconds: 120 }, current.version);
    expect(leave).not.toHaveBeenCalled();
    expect(within(warning()).getByRole('button', { name: '捨棄變更並離開' })).toBeDisabled();
    const saved = { ...current, version: 3, timeout_seconds: 120 };
    vi.mocked(fileSettingsClient.read).mockResolvedValue(saved);
    await act(async () => { acknowledge(saved); await response; });
    await waitFor(() => expect(leave).toHaveBeenCalledOnce());
    result.unmount();
    render(<FileSettingsPage />);
    expect(await screen.findByLabelText('檔案操作等待時間（秒）')).toHaveValue(120);
    expect(save).toHaveBeenCalledOnce();
  });

  it.each([
    ['版本衝突', new ApiHttpError(409, 'file_settings_stale', 'stale', false, null)],
    ['連線中斷', new Error('network lost')],
  ])('提醒視窗儲存遇到%s時保留輸入且不離開', async (_label, failure) => {
    const save = vi.spyOn(fileSettingsClient, 'save').mockRejectedValue(failure);
    const leave = vi.fn();
    render(<UnsavedChangesProvider><FileSettingsPage /><LeaveButton onLeave={leave} /></UnsavedChangesProvider>);
    fireEvent.change(await screen.findByLabelText('檔案操作等待時間（秒）'), { target: { value: '120' } });
    fireEvent.click(screen.getByRole('button', { name: '離開設定' }));
    const warning = screen.getByRole('dialog', { name: '尚有未儲存的變更' });
    fireEvent.click(within(warning).getByRole('button', { name: '儲存變更並離開' }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    await screen.findByText(/設定已變更或正在儲存|儲存結果尚未確認/);
    expect(screen.getByLabelText('檔案操作等待時間（秒）')).toHaveValue(120);
    expect(leave).not.toHaveBeenCalled();
  });

  it('shows the actual path read-only and saves only size and timeout after preview', async () => {
    const save = vi.spyOn(fileSettingsClient, 'save').mockResolvedValue({ ...current, version: 3,
      photo_max_bytes: 26214400, timeout_seconds: 120 });
    render(<FileSettingsPage />);
    expect(await screen.findByLabelText('照片單檔上限（MiB）')).toHaveValue(10);
    expect(screen.queryByText('原設計的檔案分類')).not.toBeInTheDocument();
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.getByText('/data/controlled-files')).toBeInTheDocument();
    expect(screen.queryByText('部署需求')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('照片單檔上限（MiB）'), { target: { value: '25' } });
    fireEvent.change(screen.getByLabelText('檔案操作等待時間（秒）'), { target: { value: '120' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    expect(save).not.toHaveBeenCalled();
    const preview = screen.getByRole('region', { name: '變更內容預覽' });
    expect(preview).toHaveTextContent('25 MiB');
    expect(preview).not.toHaveTextContent('/data/controlled-files');
    fireEvent.click(within(preview).getByRole('button', { name: '儲存設定' }));
    await screen.findByText('檔案設定已儲存，容量與等待時間已生效。');
    expect(save).toHaveBeenCalledWith({ photo_max_bytes: 26214400,
      resume_max_bytes: 20971520, timeout_seconds: 120 }, 2);
    expect(screen.getByLabelText('檔案操作等待時間（秒）')).toHaveValue(120);
    expect(screen.getByText('/data/controlled-files')).toBeInTheDocument();
  });

  it('allows no timer, and editing after preview invalidates the saved candidate', async () => {
    render(<FileSettingsPage />);
    await screen.findByLabelText('照片單檔上限（MiB）');
    fireEvent.click(screen.getByLabelText('不設定這一層的等待上限'));
    expect(screen.getByLabelText('檔案操作等待時間（秒）')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    expect(screen.getByRole('region', { name: '變更內容預覽' })).toHaveTextContent('不設定這一層的等待上限');
    fireEvent.change(screen.getByLabelText('履歷 PDF 單檔上限（MiB）'), { target: { value: '40' } });
    expect(screen.queryByRole('button', { name: '儲存設定' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '取消變更' }));
    expect(screen.getByLabelText('履歷 PDF 單檔上限（MiB）')).toHaveValue(20);
  });

  it('rejects invalid capacity with focus and no write', async () => {
    const save = vi.spyOn(fileSettingsClient, 'save');
    render(<FileSettingsPage />);
    const capacity = await screen.findByLabelText('照片單檔上限（MiB）');
    fireEvent.change(capacity, { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    expect(screen.getByRole('alert')).toHaveTextContent('大於 0');
    expect(capacity).toHaveFocus(); expect(save).not.toHaveBeenCalled();
  });

  it('requires a requery after an unknown save result and never blindly retries', async () => {
    const save = vi.spyOn(fileSettingsClient, 'save').mockRejectedValue(new Error('network lost'));
    render(<FileSettingsPage />); await screen.findByLabelText('照片單檔上限（MiB）');
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    fireEvent.click(screen.getByRole('button', { name: '儲存設定' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('儲存結果尚未確認');
    expect(screen.getByRole('button', { name: '預覽變更' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '重新讀取設定' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '預覽變更' })).toBeEnabled());
    expect(save).toHaveBeenCalledTimes(1);
  });

  it('reports a version conflict and reloads the current version', async () => {
    vi.spyOn(fileSettingsClient, 'save').mockRejectedValue(new ApiHttpError(409, 'file_settings_stale', 'stale', false, null));
    render(<FileSettingsPage />); await screen.findByLabelText('照片單檔上限（MiB）');
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    fireEvent.click(screen.getByRole('button', { name: '儲存設定' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('重新讀取');
    vi.mocked(fileSettingsClient.read).mockResolvedValue({ ...current, version: 3, timeout_seconds: 900 });
    fireEvent.click(screen.getByRole('button', { name: '重新讀取設定' }));
    await waitFor(() => expect(screen.getByLabelText('檔案操作等待時間（秒）')).toHaveValue(900));
  });

  it('does not show example settings or the editor after a permission denial', async () => {
    vi.mocked(fileSettingsClient.read).mockRejectedValue(new ApiHttpError(403, 'file_settings_forbidden', 'forbidden', false, null));
    render(<FileSettingsPage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('僅 root');
    expect(screen.queryByText('/data/controlled-files')).not.toBeInTheDocument();
  });

  it('reports an unconfigured path honestly without preventing transfer settings', async () => {
    vi.mocked(fileSettingsClient.read).mockResolvedValue({ ...current, container_root: null });
    render(<FileSettingsPage />);
    expect(await screen.findByText('尚未設定儲存位置')).toBeInTheDocument();
    expect(screen.getByLabelText('檔案操作等待時間（秒）')).toBeEnabled();
  });
});
