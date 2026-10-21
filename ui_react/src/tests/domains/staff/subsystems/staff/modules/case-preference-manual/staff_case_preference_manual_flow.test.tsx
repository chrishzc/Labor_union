import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { StaffCasePreferenceManualEditor, StaffCasePreferenceManualPreview, updateManualDraftRow } from '../../../../../../../pages/StaffPage';
import { staffCasePreferenceManualClient } from '../../../../../../../api/staff_case_preferences/staff_case_preferences_client';
import { StaffCasePreferenceRelationsSchema } from '../../../../../../../api/staff_case_preferences/staff_case_preferences_schemas';
import type { StaffCasePreferenceRelations } from '../../../../../../../api/staff_case_preferences/staff_case_preferences_schemas';
import { STAFF_MANUAL_OPTIONS } from '../../integration/fixtures/staff_manual_options';

const relations: StaffCasePreferenceRelations = {
  service_regions: [{ value: '北區', detail: '原區域說明' }],
  rest_schedule: [{ value: '週休二日', detail: null }],
  service_periods: [{ value: '8小時(08:30-17:00)', detail: null, service_hours: 8, start_time: '08:30', end_time: '17:00', end_day_offset: 0 }],
  cooking_skills: [{ value: '其他', detail: '家常料理，保留原說明' }],
  holiday_availability: [{ value: '中秋節', detail: '需事先協調' }],
  baby_types: [{ value: '雙胞胎', detail: '原胎數說明' }],
};
const snapshot = { staff_id: 531, before: relations, after: relations, snapshot_fingerprint: 'a'.repeat(64), preview_fingerprint: null };
const preview = { ...snapshot, after: { ...relations, service_regions: [{ value: '東區', detail: null }] }, preview_fingerprint: 'b'.repeat(64) };

afterEach(() => vi.restoreAllMocks());
beforeEach(() => {
  vi.spyOn(staffCasePreferenceManualClient, 'query').mockResolvedValue(snapshot);
  vi.spyOn(staffCasePreferenceManualClient, 'queryOptions').mockResolvedValue(STAFF_MANUAL_OPTIONS);
  vi.spyOn(staffCasePreferenceManualClient, 'preview').mockResolvedValue(preview);
  vi.spyOn(staffCasePreferenceManualClient, 'apply').mockResolvedValue({ staff_id: 531, relations, snapshot_fingerprint: 'c'.repeat(64), preview_fingerprint: 'b'.repeat(64), idempotency_key: 'synthetic-preference', replayed: false });
});

