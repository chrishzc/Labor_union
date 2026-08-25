/**
 * File: staff_qualification_contract_fixtures.ts
 * Description: 提供 Staff qualification 六區段的去敏 typed 測試資料。
 */
import type { StaffQualificationMaster } from '../../../api/staff/qualification_master_schemas';

export const STAFF_QUALIFICATION_MASTER: StaffQualificationMaster = {
  staff_id: 11,
  staff_name: '去敏人員甲',
  as_of: '2026-08-23',
  overall_availability: 'partial',
  availability_reason: 'qualification_sources_partial',
  service_profile: {
    care_babies: 2,
    service_regions: [{ value: '北區', detail: null }, { value: '其他', detail: '新竹市' }],
    service_time_slots: [{ value: '8小時', detail: null }],
    transportation: [{ value: '機車', detail: null }],
    holiday_availability: [{ value: '中秋節', detail: null }],
    weekly_rest: [{ value: '週休1日', detail: null }],
    baby_types: [{ value: '單胞胎', detail: null }, { value: '雙胞胎', detail: null }],
  },
  sections: [
    'skills',
    'cooking',
    'certifications',
    'medical',
    'validity',
    'unavailability',
  ].map((kind) => ({
    kind: kind as StaffQualificationMaster['sections'][number]['kind'],
    owner: 'Staff',
    availability: 'unavailable' as const,
    availability_reason: 'qualification_source_empty',
    source_identity: null,
    source_version: null,
    items: [],
  })),
};

export const STAFF_QUALIFICATION_RESPONSE = {
  success: true,
  message: '成功取得資格主檔',
  data: STAFF_QUALIFICATION_MASTER,
  error: null,
};
