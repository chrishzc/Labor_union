import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RegistrationApplications } from '../components/RegistrationApplications';
import { registrationApplicationsClient as client } from '../api/registration_applications/client';
import { sessionClient } from '../api/auth/session_client';
import { clientRegistryClient } from '../api/client_registry/client_registry_client';
import type { ClientRegistryDetail } from '../api/client_registry/client_registry_schemas';

const application = { registration_id: 5, version: 1, name: '測試申請人', phone: '0900000000',
  approved: false, status: 'pending' as const, submitted_at_utc: '2026-11-05T00:00:00Z', expires_at_utc: '2026-11-19T00:00:00Z', registration_kind: 'subsidy' as const, case_no: null, approved_at_utc: null,
  fields: [{ label: '服務地址', value: '測試地址' }] };
const envelope = (data: unknown) => ({ success: true, message: '', data, error: null });
const response = (data: unknown) => ({ ok: true, status: 200, statusText: 'OK',
  headers: new Headers({ 'content-type': 'application/json' }), json: async () => envelope(data) });

const sourceDetail: ClientRegistryDetail = {
  case_no: '115000001',
  client: { client_id: 8, version: 1, field_capabilities: {}, values: {
    name: '來源客戶', gender: '女', phone: '0912345678', city: '新竹市', address: '測試地址',
    residence_type: '電梯大樓', delivery_type: '自然產', baby_info: '單胞胎', notes: '來源備註',
    identity_status: '一般市民', email: 'source@example.test', service_type: '連續服務',
  } },
  beclass: { status: 'ready', record_id: 3, source_kind: 'imported', version: 1, field_capabilities: {},
    full_refund_account_visible: true, values: {
      name: '來源客戶', email: 'source@example.test', phone: '0912345678', tel: '030000000', ext: '123',
      city: '新竹市', zip_code: '300', address: '測試地址', admin_notes: '已保存的報名備註', multi_birth_count: '雙胞胎',
      refund_bank_code: '0000001', refund_account_no: '000000000001', birth_date: '1990-01-01',
    } },
  order_information: { status: 'ready', values: {
    dietary_habits: '清淡', vegetarian_preference: false, alcohol_ratio: 0, cooking_oil_type: '橄欖油',
    maternal_allergy: '花生', special_care_notes: '已保存照護注意事項', meal_preferences: '不吃香菜',
    cooking_tools: '電鍋', bath_water_prep: '熱水器', breastfeeding_method: '親餵',
    multi_birth_count: '雙胞胎', stair_floor_fee_mode: '一樓', parking_space_provided: true, other_babies_present: '是',
  }, field_issues: {} },
  finance: { status: 'not_ready', code: null, values: null },
  order_terms: { status: 'ready', code: null, field_capabilities: {}, data: {
    case_no: '115000001', order_version: 1, scheduling_version: 1, scheduling_generation: 1,
    client_finance_version: null, payroll_version: null, service_data_locked: false,
    terms: { planned_start_date: '2026-12-01', service_days: 12, service_hours_per_day: 8,
      requires_cooking: true, floor_fee_ntd: 0,
      service_time: { start_time: '08:45', end_time: '16:45', end_day_offset: 0 } },
  } },
};

beforeEach(() => sessionClient.setSession('test-session', { id: 7, username: 'staff', display_name: 'Staff', role: 'admin' }));
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); sessionClient.clearSession(); });

