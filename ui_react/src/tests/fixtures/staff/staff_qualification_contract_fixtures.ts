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
