import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { staffCasePreferenceSummaryClient } from '../api/staff_case_preference_summary/staff_case_preference_summary_client';
import type {
  StaffCasePreferenceSummary,
} from '../api/staff_case_preference_summary/staff_case_preference_summary_schemas';
import { StaffCasePreferenceEditor } from '../components/StaffCasePreferenceEditor';

const INITIAL: StaffCasePreferenceSummary = {
  staff_id: 531,
  service_regions: { values: ['北區'], other_detail: null, other_detail_status: 'not_recorded' },
  service_periods: { values: ['8小時'], other_detail: null, other_detail_status: 'not_recorded' },
  rest_schedule: { values: ['週休1日'], other_detail: null, other_detail_status: 'not_recorded' },
  baby_counts: { values: ['雙胞胎'], other_detail: null, other_detail_status: 'not_recorded' },
  holiday_availability: { values: ['中秋節'], other_detail: null, other_detail_status: 'not_recorded' },
  transportation: { values: ['機車'], other_detail: null, other_detail_status: 'source_not_ready' },
};

const UPDATED: StaffCasePreferenceSummary = {
  ...INITIAL,
  service_regions: { values: ['北區', '新竹縣'], other_detail: null, other_detail_status: 'not_recorded' },
};

const FINGERPRINT = 'a'.repeat(64);

describe('StaffCasePreferenceEditor', () => {
  afterEach(() => vi.restoreAllMocks());

  it('edits the six-topic Staff snapshot through preview, apply, then owner re-query', async () => {
    const query = vi.spyOn(staffCasePreferenceSummaryClient, 'query')
      .mockResolvedValueOnce(INITIAL)
      .mockResolvedValueOnce(UPDATED);
    const preview = vi.spyOn(staffCasePreferenceSummaryClient, 'preview').mockResolvedValue({
      staff_id: 531,
      before: {
        service_regions: { values: ['北區'], other_detail: null },
        service_periods: { values: ['8小時'], other_detail: null },
        rest_schedule: { values: ['週休1日'], other_detail: null },
        baby_counts: { values: ['雙胞胎'], other_detail: null },
        holiday_availability: { values: ['中秋節'], other_detail: null },
        transportation: { values: ['機車'], other_detail: null },
      },
      after: {
        service_regions: { values: ['北區', '新竹縣'], other_detail: null },
        service_periods: { values: ['8小時'], other_detail: null },
        rest_schedule: { values: ['週休1日'], other_detail: null },
        baby_counts: { values: ['雙胞胎'], other_detail: null },
        holiday_availability: { values: ['中秋節'], other_detail: null },
        transportation: { values: ['機車'], other_detail: null },
      },
      preview_fingerprint: FINGERPRINT,
    });
    const apply = vi.spyOn(staffCasePreferenceSummaryClient, 'apply').mockResolvedValue({
      staff_id: 531,
      preview_fingerprint: FINGERPRINT,
      snapshot: {
        service_regions: { values: ['北區', '新竹縣'], other_detail: null },
        service_periods: { values: ['8小時'], other_detail: null },
        rest_schedule: { values: ['週休1日'], other_detail: null },
        baby_counts: { values: ['雙胞胎'], other_detail: null },
        holiday_availability: { values: ['中秋節'], other_detail: null },
        transportation: { values: ['機車'], other_detail: null },
      },
    });

    render(<StaffCasePreferenceEditor staffId={531} />);

    await screen.findByRole('button', { name: '編輯六項偏好' });
    fireEvent.click(screen.getByRole('button', { name: '編輯六項偏好' }));
    fireEvent.click(screen.getByRole('checkbox', { name: '新竹縣' }));
    fireEvent.click(screen.getByRole('button', { name: '預覽變更' }));

    await waitFor(() => expect(preview).toHaveBeenCalledTimes(1));
    expect(preview).toHaveBeenCalledWith(
      531,
      expect.objectContaining({
        service_regions: { values: ['北區', '新竹縣'], other_detail: null },
      }),
    );

    fireEvent.click(await screen.findByRole('button', { name: '確認儲存' }));

    await waitFor(() => expect(apply).toHaveBeenCalledTimes(1));
    expect(apply).toHaveBeenCalledWith(
      531,
      expect.objectContaining({ preview_fingerprint: FINGERPRINT }),
    );
    await waitFor(() => expect(query).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('北區、新竹縣')).toBeInTheDocument();
    expect(screen.queryByText('可承接服務天數範圍')).not.toBeInTheDocument();
    expect(screen.queryByText('可承接每日服務時數')).not.toBeInTheDocument();
  });
});