describe('saved demand application review', () => {
  it('ignores a late response after changing source cases', async () => {
    vi.spyOn(client, 'pending').mockResolvedValue([]);
    vi.spyOn(client, 'nextNonCitizenNumber').mockResolvedValue({ case_no: 'A115001', virtual_account: '99781699115501' });
    let finishFirst: ((detail: ClientRegistryDetail) => void) | undefined;
    const first = new Promise<ClientRegistryDetail>(resolve => { finishFirst = resolve; });
    vi.spyOn(clientRegistryClient, 'query').mockReturnValueOnce(first).mockResolvedValueOnce({
      ...sourceDetail, case_no: '115000002',
      client: { ...sourceDetail.client, values: { ...sourceDetail.client.values, name: '新來源客戶' } },
    });
    const { rerender } = render(<RegistrationApplications sourceCaseNo="115000001" onEditStateChange={vi.fn()} />);
    rerender(<RegistrationApplications sourceCaseNo="115000002" onEditStateChange={vi.fn()} />);
    await screen.findByText(/資料來源案件：115000002/);
    fireEvent.change(screen.getByPlaceholderText('姓名'), { target: { value: '人員已核對' } });
    await act(async () => { finishFirst?.(sourceDetail); await first; });
    expect(screen.getByPlaceholderText('姓名')).toHaveValue('人員已核對');
    expect(screen.queryByText(/資料來源案件：115000001/)).not.toBeInTheDocument();
  });
  it('carries source fields into the manual form and creates a separate new case', async () => {
    vi.spyOn(client, 'pending').mockResolvedValue([]);
    vi.spyOn(client, 'nextNonCitizenNumber').mockResolvedValue({ case_no: 'A115001', virtual_account: '99781699115501' });
    const query = vi.spyOn(clientRegistryClient, 'query').mockResolvedValue(sourceDetail);
    const create = vi.spyOn(client, 'createManualNonCitizen').mockResolvedValue({
      case_no: 'A115001', virtual_account: '99781699115501', client_id: 21, message: '新案已建立',
    });
    render(<RegistrationApplications sourceCaseNo="115000001" onEditStateChange={vi.fn()} />);
    await screen.findByText(/資料來源案件：115000001/);
    expect(query).toHaveBeenCalledWith('115000001', expect.any(AbortSignal), true);
    expect(screen.getByPlaceholderText('姓名')).toHaveValue('來源客戶');
    expect(screen.getByLabelText('胎數')).toHaveValue('雙胞胎');
    expect(screen.getByLabelText('每日開始時間')).toHaveValue('08:45');
    expect(screen.getByLabelText('退款銀行帳號')).toHaveValue('000000000001');
    await screen.findByText('A115001');
    fireEvent.click(screen.getByRole('button', { name: '確認建立新案' }));
    await screen.findByText(/新案已建立/);
    expect(create).toHaveBeenCalledWith(expect.objectContaining({
      name: '來源客戶', identity_status: '非市民', service_days: 12,
      beclass_details: { ...sourceDetail.order_information.values, tel: '030000000', ext: '123', zip_code: '300', admin_notes: '已保存的報名備註' },
      service_time: '08:45-16:45 (8小時)', baby_info: '雙胞胎', line_id: '',
    }));
    expect(create.mock.calls[0][0]).not.toHaveProperty('line_user_id');
    expect(create.mock.calls[0][0]).not.toHaveProperty('client_id');
    expect(create.mock.calls[0][0]).not.toHaveProperty('case_no');
    expect(screen.queryByText(/資料來源案件/)).not.toBeInTheDocument();
  });

  it.each([
    ['08:00', '17:00', true],
    ['08:00', '16:00', true],
    ['08:00', '15:59', false],
    ['17:00', '08:00', false],
    ['', '17:00', false],
  ])('validates window %s–%s against selected 8 hours', async (start, end, accepted) => {
    vi.spyOn(client, 'pending').mockResolvedValue([]);
    vi.spyOn(client, 'nextNonCitizenNumber').mockResolvedValue({ case_no: 'A115001', virtual_account: '99781699115501' });
    vi.spyOn(clientRegistryClient, 'query').mockResolvedValue(sourceDetail);
    const create = vi.spyOn(client, 'createManualNonCitizen').mockResolvedValue({
      case_no: 'A115001', virtual_account: '99781699115501', client_id: 21, message: '新案已建立',
    });
    render(<RegistrationApplications sourceCaseNo="115000001" onEditStateChange={vi.fn()} />);
    await screen.findByText(/資料來源案件/);
    await screen.findByText('A115001');
    fireEvent.change(screen.getByLabelText('每日開始時間'), { target: { value: start } });
    fireEvent.change(screen.getByLabelText('每日結束時間'), { target: { value: end } });
    const form = screen.getByRole('button', { name: '確認建立新案' }).closest('form');
    if (!form) throw new Error('找不到建案表單');
    fireEvent.submit(form);
    if (accepted) {
      await screen.findByText(/新案已建立/);
      expect(create).toHaveBeenCalledWith(expect.objectContaining({ service_time: `${start}-${end} (8小時)` }));
    } else {
      expect(await screen.findByRole('alert')).toHaveTextContent('起訖時間差須至少涵蓋所選的 8 小時。');
      expect(create).not.toHaveBeenCalled();
    }
  });

  it('leaves masked refund values blank for staff to complete', async () => {
    vi.spyOn(client, 'pending').mockResolvedValue([]);
    vi.spyOn(client, 'nextNonCitizenNumber').mockResolvedValue({ case_no: 'A115001', virtual_account: '99781699115501' });
    vi.spyOn(clientRegistryClient, 'query').mockResolvedValue({ ...sourceDetail,
      beclass: { ...sourceDetail.beclass, full_refund_account_visible: false,
        values: sourceDetail.beclass.values && { ...sourceDetail.beclass.values, refund_account_no: '****0001' } },
    });
    const create = vi.spyOn(client, 'createManualNonCitizen');
    render(<RegistrationApplications sourceCaseNo="115000001" onEditStateChange={vi.fn()} />);
    await screen.findByText(/資料來源案件/);
    expect(screen.getByLabelText('退款銀行帳號')).toHaveValue('');
    expect(screen.getByLabelText('退款銀行帳號')).toBeRequired();
    await screen.findByText('A115001');
    const form = screen.getByRole('button', { name: '確認建立新案' }).closest('form');
    if (!form) throw new Error('找不到建案表單');
    fireEvent.submit(form);
    expect(await screen.findByRole('alert')).toHaveTextContent('退款銀行代號');
    expect(create).not.toHaveBeenCalled();
  });

  it('does not open an empty form when the source query fails', async () => {
    vi.spyOn(client, 'pending').mockResolvedValue([]);
    vi.spyOn(clientRegistryClient, 'query').mockRejectedValue(new Error('來源案件讀取失敗'));
    render(<RegistrationApplications sourceCaseNo="missing" onEditStateChange={vi.fn()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('來源案件讀取失敗');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
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
    await waitFor(() => expect(screen.getByRole('button', { name: '新增非市民案件' })).toBeEnabled());
    expect(screen.queryByRole('button', { name: '補登歷史非市民案件' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '新增非市民案件' }));
    expect(await screen.findByText('A115001')).toBeInTheDocument();
    expect(screen.getByText('99781699115501')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('例如 A113001')).not.toBeInTheDocument();
    expect(screen.getByLabelText('是否需要下廚')).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('姓名'), { target: { value: '測試客戶' } });
    fireEvent.change(screen.getByPlaceholderText('手機或市話'), { target: { value: '0912345678' } });
    fireEvent.change(screen.getByLabelText(/預計服務開始日/), { target: { value: '2026-12-01' } });
    fireEvent.change(screen.getByLabelText(/每日服務時數/), { target: { value: '08:30-16:30 (8小時)' } });
    const babyInfo = screen.getByRole('combobox', { name: '胎數' });
    expect(babyInfo).toBeRequired();
    expect(babyInfo).toHaveValue('');
    const holidayPreference = screen.getByRole('combobox', { name: /三節假日.*雙倍薪水/ });
    expect(holidayPreference).not.toBeRequired();
    expect(holidayPreference).toHaveValue('');
    fireEvent.change(holidayPreference, { target: { value: '否' } });
    expect(Array.from((babyInfo as HTMLSelectElement).options, option => option.value)).toEqual(['', '單胞胎', '雙胞胎']);
    fireEvent.change(babyInfo, { target: { value: '雙胞胎' } });
    for (const [label, value] of [
      ['電子郵件', 'synthetic@example.test'],
      ['退款銀行代號（7碼）', '0000001'],
      ['退款銀行帳號', '000000000001'],
    ]) {
      const field = screen.getByLabelText(label);
      expect(field).toBeRequired();
      expect(field).toHaveValue('');
      fireEvent.change(field, { target: { value } });
    }
    fireEvent.change(screen.getByLabelText('每日開始時間'), { target: { value: '08:45' } });
    fireEvent.click(screen.getByRole('button', { name: '確認建立新案' }));
    expect(await screen.findByText('起訖時間差須至少涵蓋所選的 8 小時。')).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('每日結束時間'), { target: { value: '16:45' } });
    fireEvent.click(screen.getByRole('button', { name: '確認建立新案' }));

    expect(await screen.findByText(/A115002.*99781699115502/)).toBeInTheDocument();
    expect(create.mock.calls[0][0]).toMatchObject({
      mode: 'new', service_time: '08:45-16:45 (8小時)', baby_info: '雙胞胎', holiday_double_pay: '否',
    });
    expect(create.mock.calls[0][0]).not.toHaveProperty('case_no');
    expect(create.mock.calls[0][0]).not.toHaveProperty('virtual_account');
  });
});
