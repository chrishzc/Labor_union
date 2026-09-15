import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ClientRegistryPage } from '../../../../../../../pages/ClientRegistryPage';

const mocks = vi.hoisted(() => ({ list: vi.fn(), query: vi.fn(), preview: vi.fn(), apply: vi.fn() }));
vi.mock('../../../../../../../api/client_registry/client_registry_client', () => ({ clientRegistryClient: mocks }));
vi.mock('../../../../../../../components/OrderTermsMutationPanel', () => ({ OrderTermsMutationPanel: () => <div>訂單條款 owner</div> }));

const detail = {
  case_no: 'CASE-001',
  client: {
    client_id: 7, version: 2,
    values: { name: '王小明', gender: null, phone: '0911111111', city: '新竹市', address: null, residence_type: null, delivery_type: null, baby_info: null, notes: null },
    field_capabilities: {
      name: { owner: 'client_profile', editable: true, reason: null, options: null },
      gender: { owner: 'client_profile', editable: true, reason: null, options: ['女', '男'] },
      phone: { owner: 'client_profile', editable: true, reason: null, options: null },
      city: { owner: 'client_profile', editable: true, reason: null, options: ['台北市', '新竹市'] },
      address: { owner: 'client_profile', editable: true, reason: null, options: null },
      residence_type: { owner: 'client_profile', editable: true, reason: null, options: ['電梯大樓', '公寓', '透天', '其他'] },
      delivery_type: { owner: 'client_profile', editable: true, reason: null, options: ['自然產', '剖腹產', '未定'] },
      baby_info: { owner: 'client_profile', editable: true, reason: null, options: null },
      notes: { owner: 'client_profile', editable: true, reason: null, options: null },
    },
  },
  beclass: {
    status: 'ready' as const, record_id: 12, source_kind: 'imported' as const, version: 3,
    values: { name: '王小明', email: null, phone: '0922222222', tel: null, ext: null, city: '新竹市', zip_code: null, address: null, admin_notes: null, multi_birth_count: '雙胞胎' },
    field_capabilities: {
      name: { owner: 'client_beclass', editable: true, reason: null, options: null },
      email: { owner: 'client_beclass', editable: true, reason: null, options: null },
      phone: { owner: 'client_beclass', editable: true, reason: null, options: null },
      tel: { owner: 'client_beclass', editable: true, reason: null, options: null },
      ext: { owner: 'client_beclass', editable: true, reason: null, options: null },
      city: { owner: 'client_beclass', editable: true, reason: null, options: null },
      zip_code: { owner: 'client_beclass', editable: true, reason: null, options: null },
      address: { owner: 'client_beclass', editable: true, reason: null, options: null },
      admin_notes: { owner: 'client_beclass', editable: true, reason: null, options: null },
      multi_birth_count: { owner: 'client_beclass', editable: true, reason: null, options: ['單胞胎', '雙胞胎'] },
    },
  },
  order_information: {
    status: 'ready' as const,
    values: {
      dietary_habits: '不吃牛肉', vegetarian_preference: null, alcohol_ratio: null,
      cooking_oil_type: null, maternal_allergy: null, special_care_notes: null,
      meal_preferences: null, cooking_tools: null, bath_water_prep: null,
      breastfeeding_method: null, holiday_pricing_terms: null, multi_birth_count: '雙胞胎',
      stair_floor_fee_mode: null, parking_space_provided: null, other_babies_present: null,
    },
    field_issues: {},
  },
  order_terms: { status: 'not_ready' as const, code: 'order_terms_incomplete', data: null, field_capabilities: {} },
};

