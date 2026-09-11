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
    field_capabilities: {},
  },
  beclass: {
    status: 'ready' as const, record_id: 12, version: 3,
    values: { name: '王小明', email: null, phone: '0922222222', tel: null, ext: null, city: '新竹市', zip_code: null, address: null, admin_notes: null },
    field_capabilities: {},
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
});
