import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import {
  StaffCasePreferenceManualEditor,
  StaffCasePreferenceManualPreview,
  updateManualDraftRow,
} from '../../../../../../../pages/StaffPage';
import { staffCasePreferenceManualClient } from '../../../../../../../api/staff_case_preferences/staff_case_preferences_client';
import { StaffCasePreferenceRelationsSchema } from '../../../../../../../api/staff_case_preferences/staff_case_preferences_schemas';
import { STAFF_MANUAL_OPTIONS } from '../../integration/fixtures/staff_manual_options';

const keys = ['service_regions', 'service_periods', 'cooking_skills', 'holiday_availability', 'rest_schedule', 'baby_types'] as const;
const labels = ['可承接區域', '可承接時段', '下廚能力', '特殊節日意願', '週間服務／排休', '可承接胎數／型態'] as const;
const relations = Object.fromEntries(keys.map((key) => [key, [{ value: '北區', detail: key === 'service_regions' ? '既有說明' : null }]]));
const snapshot = {
  staff_id: 531,
  before: relations,
  after: relations,
  snapshot_fingerprint: 'a'.repeat(64),
  preview_fingerprint: null,
};
const preview = {
  ...snapshot,
  after: { ...relations, service_regions: [{ value: '東區', detail: '新說明' }] },
  preview_fingerprint: 'b'.repeat(64),
};

afterEach(() => vi.restoreAllMocks());
beforeEach(() => { vi.spyOn(staffCasePreferenceManualClient, 'queryOptions').mockResolvedValue(STAFF_MANUAL_OPTIONS); });

