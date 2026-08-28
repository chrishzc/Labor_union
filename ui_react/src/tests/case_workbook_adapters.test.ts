/**
 * File: case_workbook_adapters.test.ts
 * Description: 驗證Case Workbook Preview投影、terminal守恆與Historical Orders review overlay。
 */
import { describe, expect, it } from 'vitest';
import { adaptClientBeClassWorkbookPreview } from '../adapters/case_import/client_beclass_workbook_adapter';
import { adaptStaffHistoricalWorkbookPreview } from '../adapters/case_import/staff_historical_workbook_adapter';
import { adaptHistoricalOrderWorkbookPreview } from '../adapters/orders/historical_order_workbook_adapter';

const digest = 'a'.repeat(64);
const identity = 'b'.repeat(64);
const fingerprint = 'c'.repeat(64);

describe('Case workbook Preview adapters', () => {
  it('投影三個互不混用的aggregate contract', () => {
    expect(adaptClientBeClassWorkbookPreview({ source_content_digest: digest, sheet_identity: identity, source_row_count: 4, create_count: 1, review_required_count: 1, existing_conflict_count: 1, existing_source_count: 1, preview_fingerprint: fingerprint }).createCount).toBe(1);
    expect(adaptStaffHistoricalWorkbookPreview({ source_content_digest: digest, source_row_count: 4, created_count: 1, adopted_existing_count: 1, blocked_identity_count: 1, identity_conflict_count: 1, review_required_count: 1, preview_fingerprint: fingerprint }).adoptedExistingCount).toBe(1);
    expect(adaptHistoricalOrderWorkbookPreview({ source_content_digest: digest, sheet_identity: identity, source_row_count: 4, adopted_count: 2, unmatched_case_count: 1, review_required_count: 1, current_conflict_count: 1, assignment_candidate_count: 1, evidence_only_pairing_count: 1, preview_fingerprint: fingerprint }).assignmentCandidateCount).toBe(1);
  });

  it('Historical Orders review_required是adopted row overlay，不重複計入terminal總數', () => {
    const model = adaptHistoricalOrderWorkbookPreview({ source_content_digest: digest, sheet_identity: identity, source_row_count: 1, adopted_count: 1, unmatched_case_count: 0, review_required_count: 1, current_conflict_count: 0, assignment_candidate_count: 0, evidence_only_pairing_count: 1, preview_fingerprint: fingerprint });
    expect(model.adoptedCount).toBe(1);
    expect(model.reviewRequiredCount).toBe(1);
  });

  it('Historical Orders接受invalid status形成的terminal review row', () => {
    const model = adaptHistoricalOrderWorkbookPreview({ source_content_digest: digest, sheet_identity: identity, source_row_count: 1, adopted_count: 0, unmatched_case_count: 0, review_required_count: 1, current_conflict_count: 0, assignment_candidate_count: 0, evidence_only_pairing_count: 0, preview_fingerprint: fingerprint });
    expect(model.reviewRequiredCount).toBe(1);
  });

  it('拒絕來源列數不守恆', () => {
    expect(() => adaptClientBeClassWorkbookPreview({ source_content_digest: digest, sheet_identity: identity, source_row_count: 9, create_count: 1, review_required_count: 1, existing_conflict_count: 1, existing_source_count: 1, preview_fingerprint: fingerprint })).toThrow(/不守恆/);
    expect(() => adaptStaffHistoricalWorkbookPreview({ source_content_digest: digest, source_row_count: 9, created_count: 1, adopted_existing_count: 1, blocked_identity_count: 1, identity_conflict_count: 1, review_required_count: 1, preview_fingerprint: fingerprint })).toThrow(/不守恆/);
    expect(() => adaptHistoricalOrderWorkbookPreview({ source_content_digest: digest, sheet_identity: identity, source_row_count: 9, adopted_count: 2, unmatched_case_count: 1, review_required_count: 1, current_conflict_count: 0, assignment_candidate_count: 1, evidence_only_pairing_count: 1, preview_fingerprint: fingerprint })).toThrow(/不守恆/);
  });
});
