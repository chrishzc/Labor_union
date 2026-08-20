/**
 * File: hcm_import_result_fixtures.ts
 * Description: 提供 HCM recent-result strict deterministic fixture，不含真實個資或來源值。
 */
import type { HcmImportResultRecord } from '../../api/case_import/hcm_import_result_schemas';

export const detailedHcmResult: HcmImportResultRecord = {
  receipt_id: 8,
  completed_at: '2026-08-17T12:00:00',
  source_content_digest: 'a'.repeat(64),
  source_row_count: 3,
  inserted_count: 1,
  inserted_with_warning_count: 1,
  exact_replay_count: 1,
  review_required_count: 0,
  failed_count: 0,
  replayed_workbook: false,
  row_outcomes_available: true,
  legacy_summary_only: false,
  row_outcomes: [
    { source_row: 1, case_no: '115000001', outcome: 'inserted', problem_identity: null, problem_fields: [], issue_codes: [], referral_occurrence_identities: [] },
    { source_row: 2, case_no: '115000002', outcome: 'inserted_with_warning', problem_identity: 'review-2', problem_fields: ['行動電話'], issue_codes: ['hcm_field_invalid:行動電話'], referral_occurrence_identities: ['warning-2'] },
    { source_row: 3, case_no: '115000003', outcome: 'exact_replay', problem_identity: null, problem_fields: [], issue_codes: [], referral_occurrence_identities: [] },
  ],
};

