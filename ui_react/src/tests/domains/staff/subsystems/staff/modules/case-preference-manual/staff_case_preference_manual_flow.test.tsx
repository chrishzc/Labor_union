import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import {
  StaffCasePreferenceManualEditor,
  StaffCasePreferenceManualPreview,
  updateManualDraftRow,
} from '../../../../../../../pages/StaffPage';
import { staffCasePreferenceManualClient } from '../../../../../../../api/staff_case_preferences/staff_case_preferences_client';
import { StaffCasePreferenceRelationsSchema } from '../../../../../../../api/staff_case_preferences/staff_case_preferences_schemas';

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
    await waitFor(() => expect(query).toHaveBeenCalledWith(531));
    for (const label of labels) {
      expect(screen.getByLabelText(`${label}值1`)).toBeEnabled();
      expect(screen.getByLabelText(`${label}說明1`)).toBeEnabled();
    }
    expect(screen.queryAllByRole('spinbutton')).toHaveLength(0);

    const applyButton = screen.getByRole('button', { name: '套用六大能力' });
    expect(applyButton).toBeDisabled();
    fireEvent.change(screen.getByLabelText('可承接區域值1'), { target: { value: '東區' } });
    fireEvent.change(screen.getByLabelText('可承接區域說明1'), { target: { value: '新說明' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽六大能力' }));
    await waitFor(() => expect(previewRequest).toHaveBeenCalledWith(531, expect.objectContaining({
      service_regions: [{ value: '東區', detail: '新說明' }],
    })));
    await waitFor(() => expect(screen.getByText('預覽已完成，尚未寫入。')).toBeInTheDocument());
    expect(applyButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText('六大接案能力變更原因'), { target: { value: '人工修正' } });
    expect(applyButton).toBeEnabled();
    fireEvent.click(applyButton);
    await waitFor(() => expect(apply).toHaveBeenCalledWith(531, expect.objectContaining({
      expected_snapshot_fingerprint: snapshot.snapshot_fingerprint,
      preview_fingerprint: preview.preview_fingerprint,
      reason: '人工修正',
      service_regions: [{ value: '東區', detail: '新說明' }],
    }), expect.objectContaining({ idempotencyKey: expect.stringContaining('staff-case-preference-') })));
  });

  it('keeps Apply zero-write before Preview and surfaces a stale owner rejection', async () => {
    const query = vi.spyOn(staffCasePreferenceManualClient, 'query').mockResolvedValue(snapshot as never);
    const previewRequest = vi.spyOn(staffCasePreferenceManualClient, 'preview').mockResolvedValue(preview as never);
    const apply = vi.spyOn(staffCasePreferenceManualClient, 'apply').mockRejectedValue(new Error('stale_snapshot'));

    render(<StaffCasePreferenceManualEditor staffId={531} />);
    await waitFor(() => expect(query).toHaveBeenCalledWith(531));
    fireEvent.change(screen.getByLabelText('六大接案能力變更原因'), { target: { value: '人工修正' } });
    const applyButton = screen.getByRole('button', { name: '套用六大能力' });
    expect(applyButton).toBeDisabled();
    expect(apply).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '預覽六大能力' }));
    await waitFor(() => expect(previewRequest).toHaveBeenCalled());
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
});
