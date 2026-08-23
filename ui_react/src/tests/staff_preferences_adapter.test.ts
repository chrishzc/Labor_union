/**
 * File: staff_preferences_adapter.test.ts
 * Description: 驗證偏好 adapter 只暴露兩個核准欄位並保留 server value lineage。
 */
import { describe, expect, it } from 'vitest';
import { adaptStaffPreferencesProfile } from '../adapters/staff/staff_preferences_adapter';
import {
  STAFF_PREFERENCE_PROFILE,
} from './fixtures/staff/staff_preferences_contract_fixtures';

describe('staff preferences adapter', () => {
  it('maps only preferred service days and daily service hours', () => {
    const view = adaptStaffPreferencesProfile(STAFF_PREFERENCE_PROFILE);

    expect(view).toEqual({
      staffId: 7,
      version: 4,
      preferredServiceDays: {
        preference_key: 'preferred_service_days',
        value: { kind: 'integer_range', minimum: 20, maximum: 30 },
      },
      dailyServiceHours: {
        preference_key: 'daily_service_hours',
        value: { kind: 'integer_set', values: [4, 8] },
      },
    });
    expect(Object.keys(view)).toEqual([
      'staffId',
      'version',
      'preferredServiceDays',
      'dailyServiceHours',
    ]);
  });

  it('does not expose unsupported values and leaves missing approved slots null', () => {
    const view = adaptStaffPreferencesProfile({
      staff_id: 8,
      version: 1,
      values: [
        {
          preference_key: 'unapproved_preference',
          value: { kind: 'integer_set', values: [1] },
        },
      ],
    });

    expect(view.preferredServiceDays).toBeNull();
    expect(view.dailyServiceHours).toBeNull();
    expect(view).not.toHaveProperty('unapproved_preference');
  });
});
