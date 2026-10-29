import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RegistrationApplications } from '../components/RegistrationApplications';
import { registrationApplicationsClient as client } from '../api/registration_applications/client';
import { sessionClient } from '../api/auth/session_client';

const application = { registration_id: 5, version: 1, name: '測試申請人', phone: '0900000000',
  approved: false, registration_kind: 'subsidy' as const, case_no: null, approved_at_utc: null,
  fields: [{ label: '服務地址', value: '測試地址' }] };
const envelope = (data: unknown) => ({ success: true, message: '', data, error: null });
const response = (data: unknown) => ({ ok: true, status: 200, statusText: 'OK',
  headers: new Headers({ 'content-type': 'application/json' }), json: async () => envelope(data) });

beforeEach(() => sessionClient.setSession('test-session', { id: 7, username: 'staff', display_name: 'Staff', role: 'admin' }));
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); sessionClient.clearSession(); });

describe('saved demand application review', () => {
  it('requires a complete non-citizen case result after approval', async () => {
    const pending = { ...application, registration_kind: 'non_citizen' as const };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ ...pending, approved: true, version: 2 })));
    await expect(client.approve(pending)).rejects.toThrow('正式案件尚未確認');
    const approved = { ...pending, approved: true, version: 2, case_no: 'A115001', approved_at_utc: '2026-10-29T05:00:00+00:00' };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(approved)));
    await expect(client.approve(pending)).resolves.toEqual(approved);
  });
  it('uses the authenticated session and version, without accepting an actor from the browser', async () => {
    const fetch = vi.fn().mockResolvedValue(response({ ...application, approved: true, version: 2 }));
    vi.stubGlobal('fetch', fetch);
    await client.approve(application);
    expect(fetch.mock.calls[0][0]).toBe('/api/v1/admin/registration-applications/5/approve');
    expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer test-session');
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ expected_version: 1 });
  });

  it('rejects an unconfirmed approval result', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(application)));
    await expect(client.approve(application)).rejects.toThrow('核准結果尚未確認');
  });

  it('shows the saved contents before approval and keeps failed approvals visible', async () => {
    vi.spyOn(client, 'pending').mockResolvedValue([application]);
    vi.spyOn(client, 'detail').mockResolvedValue(application);
    const approve = vi.spyOn(client, 'approve').mockRejectedValueOnce(new Error('狀態已變更，請重新查詢'));
    const state = vi.fn();
    render(<RegistrationApplications onEditStateChange={state} />);
    fireEvent.click(await screen.findByText('申請 5：測試申請人／0900000000'));
    expect(await screen.findByText('測試地址')).toBeInTheDocument();
    expect(approve).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('核准並建立客戶'));
    expect(await screen.findByRole('alert')).toHaveTextContent('狀態已變更');
    expect(screen.getByText('申請 5：測試申請人／0900000000')).toBeInTheDocument();
    expect(approve).toHaveBeenCalledWith(application);
    await waitFor(() => expect(state).toHaveBeenLastCalledWith({ dirty: false, busy: false }));
  });
});