describe('manual preference editor contract', () => {
  it('renders concrete before and after values/details', () => {
    render(<StaffCasePreferenceManualPreview preview={{ ...preview, before: relations, after: preview.after } as never} />);
    expect(screen.getByText(/可承接區域（變更前）: 北區/)).toBeTruthy();
    expect(screen.getByText(/可承接區域（變更後）: 東區/)).toBeTruthy();
    expect(screen.getByText(/既有說明/)).toBeTruthy();
    expect(screen.getByText(/新說明/)).toBeTruthy();
  });

  it('exposes only the six relation editors and gates Apply on preview plus reason', async () => {
    const query = vi.spyOn(staffCasePreferenceManualClient, 'query').mockResolvedValue(snapshot as never);
    const previewRequest = vi.spyOn(staffCasePreferenceManualClient, 'preview').mockResolvedValue(preview as never);
    const apply = vi.spyOn(staffCasePreferenceManualClient, 'apply').mockResolvedValue({
      staff_id: 531,
      relations: preview.after,
      snapshot_fingerprint: snapshot.snapshot_fingerprint,
      preview_fingerprint: preview.preview_fingerprint,
      idempotency_key: 'staff-manual-test',
      replayed: false,
    } as never);

    render(<StaffCasePreferenceManualEditor staffId={531} />);
    await waitFor(() => expect(query).toHaveBeenCalledWith(531, expect.objectContaining({ signal: expect.any(AbortSignal) })));
    fireEvent.click(await screen.findByRole('button', { name: '編輯六項偏好' }));
    for (const label of labels) {
      expect(screen.getByRole('combobox', { name: `${label}值1` })).toBeEnabled();
      expect(screen.queryByLabelText(`${label}說明1`)).not.toBeInTheDocument();
    }
    expect(screen.queryAllByRole('spinbutton')).toHaveLength(0);

    expect(screen.getByRole('button', { name: '確認儲存' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '確認儲存' })).toHaveAccessibleDescription('尚未預覽：請先按「預覽變更」。');
    fireEvent.click(screen.getByRole('button', { name: '確認儲存' }));
    expect(apply).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('可承接區域值1'), { target: { value: '東區' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    await waitFor(() => expect(previewRequest).toHaveBeenCalledWith(
      531,
      expect.objectContaining({ service_regions: [{ value: '東區', detail: null }] }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    await waitFor(() => expect(screen.getByText('預覽已完成，尚未寫入。')).toBeInTheDocument());
    const applyButton = screen.getByRole('button', { name: '確認儲存' });
    expect(applyButton).toBeDisabled();
    expect(applyButton).toHaveAccessibleDescription('預覽完成：請填寫「變更原因」後確認儲存。');

    fireEvent.change(screen.getByLabelText('六大接案能力變更原因'), { target: { value: '人工修正' } });
    expect(applyButton).toBeEnabled();
    expect(applyButton).toHaveAccessibleDescription('預覽與異動原因已完成，可以按「確認儲存」。');
    fireEvent.click(applyButton);
    await waitFor(() => expect(apply).toHaveBeenCalledWith(531, expect.objectContaining({
      expected_snapshot_fingerprint: snapshot.snapshot_fingerprint,
      preview_fingerprint: preview.preview_fingerprint,
      reason: '人工修正',
      service_regions: [{ value: '東區', detail: null }],
    }), expect.objectContaining({
      idempotencyKey: expect.stringContaining('staff-case-preference-'),
      signal: expect.any(AbortSignal),
    })));
  });

  it('keeps Apply zero-write before Preview and surfaces a stale owner rejection', async () => {
    const query = vi.spyOn(staffCasePreferenceManualClient, 'query').mockResolvedValue(snapshot as never);
    const previewRequest = vi.spyOn(staffCasePreferenceManualClient, 'preview').mockResolvedValue(preview as never);
    const apply = vi.spyOn(staffCasePreferenceManualClient, 'apply').mockRejectedValue(new Error('stale_snapshot'));

    render(<StaffCasePreferenceManualEditor staffId={531} />);
    await waitFor(() => expect(query).toHaveBeenCalledWith(531, expect.objectContaining({ signal: expect.any(AbortSignal) })));
    fireEvent.click(await screen.findByRole('button', { name: '編輯六項偏好' }));
    fireEvent.change(screen.getByLabelText('六大接案能力變更原因'), { target: { value: '人工修正' } });
    expect(screen.getByRole('button', { name: '確認儲存' })).toBeDisabled();
    expect(apply).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    await screen.findByText('預覽已完成，尚未寫入。');
    expect(previewRequest).toHaveBeenCalled();
    const applyButton = screen.getByRole('button', { name: '確認儲存' });
    fireEvent.click(applyButton);
    await waitFor(() => expect(apply).toHaveBeenCalled());
    expect(screen.getByText('stale_snapshot')).toBeInTheDocument();
  });

  it('preserves unchanged details and comma-containing values while editing rows', () => {
    const current = relations as never;
    const next = updateManualDraftRow(current, 'service_regions', 0, 'value', '其他,雙胞胎');
    expect(next.service_regions).toEqual([{ value: '其他,雙胞胎', detail: '既有說明' }]);
    expect(() => StaffCasePreferenceRelationsSchema.parse({ ...next, transportation: [] })).toThrow();
  });

  it('adds only one pending selection on demand and has no note editors', async () => {
    vi.spyOn(staffCasePreferenceManualClient, 'query').mockResolvedValue(snapshot as never);
    const previewRequest = vi.spyOn(staffCasePreferenceManualClient, 'preview').mockResolvedValue(preview as never);
    render(<StaffCasePreferenceManualEditor staffId={531} directEditing />);
    await screen.findByRole('combobox', { name: '可承接區域值1' });
    expect(screen.getAllByRole('combobox')).toHaveLength(7);
    fireEvent.change(screen.getByRole('combobox', { name: '可承接區域值1' }), { target: { value: '東區' } });
    fireEvent.change(screen.getByLabelText('六大接案能力變更原因'), { target: { value: '測試取消' } });
    fireEvent.click(screen.getByRole('button', { name: '取消變更' }));
    expect(screen.getByRole('combobox', { name: '可承接區域值1' })).toHaveValue('北區');
    expect(screen.getByLabelText('六大接案能力變更原因')).toHaveValue('');
    expect(screen.getByRole('button', { name: '確認儲存' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '預覽變更' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: '編輯六項偏好' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('下廚能力說明1')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /新增說明/ })).not.toBeInTheDocument();
    expect(screen.getByText('來源資料：既有說明')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '新增可承接區域條件' }));
    expect(screen.getAllByRole('combobox')).toHaveLength(8);
    expect(screen.getByRole('button', { name: '新增可承接區域條件' })).toBeDisabled();
    const next = screen.getByRole('combobox', { name: '可承接區域值2' });
    expect(next.querySelector('option[value="北區"]')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    expect(screen.getByText('請選擇新增條件，或移除尚未選擇的項目。')).toBeInTheDocument();
    expect(previewRequest).not.toHaveBeenCalled();
    fireEvent.change(next, { target: { value: '東區' } });
    expect(screen.queryByLabelText('可承接區域說明2')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    await screen.findByText('預覽已完成，尚未寫入。');
    fireEvent.click(screen.getByRole('button', { name: '移除可承接區域第2項' }));
    expect(screen.queryByTestId('staff-case-preference-manual-preview')).not.toBeInTheDocument();
    expect(screen.getAllByRole('combobox')).toHaveLength(7);
  });

  it('sends custom start/end times and explicit next day without writing a note', async () => {
    vi.spyOn(staffCasePreferenceManualClient, 'query').mockResolvedValue(snapshot as never);
    const previewRequest = vi.spyOn(staffCasePreferenceManualClient, 'preview').mockResolvedValue(preview as never);
    render(<StaffCasePreferenceManualEditor staffId={531} directEditing />);
    fireEvent.change(await screen.findByRole('combobox', { name: '可承接時段值1' }), { target: { value: '8小時' } });
    fireEvent.change(screen.getByLabelText('可承接時段開始時間1'), { target: { value: '08:30' } });
    fireEvent.change(screen.getByLabelText('可承接時段結束時間1'), { target: { value: '17:00' } });
    fireEvent.change(screen.getByRole('combobox', { name: '週間服務／排休值1' }), { target: { value: '休周六' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    await waitFor(() => expect(previewRequest).toHaveBeenCalledWith(531, expect.objectContaining({
      service_periods: [{ value: '8小時', detail: null, service_hours: 8, start_time: '08:30', end_time: '17:00', end_day_offset: 0 }], rest_schedule: [{ value: '休周六', detail: null }],
    }), expect.objectContaining({ signal: expect.any(AbortSignal) })));
    fireEvent.change(screen.getByRole('combobox', { name: '可承接時段值1' }), { target: { value: '4小時' } });
    fireEvent.change(screen.getByLabelText('可承接時段開始時間1'), { target: { value: '22:00' } });
    fireEvent.change(screen.getByLabelText('可承接時段結束時間1'), { target: { value: '02:00' } });
    fireEvent.change(screen.getByRole('combobox', { name: '可承接時段結束日1' }), { target: { value: '1' } });
    expect(screen.queryByTestId('staff-case-preference-manual-preview')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));
    await waitFor(() => expect(previewRequest).toHaveBeenLastCalledWith(531, expect.objectContaining({
      service_periods: [{ value: '4小時', detail: null, service_hours: 4, start_time: '22:00', end_time: '02:00', end_day_offset: 1 }],
    }), expect.anything()));
  });

  it('keeps the editor unavailable when option metadata cannot be loaded', async () => {
    vi.spyOn(staffCasePreferenceManualClient, 'query').mockResolvedValue(snapshot as never);
    vi.mocked(staffCasePreferenceManualClient.queryOptions).mockRejectedValueOnce(new Error('選項暫時無法載入'));
    render(<StaffCasePreferenceManualEditor staffId={531} directEditing />);
    await screen.findByText('選項暫時無法載入');
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '預覽變更' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新查詢' }));
    await screen.findByRole('combobox', { name: '可承接區域值1' });
  });
});
