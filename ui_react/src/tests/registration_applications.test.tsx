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

  it('opens manual non-citizen creation modal and displays customized form fields', async () => {
    vi.spyOn(client, 'pending').mockResolvedValue([]);
    render(<RegistrationApplications onEditStateChange={vi.fn()} />);
    expect(screen.getByRole('heading', { level: 2, name: '非市民申請' })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('正在處理需求申請…')).not.toBeInTheDocument());
    const manualBtn = screen.getByRole('button', { name: '手動新增非市民案件' });
    fireEvent.click(manualBtn);
    expect(await screen.findByRole('heading', { level: 3, name: '手動新增非市民案件（補齊歷史案件）' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('例如 A113001')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('99781699 開頭之 14 碼')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('例如 09:00-18:00 (8小時)')).toBeInTheDocument();
  });

  it('handles virtual account conflict with manual override decision', async () => {
    vi.spyOn(client, 'pending').mockResolvedValue([]);
    const checkSpy = vi.spyOn(client, 'checkAccount').mockResolvedValue({
      virtual_account: '99781699113599',
      conflict: true,
      conflict_case_no: '113000099',
      conflict_case_status: '訂單取消',
      conflict_case_client_name: '被取消客戶',
      conflict_case_client_phone: '0988776655',
      has_accounting_details: false,
      received_total_ntd: 0,
      accounting_description: '無帳務明細與收款紀錄',
      cancel_reason: '客戶因素取消',
    });
    const createSpy = vi.spyOn(client, 'createManualNonCitizen').mockResolvedValue({
      case_no: 'A113099',
      virtual_account: '99781699113599',
      client_id: 101,
      overridden_case_no: '113000099',
      message: '歷史非市民案件「A113099」建立成功。',
    });

    render(<RegistrationApplications onEditStateChange={vi.fn()} />);
    await waitFor(() => expect(screen.queryByText('正在處理需求申請…')).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '手動新增非市民案件' }));

    expect(await screen.findByRole('heading', { level: 3, name: '手動新增非市民案件（補齊歷史案件）' })).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('例如 A113001'), { target: { value: 'A113099' } });
    fireEvent.change(screen.getByPlaceholderText('99781699 開頭之 14 碼'), { target: { value: '99781699113599' } });
    fireEvent.change(screen.getByPlaceholderText('姓名'), { target: { value: '歷史補登客戶' } });
    fireEvent.change(screen.getByPlaceholderText('手機或市話'), { target: { value: '0912345678' } });
    fireEvent.change(screen.getByLabelText(/預計服務開始日/), { target: { value: '2024-05-01' } });
    fireEvent.change(screen.getByLabelText(/服務天數/), { target: { value: '10' } });
    fireEvent.change(screen.getByPlaceholderText('例如 09:00-18:00 (8小時)'), { target: { value: '09:00-18:00 (8小時)' } });

    fireEvent.click(screen.getByRole('button', { name: '確認建立歷史非市民案件' }));

    expect(await screen.findByRole('heading', { level: 4, name: '⚠️ 虛擬帳號重複確認' })).toBeInTheDocument();
    expect(screen.getByText('113000099')).toBeInTheDocument();
    expect(screen.getByText('訂單取消')).toBeInTheDocument();
    expect(screen.getByText('無帳務明細與收款紀錄')).toBeInTheDocument();

    const overrideBtn = screen.getByRole('button', { name: /【由本案件覆蓋原案件】/ });
    fireEvent.click(overrideBtn);

    await waitFor(() => {
      expect(checkSpy).toHaveBeenCalled();
      expect(createSpy).toHaveBeenCalledWith(expect.objectContaining({
        case_no: 'A113099',
        virtual_account: '99781699113599',
        name: '歷史補登客戶',
        override_conflict: true,
        override_case_no: '113000099',
      }));
    });
    expect(await screen.findByText('歷史非市民案件「A113099」建立成功。')).toBeInTheDocument();
  });
});
