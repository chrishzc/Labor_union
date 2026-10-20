/**
 * File: case_workbook_adapters.test.ts
 * Description: 驗證Case Workbook Preview投影、terminal守恆與Historical Orders review overlay。
 */
import { describe, expect, it } from 'vitest';
import { adaptClientBeClassWorkbookPreview } from '../adapters/case_import/client_beclass_workbook_adapter';
import { adaptStaffHistoricalWorkbookPreview } from '../adapters/case_import/staff_historical_workbook_adapter';
import { adaptHistoricalOrderWorkbookPreview } from '../adapters/orders/historical_order_workbook_adapter';
import { adaptClientBeClassImportResult, adaptHcmImportResult, adaptHistoricalOrderImportResult, adaptStaffHistoricalImportResult } from '../adapters/workbook_import_result_adapter';

const digest = 'a'.repeat(64);
const identity = 'b'.repeat(64);
const fingerprint = 'c'.repeat(64);
const statusCounts = { cancelled_0: 1, deposit_paid_1: 1, discussion_2: 1, invalid_or_blank: 1 };
const resultCounts = { not_adopted: 1, matching_pending_deposit: 1, historical_unserved: 1, historical_in_service: 1, historical_service_completed: 0 };

describe('Case workbook Preview adapters', () => {
  it('投影三個互不混用的aggregate contract', () => {
    expect(adaptClientBeClassWorkbookPreview({ source_content_digest: digest, sheet_identity: identity, source_row_count: 4, create_count: 1, review_required_count: 1, existing_conflict_count: 1, existing_source_count: 1, preview_fingerprint: fingerprint }).createCount).toBe(1);
    expect(adaptStaffHistoricalWorkbookPreview({ source_content_digest: digest, source_row_count: 4, created_count: 1, adopted_existing_count: 1, blocked_identity_count: 1, identity_conflict_count: 1, review_required_count: 1, preview_fingerprint: fingerprint }).adoptedExistingCount).toBe(1);
    const historical = adaptHistoricalOrderWorkbookPreview({ source_content_digest: digest, sheet_identity: identity, source_row_count: 4, adopted_count: 2, unmatched_case_count: 1, review_required_count: 1, current_conflict_count: 1, assignment_candidate_count: 1, evidence_only_pairing_count: 1, absent_order_cancellation_count: 0, status_counts: statusCounts, result_counts: resultCounts, preview_fingerprint: fingerprint, row_issues: [] });
    expect(historical.assignmentCandidateCount).toBe(1);
    expect(historical.statusCounts.depositPaid1).toBe(1);
  });

  it('Historical Orders review_required是adopted row overlay，不重複計入terminal總數', () => {
    const model = adaptHistoricalOrderWorkbookPreview({ source_content_digest: digest, sheet_identity: identity, source_row_count: 1, adopted_count: 1, unmatched_case_count: 0, review_required_count: 1, current_conflict_count: 0, assignment_candidate_count: 0, evidence_only_pairing_count: 1, absent_order_cancellation_count: 0, status_counts: { ...statusCounts, cancelled_0: 0, discussion_2: 0, invalid_or_blank: 0 }, result_counts: { ...resultCounts, not_adopted: 0, matching_pending_deposit: 0, historical_in_service: 0 }, preview_fingerprint: fingerprint, row_issues: [] });
    expect(model.adoptedCount).toBe(1);
    expect(model.reviewRequiredCount).toBe(1);
  });

  it('Historical Orders接受invalid status形成的terminal review row', () => {
    const model = adaptHistoricalOrderWorkbookPreview({ source_content_digest: digest, sheet_identity: identity, source_row_count: 1, adopted_count: 0, unmatched_case_count: 0, review_required_count: 1, current_conflict_count: 0, assignment_candidate_count: 0, evidence_only_pairing_count: 0, absent_order_cancellation_count: 0, status_counts: { cancelled_0: 0, deposit_paid_1: 0, discussion_2: 0, invalid_or_blank: 1 }, result_counts: { not_adopted: 1, matching_pending_deposit: 0, historical_unserved: 0, historical_in_service: 0, historical_service_completed: 0 }, preview_fingerprint: fingerprint, row_issues: [] });
    expect(model.reviewRequiredCount).toBe(1);
  });

  it('拒絕來源列數不守恆', () => {
    expect(() => adaptClientBeClassWorkbookPreview({ source_content_digest: digest, sheet_identity: identity, source_row_count: 9, create_count: 1, review_required_count: 1, existing_conflict_count: 1, existing_source_count: 1, preview_fingerprint: fingerprint })).toThrow(/不守恆/);
    expect(() => adaptStaffHistoricalWorkbookPreview({ source_content_digest: digest, source_row_count: 9, created_count: 1, adopted_existing_count: 1, blocked_identity_count: 1, identity_conflict_count: 1, review_required_count: 1, preview_fingerprint: fingerprint })).toThrow(/不守恆/);
    expect(() => adaptHistoricalOrderWorkbookPreview({ source_content_digest: digest, sheet_identity: identity, source_row_count: 9, adopted_count: 2, unmatched_case_count: 1, review_required_count: 1, current_conflict_count: 0, assignment_candidate_count: 1, evidence_only_pairing_count: 1, absent_order_cancellation_count: 0, status_counts: statusCounts, result_counts: resultCounts, preview_fingerprint: fingerprint, row_issues: [] })).toThrow(/不守恆/);
  });

  it('拒絕0、1、2與空白狀態計數不守恆', () => {
    expect(() => adaptHistoricalOrderWorkbookPreview({ source_content_digest: digest, sheet_identity: identity, source_row_count: 4, adopted_count: 2, unmatched_case_count: 1, review_required_count: 1, current_conflict_count: 1, assignment_candidate_count: 1, evidence_only_pairing_count: 1, absent_order_cancellation_count: 0, status_counts: { ...statusCounts, invalid_or_blank: 0 }, result_counts: resultCounts, preview_fingerprint: fingerprint, row_issues: [] })).toThrow(/狀態判定計數不守恆/);
  });
});

