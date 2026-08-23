/**
 * File: staff_preferences_contract_fixtures.ts
 * Description: 提供 Staff 偏好去敏正向回應與 strict 負向契約 fixtures。
 */
import type {
  StaffPreferenceDefinition,
  StaffPreferenceProfile,
  StaffPreferenceProfileApplyReceipt,
  StaffPreferenceProfilePreview,
} from '../../../api/staff_preferences/staff_preferences_schemas';

const FINGERPRINT = 'a'.repeat(64);

export const STAFF_PREFERENCE_DEFINITIONS: StaffPreferenceDefinition[] = [
  {
    preference_key: 'preferred_service_days',
    display_name: '希望服務天數',
    value_kind: 'integer_range',
    is_filterable: true,
    order_fact_key: 'service_days',
    comparison_operator: 'range_with_tolerance',
    active: true,
    version: 1,
  },
  {
    preference_key: 'daily_service_hours',
    display_name: '每日服務時數',
    value_kind: 'integer_set',
    is_filterable: true,
    order_fact_key: 'service_hours_per_day',
    comparison_operator: 'contains_integer',
    active: true,
    version: 1,
  },
];

export const STAFF_PREFERENCE_PROFILE: StaffPreferenceProfile = {
  staff_id: 7,
  version: 4,
  values: [
    {
      preference_key: 'preferred_service_days',
      value: { kind: 'integer_range', minimum: 20, maximum: 30 },
    },
    {
      preference_key: 'daily_service_hours',
      value: { kind: 'integer_set', values: [4, 8] },
    },
  ],
};

export const STAFF_PREFERENCE_PROFILE_PREVIEW: StaffPreferenceProfilePreview = {
  staff_id: 7,
  before: STAFF_PREFERENCE_PROFILE.values,
  after: [
    {
      preference_key: 'preferred_service_days',
      value: { kind: 'integer_range', minimum: 22, maximum: 30 },
    },
    {
      preference_key: 'daily_service_hours',
      value: { kind: 'integer_set', values: [4, 8] },
    },
  ],
  version: 4,
  preview_fingerprint: FINGERPRINT,
};

export const STAFF_PREFERENCE_APPLY_RECEIPT: StaffPreferenceProfileApplyReceipt = {
  staff_id: 7,
  version: 5,
  values: STAFF_PREFERENCE_PROFILE_PREVIEW.after,
  preview_fingerprint: FINGERPRINT,
  idempotency_key: 'staff-preference-apply-01',
};

export const STAFF_PREFERENCE_PROFILE_FOR_STAFF_11: StaffPreferenceProfile = {
  ...STAFF_PREFERENCE_PROFILE,
  staff_id: 11,
};

export const STAFF_PREFERENCE_PREVIEW_FOR_STAFF_11: StaffPreferenceProfilePreview = {
  ...STAFF_PREFERENCE_PROFILE_PREVIEW,
  staff_id: 11,
};

export const STAFF_PREFERENCE_RECEIPT_FOR_STAFF_11: StaffPreferenceProfileApplyReceipt = {
  ...STAFF_PREFERENCE_APPLY_RECEIPT,
  staff_id: 11,
};

export const STAFF_PREFERENCE_DEFINITIONS_RESPONSE = {
  success: true,
  message: '成功取得月嫂偏好 definitions',
  data: STAFF_PREFERENCE_DEFINITIONS,
  error: null,
};

export const STAFF_PREFERENCE_PROFILE_RESPONSE = {
  success: true,
  message: '成功取得月嫂偏好 profile',
  data: STAFF_PREFERENCE_PROFILE,
  error: null,
};

export const STAFF_PREFERENCE_PROFILE_PREVIEW_RESPONSE = {
  success: true,
  message: '成功預覽月嫂偏好',
  data: STAFF_PREFERENCE_PROFILE_PREVIEW,
  error: null,
};

export const STAFF_PREFERENCE_APPLY_RECEIPT_RESPONSE = {
  success: true,
  message: '月嫂偏好已更新',
  data: STAFF_PREFERENCE_APPLY_RECEIPT,
  error: null,
};

export const STAFF_PREFERENCE_DEFINITIONS_EXTRA_FIELD_RESPONSE = {
  ...STAFF_PREFERENCE_DEFINITIONS_RESPONSE,
  unexpected: true,
};

export const STAFF_PREFERENCE_PROFILE_MISSING_VERSION_RESPONSE = {
  ...STAFF_PREFERENCE_PROFILE_RESPONSE,
  data: {
    staff_id: STAFF_PREFERENCE_PROFILE.staff_id,
    values: STAFF_PREFERENCE_PROFILE.values,
  },
};

export const STAFF_PREFERENCE_PREVIEW_NULL_FINGERPRINT_RESPONSE = {
  ...STAFF_PREFERENCE_PROFILE_PREVIEW_RESPONSE,
  data: {
    ...STAFF_PREFERENCE_PROFILE_PREVIEW,
    preview_fingerprint: null,
  },
};

export const STAFF_PREFERENCE_RECEIPT_EXTRA_FIELD_RESPONSE = {
  ...STAFF_PREFERENCE_APPLY_RECEIPT_RESPONSE,
  data: {
    ...STAFF_PREFERENCE_APPLY_RECEIPT,
    server_only: 'not-declared',
  },
};

export const STAFF_PREFERENCE_PROFILE_WRONG_VALUE_KIND_RESPONSE = {
  ...STAFF_PREFERENCE_PROFILE_RESPONSE,
  data: {
    ...STAFF_PREFERENCE_PROFILE,
    values: [
      {
        preference_key: 'preferred_service_days',
        value: { kind: 'decimal_range', minimum: 20, maximum: 30 },
      },
    ],
  },
};
