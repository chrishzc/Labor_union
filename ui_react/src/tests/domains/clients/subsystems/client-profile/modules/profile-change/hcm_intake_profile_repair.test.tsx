import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { clientRegistryClient } from '../../../../../../../api/client_registry/client_registry_client';
import type { ClientRegistryDetail } from '../../../../../../../api/client_registry/client_registry_schemas';
import { HcmIntakeProfileRepairPanel } from '../../../../../../../components/HcmIntakeProfileRepairPanel';

const fingerprint = 'a'.repeat(64);
const detail: ClientRegistryDetail = {
  case_no: 'SYNTH-REPAIR',
  client: {
    client_id: 1, version: 2,
    values: { name: '測試客戶', gender: null, phone: null, city: null, address: null,
      residence_type: null, delivery_type: null, baby_info: null, notes: null, service_type: null },
    field_capabilities: {
      phone: { owner: 'client_profile', editable: true, reason: null, options: null },
      service_type: { owner: 'client_profile', editable: true, reason: null, options: ['連續服務', '休周六', '休周日', '週休2日'] },
    },
  },
  beclass: { status: 'unbound', record_id: null, source_kind: null, version: null, values: null, field_capabilities: {} },
  order_information: { status: 'unbound', values: null, field_issues: {} },
  finance: { status: 'not_ready', code: 'client_finance_bootstrap_required', values: null },
  order_terms: { status: 'not_ready', code: 'order_terms_incomplete', data: null, field_capabilities: {} },
};

beforeEach(() => {
  vi.spyOn(clientRegistryClient, 'query').mockResolvedValue(detail);
  vi.spyOn(clientRegistryClient, 'preview').mockResolvedValue({
    owner: 'client_profile', aggregate_identity: detail.case_no, current_version: 2,
    before: { phone: null, service_type: null }, after: { phone: '0912345678', service_type: '連續服務' },
    preview_fingerprint: fingerprint,
  });
  vi.spyOn(clientRegistryClient, 'apply').mockImplementation(async (caseNo, _owner, _changes, _version, fp, _reason, key) => ({
    owner: 'client_profile', aggregate_identity: caseNo, resulting_version: 3,
    changed_fields: ['phone', 'service_type'], preview_fingerprint: fp, idempotency_key: key!,
    replayed: false, readback: { phone: '0912345678', service_type: '連續服務' },
  }));
});
afterEach(() => vi.restoreAllMocks());

async function editAndPreview() {
  fireEvent.change(await screen.findByLabelText('行動電話'), { target: { value: '0912345678' } });
  fireEvent.change(screen.getByLabelText('服務方式'), { target: { value: '連續服務' } });
  fireEvent.change(screen.getByLabelText('欄位修正原因'), { target: { value: '補齊電話與服務方式' } });
  fireEvent.click(screen.getByRole('button', { name: '預覽欄位修正' }));
  await screen.findByLabelText('欄位修正前後');
}

it('repairs only the reviewed fields using versioned Preview/Apply and fresh readback', async () => {
  const onSaved = vi.fn().mockResolvedValue(undefined);
  const onBusy = vi.fn();
  render(<HcmIntakeProfileRepairPanel caseNo={detail.case_no} fields={['行動電話', '服務方式']} disabled={false} onSaved={onSaved} onBusyChange={onBusy} />);
  await editAndPreview();
  expect(clientRegistryClient.preview).toHaveBeenCalledWith(detail.case_no, 'profile', { phone: '0912345678', service_type: '連續服務' }, 2);
  expect(clientRegistryClient.apply).not.toHaveBeenCalled();
  vi.mocked(clientRegistryClient.query).mockResolvedValue({ ...detail, client: { ...detail.client, version: 3, values: { ...detail.client.values, phone: '0912345678', service_type: '連續服務' } } });
  fireEvent.click(screen.getByRole('button', { name: '確認儲存缺件資料' }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  expect(clientRegistryClient.apply).toHaveBeenCalledWith(detail.case_no, 'profile', { phone: '0912345678', service_type: '連續服務' }, 2, fingerprint, '補齊電話與服務方式', expect.stringContaining('hcm-intake-profile-'));
  await waitFor(() => expect(onBusy).toHaveBeenLastCalledWith(false));
});

it('invalidates the approved preview when a field is edited again', async () => {
  render(<HcmIntakeProfileRepairPanel caseNo={detail.case_no} fields={['行動電話', '服務方式']} disabled={false} onSaved={vi.fn()} onBusyChange={vi.fn()} />);
  await editAndPreview();
  fireEvent.change(screen.getByLabelText('服務方式'), { target: { value: '週休2日' } });
  expect(screen.queryByRole('button', { name: '確認儲存缺件資料' })).not.toBeInTheDocument();
  expect(clientRegistryClient.apply).not.toHaveBeenCalled();
});

it('keeps warnings and reads back without another write when the saved result is unconfirmed', async () => {
  const onSaved = vi.fn().mockResolvedValue(undefined);
  render(<HcmIntakeProfileRepairPanel caseNo={detail.case_no} fields={['行動電話', '服務方式']} disabled={false} onSaved={onSaved} onBusyChange={vi.fn()} />);
  await editAndPreview();
  fireEvent.click(screen.getByRole('button', { name: '確認儲存缺件資料' }));
  await screen.findByText('儲存結果尚未確認，請重新讀取修正結果。');
  expect(onSaved).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: '確認儲存缺件資料' })).toBeDisabled();
  vi.mocked(clientRegistryClient.query).mockResolvedValue({ ...detail, client: { ...detail.client, version: 3, values: { ...detail.client.values, phone: '0912345678', service_type: '連續服務' } } });
  fireEvent.click(screen.getByRole('button', { name: '重新讀取修正結果' }));
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  expect(clientRegistryClient.apply).toHaveBeenCalledTimes(1);
});

it('honors owner field capabilities instead of exposing a locked field', async () => {
  vi.mocked(clientRegistryClient.query).mockResolvedValue({ ...detail, client: { ...detail.client,
    field_capabilities: { ...detail.client.field_capabilities, service_type: { owner: 'client_profile', editable: false, reason: 'locked', options: ['連續服務'] } },
  } });
  render(<HcmIntakeProfileRepairPanel caseNo={detail.case_no} fields={['服務方式']} disabled={false} onSaved={vi.fn()} onBusyChange={vi.fn()} />);
  expect(await screen.findByLabelText('服務方式')).toBeDisabled();
  expect(screen.getByRole('button', { name: '預覽欄位修正' })).toBeDisabled();
});
