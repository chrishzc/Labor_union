import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { DatabaseBackupPage } from '../../../../../../../pages/DatabaseBackupPage';
import { UnsavedChangesProvider } from '../../../../../../../components/UnsavedChanges';
import { databaseBackupClient as client } from '../../../../../../../api/database_backup_client';
import { NAV_ITEMS, PAGE_SECTION_MAP } from '../../../../../../../components/MasterLayout';

vi.mock('../../../../../../../api/database_backup_client', () => ({ databaseBackupClient: { read: vi.fn(), save: vi.fn() } }));
const initial = { configured: true, enabled: true, time: '18:00', version: 3,
  storage_ready: true, storage_message: 'NAS 備份區目前可讀取；備份時會再驗證寫入。', disaster_recovery_ready: false,
  last_backup: '2026-10-30T10:00:00Z', last_result: { status: 'passed' as const, time: '2026-10-30T10:00:00Z' } };
const show = () => render(<UnsavedChangesProvider><DatabaseBackupPage /></UnsavedChangesProvider>);

describe('資料庫備份時間', () => {
  beforeEach(() => { vi.resetAllMocks(); vi.mocked(client.read).mockResolvedValue(initial); });
  it('位於稽核與系統，顯示每天18:00及最近備份，修改時帶入版本', async () => {
    expect(PAGE_SECTION_MAP['database-backup']).toBe('audit');
    expect(NAV_ITEMS.find(item => item.id === 'database-backup')?.label).toBe('資料庫備份');
    vi.mocked(client.save).mockResolvedValue({ ...initial, time: '17:30', version: 4 });
    show();
    const input = await screen.findByLabelText('每天執行時間');
    expect(input).toHaveValue('18:00');
    fireEvent.change(input, { target: { value: '17:30' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存時間' }));
    await screen.findByText('已設定每天 17:30 自動備份。');
    expect(client.save).toHaveBeenCalledWith('17:30', 3);
  });
  it('開發機未設定時不能啟用排程，也不會呼叫儲存', async () => {
    vi.mocked(client.read).mockResolvedValue({ ...initial, configured: false, enabled: false, last_backup: null });
    show();
    expect(await screen.findByRole('button', { name: '啟用每日備份' })).toBeDisabled();
    expect(screen.getByText(/尚未完成正式電腦/)).toBeInTheDocument();
    expect(client.save).not.toHaveBeenCalled();
  });
  it('顯示備份失敗；儲存衝突不會冒充成功或重試', async () => {
    vi.mocked(client.read).mockResolvedValue({ ...initial, last_result: { status: 'failed', time: '2026-10-30T10:00:00Z' } });
    vi.mocked(client.save).mockRejectedValue(new Error('備份時間已由其他人修改，請重新載入後再儲存。'));
    show();
    await screen.findByText(/最近一次備份失敗/);
    fireEvent.click(screen.getByRole('button', { name: '儲存時間' }));
    await waitFor(() => expect(screen.getByText(/備份時間已由其他人修改/)).toBeInTheDocument());
    expect(client.save).toHaveBeenCalledTimes(1);
    expect(screen.queryByText(/已設定每天/)).not.toBeInTheDocument();
  });
  it('NAS離線時停止啟用，顯示不回存本機與待復原演練狀態', async () => {
    vi.mocked(client.read).mockResolvedValue({ ...initial, enabled: false, storage_ready: false,
      storage_message: 'NAS 備份區目前無法使用，備份不會改存本機。' });
    show();
    expect(await screen.findByRole('button', { name: '啟用每日備份' })).toBeDisabled();
    expect(screen.getByText('NAS 備份區目前無法使用，備份不會改存本機。')).toBeInTheDocument();
    expect(screen.getByText('正式復原演練與備份隔離性仍待維護人員驗收。')).toBeInTheDocument();
    expect(client.save).not.toHaveBeenCalled();
  });
});
