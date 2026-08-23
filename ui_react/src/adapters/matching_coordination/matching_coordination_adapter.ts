/**
 * File: matching_coordination_adapter.ts
 * Description: 僅重命名 M3 transport 欄位，不在瀏覽器重算媒合事實。
 */
import type {
  MatchingApplyReceiptResponse,
  MatchingCoordinationQueryResponse,
} from '../../api/matching_coordination/matching_coordination_schemas';

export interface MatchingCoordinationQueryView {
  caseNo: string;
  snapshot: MatchingCoordinationQueryResponse['snapshot'];
  matchingPackage: MatchingCoordinationQueryResponse['package'];
  candidates: MatchingCoordinationQueryResponse['candidates'];
  sourceVersions: MatchingCoordinationQueryResponse['source_versions'];
  refusalHistory: MatchingCoordinationQueryResponse['refusal_history'];
  willingnessLineage: MatchingCoordinationQueryResponse['willingness_lineage'];
  expectedSourceVersionsMatch: boolean;
}

export interface MatchingApplyReceiptView {
  receiptId: string;
  commandName: MatchingApplyReceiptResponse['command_name'];
  previewFingerprint: string;
  resultState: MatchingApplyReceiptResponse['result_state'];
  receipt: MatchingApplyReceiptResponse;
}

export function toMatchingCoordinationQueryView(
  transport: MatchingCoordinationQueryResponse
): MatchingCoordinationQueryView {
  return {
    caseNo: transport.case_no,
    snapshot: transport.snapshot,
    matchingPackage: transport.package,
    candidates: transport.candidates,
    sourceVersions: transport.source_versions,
    refusalHistory: transport.refusal_history,
    willingnessLineage: transport.willingness_lineage,
    expectedSourceVersionsMatch: transport.expected_source_versions_match,
  };
}

export function toMatchingApplyReceiptView(
  transport: MatchingApplyReceiptResponse
): MatchingApplyReceiptView {
  return {
    receiptId: transport.receipt_id,
    commandName: transport.command_name,
    previewFingerprint: transport.preview_fingerprint,
    resultState: transport.result_state,
    receipt: transport,
  };
}