describe('Client registry owner editing', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.list.mockResolvedValue({ items: [{ client_id: 7, case_no: 'CASE-001', name: '王小明', phone: '0911111111', city: '新竹市', planned_start_date: null, order_status: 'matching' }], next_cursor: null });
    mocks.query.mockResolvedValue(detail);
    mocks.preview.mockResolvedValue({ owner: 'client_profile', aggregate_identity: 'CASE-001', current_version: 2, before: { phone: '0911111111' }, after: { phone: '0933333333' }, preview_fingerprint: 'a'.repeat(64) });
    mocks.apply.mockResolvedValue({ owner: 'client_profile', aggregate_identity: 'CASE-001', resulting_version: 3, changed_fields: ['phone'], preview_fingerprint: 'a'.repeat(64), idempotency_key: 'client-profile-1', replayed: false, readback: { phone: '0933333333' } });
  });

  it('cancels without writing and applies a preview with one stable idempotency key', async () => {
    render(<ClientRegistryPage />);
    expect(screen.getByRole('tab', { name: '客戶清單' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByRole('heading', { name: '客戶主檔' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '名冊資料' }));
    expect(screen.getByRole('tab', { name: '名冊資料' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.click(await screen.findByRole('button', { name: /CASE-001/ }));
    const profile = (await screen.findByRole('heading', { name: '客戶主檔' })).closest('section') as HTMLElement;
    const phone = within(profile).getByLabelText('手機');

    fireEvent.change(phone, { target: { value: '0933333333' } });
    fireEvent.click(within(profile).getByRole('button', { name: '取消變更' }));
    expect(phone).toHaveValue('0911111111');
    expect(mocks.preview).not.toHaveBeenCalled();
    expect(mocks.apply).not.toHaveBeenCalled();

    fireEvent.change(phone, { target: { value: '0933333333' } });
    fireEvent.click(within(profile).getByRole('button', { name: '預覽變更' }));
    await waitFor(() => expect(mocks.preview).toHaveBeenCalledWith('CASE-001', 'profile', { phone: '0933333333' }, 2));
    expect(within(profile).queryByLabelText('異動原因')).not.toBeInTheDocument();
    fireEvent.click(within(profile).getByRole('button', { name: '確認儲存' }));
    await waitFor(() => expect(mocks.apply).toHaveBeenCalledTimes(1));
    expect(mocks.apply.mock.calls[0][5]).toBe('後台客戶名冊主檔更新');
    expect(mocks.apply.mock.calls[0][6]).toMatch(/^client-profile-/);
    await screen.findByText('客戶主檔已儲存。');
  });

  it('uses selects for enum fields and keeps free-text fields as inputs', async () => {
    render(<ClientRegistryPage />);
    fireEvent.click(screen.getByRole('tab', { name: '名冊資料' }));
    fireEvent.click(await screen.findByRole('button', { name: /CASE-001/ }));

    const profile = (await screen.findByRole('heading', { name: '客戶主檔' })).closest('section') as HTMLElement;
    expect(within(profile).getByRole('combobox', { name: '性別' })).toHaveValue('');
    expect(within(profile).getByRole('combobox', { name: '縣市' })).toHaveValue('新竹市');
    expect(within(profile).getByRole('combobox', { name: '住宅型態' })).toBeInTheDocument();
    expect(within(profile).getByRole('combobox', { name: '生產方式' })).toBeInTheDocument();
    expect(within(profile).getByRole('textbox', { name: '手機' })).toBeInTheDocument();
    const beclass = (await screen.findByRole('heading', { name: 'BeClass 有效資料' })).closest('section') as HTMLElement;
    const birthCount = within(beclass).getByRole('combobox', { name: '胎數（單胞胎／雙胞胎）' });
    expect(birthCount).toHaveValue('雙胞胎');
    fireEvent.change(birthCount, { target: { value: '單胞胎' } });
    fireEvent.click(within(beclass).getByRole('button', { name: '預覽變更' }));
    await waitFor(() => expect(mocks.preview).toHaveBeenCalledWith('CASE-001', 'beclass', { multi_birth_count: '單胞胎' }, 3));
    const information = (await screen.findByRole('heading', { name: '照護與特殊計費資料' })).closest('section') as HTMLElement;
    expect(within(information).getByText('飲食習慣與中藥接受度')).toBeInTheDocument();
    expect(within(information).getByText('不吃牛肉')).toBeInTheDocument();
    expect(information).not.toHaveTextContent('survey_details');
  });

  it('shows editable blank fields for any case without imported BeClass data', async () => {
    mocks.query.mockResolvedValue({
      ...detail,
      beclass: {
        ...detail.beclass,
        record_id: null,
        source_kind: 'admin_manual',
        version: 0,
        values: Object.fromEntries(Object.keys(detail.beclass.values).map((field) => [field, null])),
      },
      order_information: {
        ...detail.order_information,
        values: Object.fromEntries(Object.keys(detail.order_information.values).map((field) => [field, null])),
      },
    });
    render(<ClientRegistryPage />);
    fireEvent.click(screen.getByRole('tab', { name: '名冊資料' }));
    fireEvent.click(await screen.findByRole('button', { name: /CASE-001/ }));

    const beclass = (await screen.findByRole('heading', { name: 'BeClass 有效資料' })).closest('section') as HTMLElement;
    expect(within(beclass).getByText('資料來源：後台人工補登（無 BeClass 匯入紀錄）')).toBeInTheDocument();
    expect(within(beclass).getByRole('textbox', { name: '報名姓名' })).toHaveValue('');
    expect(within(beclass).getByRole('combobox', { name: '胎數（單胞胎／雙胞胎）' })).toHaveValue('');
    expect(screen.queryByText(/尚未綁定 BeClass/)).not.toBeInTheDocument();
  });

  it('loads every registry selector page so search results are not capped at 100 cases', async () => {
    mocks.list.mockImplementation(async (request = {}) => {
      if (request.after === 'CASE-100') {
        return {
          items: [{ client_id: 108, case_no: 'CASE-108', name: '目標客戶', phone: '0988000000', city: '新竹市', planned_start_date: null, order_status: '洽談中' }],
          next_cursor: null,
        };
      }
      return {
        items: [{ client_id: 100, case_no: 'CASE-100', name: '第一頁客戶', phone: '0911000000', city: '新竹市', planned_start_date: null, order_status: '洽談中' }],
        next_cursor: 'CASE-100',
      };
    });

    render(<ClientRegistryPage />);
    fireEvent.click(screen.getByRole('tab', { name: '名冊資料' }));

    expect(await screen.findByRole('button', { name: /CASE-108/ })).toBeInTheDocument();
    expect(mocks.list).toHaveBeenCalledWith(expect.objectContaining({ limit: 100, after: 'CASE-100' }));
  });
});
