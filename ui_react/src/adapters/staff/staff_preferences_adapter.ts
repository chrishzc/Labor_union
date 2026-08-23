/**
 * File: staff_preferences_adapter.ts
 * Description: 將 Staff profile 僅映射為兩個核准偏好欄位，禁止補造其他業務事實。
 */
import type {
  StaffPreferenceProfile,
  StaffPreferenceValueView,
} from '../../api/staff_preferences/staff_preferences_schemas';

export interface StaffPreferencesProfileViewModel {
  staffId: number;
  version: number;
  preferredServiceDays: StaffPreferenceValueView | null;
  dailyServiceHours: StaffPreferenceValueView | null;
}

export function adaptStaffPreferencesProfile(
  profile: StaffPreferenceProfile,
): StaffPreferencesProfileViewModel {
  let preferredServiceDays: StaffPreferenceValueView | null = null;
  let dailyServiceHours: StaffPreferenceValueView | null = null;

  for (const item of profile.values) {
    if (item.preference_key === 'preferred_service_days') {
      preferredServiceDays = item;
    } else if (item.preference_key === 'daily_service_hours') {
      dailyServiceHours = item;
    }
  }

  return {
    staffId: profile.staff_id,
    version: profile.version,
    preferredServiceDays,
    dailyServiceHours,
  };
}

export const adaptStaffPreferenceProfile = adaptStaffPreferencesProfile;
