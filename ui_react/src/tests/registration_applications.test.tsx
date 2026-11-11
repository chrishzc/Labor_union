import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RegistrationApplications } from '../components/RegistrationApplications';
import { registrationApplicationsClient as client } from '../api/registration_applications/client';
import { sessionClient } from '../api/auth/session_client';

const application = { registration_id: 5, version: 1, name: '測試申請人', phone: '0900000000',
  approved: false, status: 'pending' as const, submitted_at_utc: '2026-11-05T00:00:00Z', expires_at_utc: '2026-11-19T00:00:00Z', registration_kind: 'subsidy' as const, case_no: null, approved_at_utc: null,
  fields: [{ label: '服務地址', value: '測試地址' }] };
const envelope = (data: unknown) => ({ success: true, message: '', data, error: null });
const response = (data: unknown) => ({ ok: true, status: 200, statusText: 'OK',
  headers: new Headers({ 'content-type': 'application/json' }), json: async () => envelope(data) });

beforeEach(() => sessionClient.setSession('test-session', { id: 7, username: 'staff', display_name: 'Staff', role: 'admin' }));
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); sessionClient.clearSession(); });

describe('saved demand application review', () => {
  it('requires a complete non-citizen case result after approval', async () => {
    const pending = { ...application, registration_kind: 'non_citizen' as const };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ ...pending, approved: true, status: 'approved' as const, version: 2 })));
    await expect(client.approve(pending)).rejects.toThrow('正式案件尚未確認');
    const approved = { ...pending, approved: true, status: 'approved' as const, version: 2, case_no: 'A115001', approved_at_utc: '2026-10-29T05:00:00+00:00' };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(approved)));
    await expect(client.approve(pending)).resolves.toEqual(approved);
  });
  it('uses the authenticated session and version, without accepting an actor from the browser', async () => {
    const fetch = vi.fn().mockResolvedValue(response({ ...application, approved: true, status: 'approved' as const, version: 2 }));
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

  it('rejects using the original version and displays only the cleared terminal result', async () => {
    vi.spyOn(client, 'pending').mockResolvedValue([application]);
    vi.spyOn(client, 'detail').mockResolvedValue(application);
    const reject = vi.spyOn(client, 'reject').mockResolvedValue({...application, name:null, phone:null,
      fields:[], status:'rejected', version:2});
    render(<RegistrationApplications onEditStateChange={vi.fn()}/>);
    fireEvent.click(await screen.findByText('申請 5：測試申請人／0900000000'));
    fireEvent.click(await screen.findByRole('button', {name:'拒絕並清除問卷'}));
    await screen.findByRole('heading', {name:'申請 5：內容已清除'});
    expect(reject).toHaveBeenCalledWith(application);
    expect(screen.queryByText('測試地址')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', {name:'核准並建立客戶'})).not.toBeInTheDocument();
  });

  it('previews new case numbers and shows the final numbers returned on submit', async () => {
    vi.spyOn(client, 'pending').mockResolvedValue([]);
    vi.spyOn(client, 'nextNonCitizenNumber').mockResolvedValue({
      case_no: 'A115001', virtual_account: '99781699115501',
    });
    const create = vi.spyOn(client, 'createManualNonCitizen').mockResolvedValue({
      case_no: 'A115002', virtual_account: '99781699115502', client_id: 101,
      message: '非市民新案「A115002」建立成功。',
    });
    render(<RegistrationApplications onEditStateChange={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole('button', { name: '手動新增非市民新案' })).toBeEnabled());
    expect(screen.queryByRole('button', { name: '補登歷史非市民案件' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '手動新增非市民新案' }));
    expect(await screen.findByText('A115001')).toBeInTheDocument();
    expect(screen.getByText('99781699115501')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('例如 A113001')).not.toBeInTheDocument();
    expect(screen.getByLabelText('是否需要下廚')).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('姓名'), { target: { value: '測試客戶' } });
    fireEvent.change(screen.getByPlaceholderText('手機或市話'), { target: { value: '0912345678' } });
    fireEvent.change(screen.getByLabelText(/預計服務開始日/), { target: { value: '2026-12-01' } });
    fireEvent.click(screen.getByRole('button', { name: '確認建立新案' }));

    expect(await screen.findByText(/A115002.*99781699115502/)).toBeInTheDocument();
    expect(create.mock.calls[0][0]).toMatchObject({ mode: 'new' });
    expect(create.mock.calls[0][0]).not.toHaveProperty('case_no');
    expect(create.mock.calls[0][0]).not.toHaveProperty('virtual_account');
  });
});