describe('Four mutually exclusive import result counters', () => {
  it('preserves a non-imported HCM row without a case number and rejects incomplete claimed detail', () => {
    const receipt = { source_content_digest: digest, source_row_count: 1, inserted_count: 0, inserted_with_warning_count: 0, exact_replay_count: 0, skipped_existing_count: 0, review_required_count: 1, failed_count: 0, replayed_workbook: false, row_outcomes_available: true, legacy_summary_only: false,
      row_outcomes: [{ source_row: 3, case_no: null, outcome: 'review_required' as const, problem_identity: null, problem_fields: ['案件編號'], issue_codes: ['hcm_case_import:case_import_case_no_required'], referral_occurrence_identities: [] }] };
    expect(adaptHcmImportResult(receipt).notImportedRows).toEqual([{ sourceRow: 3, identifier: null, fields: ['案件編號'], reasons: ['缺少可用的案件編號'] }]);
    expect(() => adaptHcmImportResult({ ...receipt, row_outcomes: [] })).toThrow('筆數不一致');
  });
  it('HCM counts imported warnings and email fills once, and includes both duplicate outcomes', () => {
    const receipt = { source_content_digest: digest, source_row_count: 10, inserted_count: 2, inserted_with_warning_count: 2, email_filled_count: 1, exact_replay_count: 1, skipped_existing_count: 2, review_required_count: 1, failed_count: 1, replayed_workbook: false, row_outcomes_available: false, legacy_summary_only: true, row_outcomes: [] };
    expect(adaptHcmImportResult(receipt)).toMatchObject({ sourceCount: 10, importedCount: 5, duplicateCount: 3, notImportedCount: 2 });
    expect(() => adaptHcmImportResult({ ...receipt, source_row_count: 11 })).toThrow('筆數不一致');
  });

  it('BeClass keeps validation and binding failures separate from duplicate skips', () => {
    expect(adaptClientBeClassImportResult({ source_content_digest: digest, source_row_count: 10, created_count: 4, exact_replay_count: 1, existing_source_count: 2, review_required_count: 1, existing_conflict_count: 2, replayed_workbook: false })).toMatchObject({ sourceCount: 10, importedCount: 4, duplicateCount: 3, notImportedCount: 3 });
  });

  it('Staff review overlays never add another row to the result', () => {
    expect(adaptStaffHistoricalImportResult({ source_content_digest: digest, source_row_count: 10, created_count: 3, adopted_existing_count: 3, exact_replay_count: 2, blocked_identity_count: 1, identity_conflict_count: 1, review_required_count: 8, preview_fingerprint: fingerprint, replayed_workbook: false })).toMatchObject({ sourceCount: 10, importedCount: 6, duplicateCount: 2, notImportedCount: 2 });
  });

  const historical = { source_content_digest: digest, source_row_count: 4, adopted_count: 2, unmatched_case_count: 1, review_required_count: 2, current_conflict_count: 0, assignments_created: 0, replayed_rows: 2, replayed_workbook: false, absent_order_cancellation_count: 100, status_counts: statusCounts, result_counts: resultCounts, review_references: [] };
  it('Historical Orders use owner counts when duplicate receipts include a non-adopted row', () => {
    expect(adaptHistoricalOrderImportResult({ ...historical, import_counts: { imported_count: 1, duplicate_skipped_count: 2, not_imported_count: 1 } })).toMatchObject({ sourceCount: 4, importedCount: 1, duplicateCount: 2, notImportedCount: 1 });
  });

  it('Old mixed-replay receipts show unavailable counts instead of guessing the overlap', () => {
    expect(adaptHistoricalOrderImportResult(historical)).toMatchObject({ sourceCount: 4, importedCount: null, duplicateCount: null, notImportedCount: null });
    expect(adaptHistoricalOrderImportResult({ ...historical, replayed_rows: 0 })).toMatchObject({ sourceCount: 4, importedCount: 2, duplicateCount: 0, notImportedCount: 2 });
  });

  it('Result lookup keeps the immutable original counts and identifies the replay', () => {
    expect(adaptHistoricalOrderImportResult({ ...historical, replayed_workbook: true, import_counts: { imported_count: 1, duplicate_skipped_count: 2, not_imported_count: 1 } })).toMatchObject({ importedCount: 1, duplicateCount: 2, notImportedCount: 1, replayedWorkbook: true });
  });
});