describe('two informational service preferences and preserved imported facts', () => {
  it('offers only Hsinchu districts for new rows and preserves an existing retired region on save', async () => {
    const existing = { ...relations, service_regions: [{ value: '台北市', detail: '原匯入說明' }], rest_schedule: [{ value: '週一至週五', detail: '原排休說明' }] };
    vi.mocked(staffCasePreferenceManualClient.query).mockResolvedValue({ ...snapshot, before: existing, after: existing });
    render(<StaffCasePreferenceManualEditor staffId={531} directEditing />);
    const region = await screen.findByLabelText('可承接區域值1');
    expect(region).toHaveValue('台北市');
    expect(within(region).getByRole('option', { name: '既有值：台北市' })).toBeInTheDocument();
    const weekly = screen.getByLabelText('週間服務值1');
    expect(weekly).toHaveValue('週一至週五');
    expect(within(weekly).getByRole('option', { name: '既有值：週一至週五' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '新增週間服務條件' }));
    const weeklyAdded = screen.getByLabelText('週間服務值2');
    expect(Array.from(weeklyAdded.querySelectorAll('option')).map(option => option.value).filter(Boolean)).toEqual(['週休一日', '週休二日', '連續服務']);
    fireEvent.click(screen.getByRole('button', { name: '移除週間服務第2項' }));
    fireEvent.click(screen.getByRole('button', { name: '新增可承接區域條件' }));
    const added = screen.getByLabelText('可承接區域值2');
    expect(within(added).getAllByRole('option')).toHaveLength(17);
    for (const value of ['竹北市', '五峰鄉', '香山區']) expect(within(added).getByRole('option', { name: value })).toBeInTheDocument();
    for (const value of ['台北市', '新竹市', '新竹縣']) expect(within(added).queryByRole('option', { name: value })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '移除可承接區域第2項' }));
    fireEvent.click(screen.getByRole('button', { name: '儲存服務偏好' }));
    await waitFor(() => expect(staffCasePreferenceManualClient.apply).toHaveBeenCalledWith(531, expect.objectContaining(existing), expect.anything()));
    await screen.findByText('已儲存並重新查詢服務偏好。');
  });

  it('renders concrete before/after values and preserves source details', () => {
    render(<StaffCasePreferenceManualPreview preview={preview} />);
    expect(screen.getByText(/可承接區域（變更前）: 北區（原區域說明）/)).toBeInTheDocument();
    expect(screen.getByText(/可承接區域（變更後）: 東區/)).toBeInTheDocument();
    expect(screen.queryByText(/可承接時段/)).not.toBeInTheDocument();
  });

  it.each(['', '   ', '人工修正'])('previews before applying, preserves four imported relations and optional reason %j', async note => {
    render(<StaffCasePreferenceManualEditor staffId={531} directEditing />);
    fireEvent.change(await screen.findByLabelText('可承接區域值1'), { target: { value: '東區' } });
    fireEvent.change(screen.getByLabelText('接案條件備註（選填）'), { target: { value: note } });
    fireEvent.click(screen.getByRole('button', { name: '儲存服務偏好' }));
    await waitFor(() => expect(staffCasePreferenceManualClient.apply).toHaveBeenCalledWith(531, expect.objectContaining({
      ...relations, service_regions: [{ value: '東區', detail: null }], reason: note.trim(),
      expected_snapshot_fingerprint: snapshot.snapshot_fingerprint, preview_fingerprint: preview.preview_fingerprint,
    }), expect.objectContaining({ idempotencyKey: expect.stringContaining('staff-case-preference-'), signal: expect.any(AbortSignal) })));
    expect(vi.mocked(staffCasePreferenceManualClient.preview).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(staffCasePreferenceManualClient.apply).mock.invocationCallOrder[0]!);
    await screen.findByText('已儲存並重新查詢服務偏好。');
  });

  it('does not apply on preview failure and surfaces stale rejection without success', async () => {
    vi.mocked(staffCasePreferenceManualClient.preview).mockRejectedValueOnce(new Error('stale_snapshot'));
    render(<StaffCasePreferenceManualEditor staffId={531} directEditing />);
    await screen.findByLabelText('可承接區域值1');
    fireEvent.click(screen.getByRole('button', { name: '儲存服務偏好' }));
    await screen.findByText('stale_snapshot');
    expect(staffCasePreferenceManualClient.apply).not.toHaveBeenCalled();
    expect(screen.queryByText('已儲存並重新查詢服務偏好。')).not.toBeInTheDocument();
  });

  it('preserves unchanged details and comma-containing values while editing rows', () => {
    const next = updateManualDraftRow(relations, 'service_regions', 0, 'value', '東區');
    expect(next.service_regions[0]?.detail).toBe('原區域說明');
    expect(next.cooking_skills).toEqual(relations.cooking_skills);
    expect(StaffCasePreferenceRelationsSchema.parse(next).cooking_skills[0]?.detail).toBe('家常料理，保留原說明');
  });

  it('adds one pending choice, blocks incomplete save and cancels to the original two fields', async () => {
    render(<StaffCasePreferenceManualEditor staffId={531} directEditing />);
    await screen.findByLabelText('可承接區域值1');
    const preferences = within(screen.getByRole('region', { name: '服務偏好' }));
    expect(preferences.getAllByRole('group')).toHaveLength(2);
    expect(preferences.getAllByRole('combobox')).toHaveLength(2);
    fireEvent.click(preferences.getByRole('button', { name: '新增可承接區域條件' }));
    expect(preferences.getByRole('button', { name: '新增可承接區域條件' })).toBeDisabled();
    expect(screen.getByLabelText('可承接區域值2').querySelector('option[value="北區"]')).toBeDisabled();
    fireEvent.click(preferences.getByRole('button', { name: '儲存服務偏好' }));
    expect(screen.getByText('請選擇新增條件，或移除尚未選擇的項目。')).toBeInTheDocument();
    expect(staffCasePreferenceManualClient.preview).not.toHaveBeenCalled();
    fireEvent.click(preferences.getByRole('button', { name: '取消變更' }));
    expect(preferences.getAllByRole('combobox')).toHaveLength(2);
    expect(screen.getByLabelText('可承接區域值1')).toHaveValue('北區');
  });

  it('shows all four imported topics read-only under professional data, outside preferences', async () => {
    render(<StaffCasePreferenceManualEditor staffId={531} directEditing />);
    await screen.findByLabelText('可承接區域值1');
    const information = within(screen.getByRole('region', { name: '專業資格與服務資料' }));
    for (const value of ['8小時(08:30-17:00)', '其他（家常料理，保留原說明）', '中秋節（需事先協調）', '雙胞胎（原胎數說明）']) expect(information.getByText(value)).toBeInTheDocument();
    expect(information.queryAllByRole('combobox')).toHaveLength(0);
    expect(screen.queryByLabelText('可承接時段開始時間1')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('下廚能力值1')).not.toBeInTheDocument();
  });

  it('keeps preferences unavailable on option failure and allows reload', async () => {
    vi.mocked(staffCasePreferenceManualClient.queryOptions).mockRejectedValueOnce(new Error('選項暫時無法載入'));
    render(<StaffCasePreferenceManualEditor staffId={531} directEditing />);
    await screen.findByText('選項暫時無法載入');
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新查詢' }));
    await screen.findByLabelText('可承接區域值1');
  });
});
