import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StaffRegistryEditor } from '../../../../../../../components/StaffRegistryEditor';
import { UnsavedChangesProvider } from '../../../../../../../components/UnsavedChanges';
import { staffProfileClient, queryStaffProfile, downloadStaffSavedDocument } from '../../../../../../../api/staff_profile/staff_profile_client';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { transport } from '../../../../../../../api/shared/transport';
import { STAFF_PROFILE } from './fixtures/staff_profile_contract_fixtures';
import type { StaffSavedDocument, StaffProfile } from '../../../../../../../api/staff_profile/staff_profile_schemas';

const first: StaffSavedDocument = { staff_id: 11, file_id: `cf_${'a'.repeat(32)}`, purpose: 'staff_certificate',
  filename: 'certificate.pdf', version: 2, sha256_digest: 'c'.repeat(64), mime_type: 'application/pdf', size_bytes: 3 };
const second: StaffSavedDocument = { ...first, file_id: `cf_${'b'.repeat(32)}`, purpose: 'staff_health_exam', filename: 'health.pdf' };
const profile = (items: StaffSavedDocument[] = [first], next: string | null = first.file_id): StaffProfile => ({
  ...STAFF_PROFILE, documents: { status: 'available', items, next_cursor: next },
});
const envelope = (value: StaffProfile) => ({ success: true, message: 'ok', error: null, data: value });
const settings = (timeout: number) => ({ success: true, message: 'ok', error: null,
  data: { photo_max_bytes: 10485760, resume_max_bytes: 20971520, timeout_seconds: timeout } });

beforeEach(() => { vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-session'); });
afterEach(() => vi.restoreAllMocks());

describe('Staff saved document client', () => {
  it('uses the original authenticated profile endpoint and exact cursor', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValue(envelope(profile([second], null)));
    const result = await queryStaffProfile(11, { documentsAfter: first.file_id, documentsPageSize: 1 });
    expect(result.documents?.items).toEqual([second]);
    expect(get).toHaveBeenCalledWith(`/api/v1/staff/11/profile?documents_after=${first.file_id}&documents_page_size=1`,
      expect.objectContaining({ token: 'synthetic-session' }));
  });

  it.each(['subject', 'privatePath', 'cursor', 'overflow', 'unavailableItems'])('rejects malformed %s source without presenting empty success', async kind => {
    const value = structuredClone(profile());
    if (kind === 'subject') value.documents!.items[0].staff_id = 12;
    if (kind === 'privatePath') Object.assign(value.documents!.items[0], { storage_locator: '/private/source' });
    if (kind === 'cursor') value.documents!.next_cursor = second.file_id;
    if (kind === 'overflow') value.documents!.items = Array.from({ length: 201 }, () => first);
    if (kind === 'unavailableItems') value.documents!.status = 'unavailable';
    vi.spyOn(transport, 'get').mockResolvedValue(envelope(value));
    await expect(queryStaffProfile(11)).rejects.toThrow();
  });

  it('distinguishes empty available from unavailable and uses the existing download boundary', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValueOnce(envelope(profile([], null)))
      .mockResolvedValueOnce(envelope({ ...STAFF_PROFILE, documents: { status: 'unavailable', items: [], next_cursor: null } }));
    expect((await queryStaffProfile(11)).documents?.status).toBe('available');
    expect((await queryStaffProfile(11)).documents?.status).toBe('unavailable');
    get.mockResolvedValueOnce(settings(0)).mockResolvedValueOnce(new Blob(['abc'], { type: 'application/pdf' }));
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:synthetic-document');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    await downloadStaffSavedDocument(first);
    expect(get).toHaveBeenLastCalledWith(`/api/v1/data-center/files/${first.file_id}/download`,
      expect.objectContaining({ token: 'synthetic-session', responseType: 'blob', cache: 'no-store', timeoutMs: 0 }));
    get.mockResolvedValueOnce(settings(120)).mockResolvedValueOnce(new Blob(['wrong'], { type: 'image/jpeg' }));
    await expect(downloadStaffSavedDocument(first)).rejects.toThrow('版本或格式');
    expect(get).toHaveBeenLastCalledWith(`/api/v1/data-center/files/${first.file_id}/download`, expect.objectContaining({ timeoutMs: 120000 }));
    expect(get.mock.calls.filter(call => call[0] === '/api/v1/storage/transfer-settings')).toHaveLength(2);
  });

  it('does not start a file download when the original fresh settings reader fails', async () => {
    const get = vi.spyOn(transport, 'get').mockRejectedValue(new Error('settings unavailable'));
    await expect(downloadStaffSavedDocument(first)).rejects.toThrow('settings unavailable');
    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith('/api/v1/storage/transfer-settings', expect.anything());
  });
});

describe('original Staff drawer saved document collection', () => {
  it('loads the next file page without resetting an unsaved profile edit', async () => {
    const query = vi.spyOn(staffProfileClient, 'query').mockResolvedValue(profile([second], null));
    const updated = vi.fn();
    render(<UnsavedChangesProvider><StaffRegistryEditor profile={profile()} onUpdated={updated} showResume={false} /></UnsavedChangesProvider>);
    fireEvent.change(screen.getByLabelText('姓名'), { target: { value: '尚未儲存的姓名' } });
    fireEvent.click(screen.getByRole('button', { name: '載入更多文件' }));
    await screen.findByRole('button', { name: '下載 health.pdf' });
    expect(screen.getByLabelText('姓名')).toHaveValue('尚未儲存的姓名');
    expect(query).toHaveBeenCalledWith(11, { documentsAfter: first.file_id });
    expect(updated).not.toHaveBeenCalled();
    const section = screen.getByText('已保存的證照／體檢與良民證文件').closest('section')!;
    expect(section.querySelector('input')).toBeNull();
    expect(within(section).queryByRole('button', { name: /上傳/ })).toBeNull();
    expect(within(section).getByText('僅列出保存文件，不代表資格、檢查結果或有效期已通過。')).toBeInTheDocument();
  });

  it('keeps existing files and unsaved edits when the next page source fails', async () => {
    vi.spyOn(staffProfileClient, 'query').mockRejectedValue(new Error('文件來源暫時無法讀取'));
    render(<UnsavedChangesProvider><StaffRegistryEditor profile={profile()} onUpdated={vi.fn()} showResume={false} /></UnsavedChangesProvider>);
    fireEvent.change(screen.getByLabelText('姓名'), { target: { value: '保留草稿' } });
    fireEvent.click(screen.getByRole('button', { name: '載入更多文件' }));
    await screen.findByText('文件來源暫時無法讀取');
    expect(screen.getByRole('button', { name: '下載 certificate.pdf' })).toBeInTheDocument();
    expect(screen.getByLabelText('姓名')).toHaveValue('保留草稿');
  });

  it.each(['empty', 'unavailable'] as const)('shows %s without claiming medical or qualification validity', async kind => {
    const value = profile([], null);
    value.documents!.status = kind === 'empty' ? 'available' : 'unavailable';
    render(<UnsavedChangesProvider><StaffRegistryEditor profile={value} onUpdated={vi.fn()} showResume={false} /></UnsavedChangesProvider>);
    await waitFor(() => expect(screen.getByText(kind === 'empty' ? '尚未保存證照、體檢或良民證文件。' : '文件清單目前無法讀取。')).toBeInTheDocument());
    expect(screen.queryByText(kind === 'empty' ? '文件清單目前無法讀取。' : '尚未保存證照、體檢或良民證文件。')).toBeNull();
  });
});
