/**
 * File: matching_coordination_client.test.ts
 * Description: 驗證 M3 全端點、Session、嚴格解碼、Apply 標頭與純轉接。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  matchingCoordinationClient,
  queryMatchingCoordination,
} from '../api/matching_coordination/matching_coordination_client';
import {
  ApiAbortError,
  ApiDecodeError,
  MatchingCoordinationClientError,
  MatchingCoordinationUnauthenticatedError,
} from '../api/matching_coordination/matching_coordination_errors';
import {
  ApplyCaregiverSelectionRequestSchema,
  ApplyCriteriaDiffRequestSchema,
  ApplyCustomerDecisionRequestSchema,
  ApplyInitialCriteriaRequestSchema,
  ApplyLeaveImpactRequestSchema,
  ApplyRematchRequestSchema,
  ApplyServiceDateRematchRequestSchema,
  ApplyZeroCandidateRequestSchema,
  ApplyZeroCandidateConfirmationRequestSchema,
  MatchingCoordinationQueryRequestSchema,
  PreviewCriteriaDiffRequestSchema,
  PreviewInitialCriteriaRequestSchema,
  PreviewLeaveImpactRequestSchema,
  PreviewMatchingPackageRequestSchema,
  PreviewRematchRequestSchema,
  PreviewServiceDateRematchRequestSchema,
  PreviewZeroCandidateRequestSchema,
  PreviewZeroCandidateConfirmationRequestSchema,
} from '../api/matching_coordination/matching_coordination_schemas';
import {
  toMatchingApplyReceiptView,
  toMatchingCoordinationQueryView,
} from '../adapters/matching_coordination/matching_coordination_adapter';
import {
  APPLY_OPTIONS,
  MATCHING_APPLY_RECEIPT,
  MATCHING_CRITERIA_DIFF,
  MATCHING_LEAVE_IMPACT,
  MATCHING_PACKAGE,
  MATCHING_NO_CANDIDATE_PACKAGE,
  MATCHING_QUERY_DATA,
  MATCHING_SERVICE_DATE_REMATCH,
  MATCHING_SNAPSHOT,
  MATCHING_SOURCE_TUPLE,
  MATCHING_ZERO_CANDIDATE,
  MATCHING_ZERO_CANDIDATE_CONFIRMATION_RECEIPT,
  PREVIEW_DIFF_REQUEST,
  PREVIEW_INITIAL_REQUEST,
  PREVIEW_LEAVE_REQUEST,
  PREVIEW_PACKAGE_REQUEST,
  PREVIEW_REMATCH_REQUEST,
  PREVIEW_SERVICE_DATE_REQUEST,
  PREVIEW_ZERO_REQUEST,
  PREVIEW_ZERO_CANDIDATE_CONFIRMATION_REQUEST,
  QUERY_REQUEST,
  SHA_A_FIXTURE,
  successEnvelope,
} from './fixtures/matching_coordination/matching_coordination_contract_fixtures';

function response(payload: object, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function setSession(token: string): void {
  sessionClient.setSession(token, {
    id: 11,
    username: 'matching-test',
    display_name: '媒合測試人員',
    role: 'operator',
    linked_line_user_id: null,
    capabilities: [],
    is_root: false,
    access_control_version: 1,
  });
}

function endpointData(url: string): unknown {
  if (url.endsWith('/query')) return MATCHING_QUERY_DATA;
  if (url.endsWith('/preview/initial-criteria')) return MATCHING_SNAPSHOT;
  if (url.endsWith('/preview/package') || url.endsWith('/preview/rematch')) {
    return MATCHING_PACKAGE;
  }
  if (url.endsWith('/preview/criteria-diff')) return MATCHING_CRITERIA_DIFF;
  if (url.endsWith('/preview/zero-candidate')) return MATCHING_ZERO_CANDIDATE;
  if (url.endsWith('/preview/confirm-zero-candidate')) {
    return MATCHING_NO_CANDIDATE_PACKAGE;
  }
  if (url.endsWith('/preview/leave-impact')) return MATCHING_LEAVE_IMPACT;
  if (url.endsWith('/preview/service-date-rematch')) {
    return MATCHING_SERVICE_DATE_REMATCH;
  }
  if (url.endsWith('/apply/confirm-zero-candidate')) {
    return MATCHING_ZERO_CANDIDATE_CONFIRMATION_RECEIPT;
  }
  return MATCHING_APPLY_RECEIPT;
}

describe('matching coordination client', () => {
  beforeEach(() => {
    setSession('matching-token-a');
    vi.restoreAllMocks();
  });

  afterEach(() => {
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('逐一呼叫 current Query 與全部正式 Preview 路徑', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) =>
      Promise.resolve(response(successEnvelope(endpointData(url))))
    );
    globalThis.fetch = fetchMock;

    await matchingCoordinationClient.query(
      'CASE-001',
      MatchingCoordinationQueryRequestSchema.parse(QUERY_REQUEST)
    );
    await matchingCoordinationClient.previewInitialCriteria(
      'CASE-001',
      PreviewInitialCriteriaRequestSchema.parse(PREVIEW_INITIAL_REQUEST)
    );
    await matchingCoordinationClient.previewMatchingPackage(
      'CASE-001',
      PreviewMatchingPackageRequestSchema.parse(PREVIEW_PACKAGE_REQUEST)
    );
    await matchingCoordinationClient.previewCriteriaDiff(
      'CASE-001',
      PreviewCriteriaDiffRequestSchema.parse(PREVIEW_DIFF_REQUEST)
    );
    await matchingCoordinationClient.previewZeroCandidate(
      'CASE-001',
      PreviewZeroCandidateRequestSchema.parse(PREVIEW_ZERO_REQUEST)
    );
    await matchingCoordinationClient.previewZeroCandidateConfirmation(
      'CASE-001',
      PreviewZeroCandidateConfirmationRequestSchema.parse(
        PREVIEW_ZERO_CANDIDATE_CONFIRMATION_REQUEST
      )
    );
    await matchingCoordinationClient.previewRematch(
      'CASE-001',
      PreviewRematchRequestSchema.parse(PREVIEW_REMATCH_REQUEST)
    );
    await matchingCoordinationClient.previewLeaveImpact(
      'CASE-001',
      PreviewLeaveImpactRequestSchema.parse(PREVIEW_LEAVE_REQUEST)
    );
    await matchingCoordinationClient.previewServiceDateRematch(
      'CASE-001',
      PreviewServiceDateRematchRequestSchema.parse(
        PREVIEW_SERVICE_DATE_REQUEST
      )
    );

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      '/api/v1/matching-coordination/CASE-001/query',
      '/api/v1/matching-coordination/CASE-001/preview/initial-criteria',
      '/api/v1/matching-coordination/CASE-001/preview/package',
      '/api/v1/matching-coordination/CASE-001/preview/criteria-diff',
      '/api/v1/matching-coordination/CASE-001/preview/zero-candidate',
      '/api/v1/matching-coordination/CASE-001/preview/confirm-zero-candidate',
      '/api/v1/matching-coordination/CASE-001/preview/rematch',
      '/api/v1/matching-coordination/CASE-001/preview/leave-impact',
      '/api/v1/matching-coordination/CASE-001/preview/service-date-rematch',
    ]);
    for (const call of fetchMock.mock.calls) {
      expect(call[1]?.method).toBe('POST');
      expect(new Headers(call[1]?.headers).get('Idempotency-Key')).toBeNull();
    }
  });

  it('逐一呼叫全部正式 Apply/decision 並強制 caller headers', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) =>
      Promise.resolve(response(successEnvelope(endpointData(url))))
    );
    globalThis.fetch = fetchMock;

    const source = { expected_source_versions: MATCHING_SOURCE_TUPLE };
    await matchingCoordinationClient.applyLeaveImpact(
      'CASE-001',
      ApplyLeaveImpactRequestSchema.parse({
        ...source,
        reason: '套用請假影響',
        package_id: 'package-1',
        leave_reference: 'leave-1',
        criteria_snapshot_id: 'snapshot-1',
        expected_leave_version: 1,
        original_staff_id: 7,
        preview_fingerprint: SHA_A_FIXTURE,
      }),
      APPLY_OPTIONS
    );
    await matchingCoordinationClient.applyServiceDateRematch(
      'CASE-001',
      ApplyServiceDateRematchRequestSchema.parse({
        ...PREVIEW_SERVICE_DATE_REQUEST,
        preview_fingerprint: SHA_A_FIXTURE,
      }),
      APPLY_OPTIONS
    );
    await matchingCoordinationClient.applyRematch(
      'CASE-001',
      ApplyRematchRequestSchema.parse({
        ...PREVIEW_REMATCH_REQUEST,
        preview_fingerprint: SHA_A_FIXTURE,
      }),
      APPLY_OPTIONS
    );
    await matchingCoordinationClient.applyInitialCriteria(
      'CASE-001',
      ApplyInitialCriteriaRequestSchema.parse({
        ...PREVIEW_INITIAL_REQUEST,
        preview_fingerprint: SHA_A_FIXTURE,
      }),
      APPLY_OPTIONS
    );
    await matchingCoordinationClient.applyCriteriaDiff(
      'CASE-001',
      ApplyCriteriaDiffRequestSchema.parse({
        ...PREVIEW_DIFF_REQUEST,
        preview_fingerprint: SHA_A_FIXTURE,
        recipient_ids: ['staff-7'],
      }),
      APPLY_OPTIONS
    );
    await matchingCoordinationClient.applyCaregiverSelection(
      'CASE-001',
      ApplyCaregiverSelectionRequestSchema.parse({
        ...source,
        reason: '月嫂回覆願意',
        criteria_snapshot_id: 'snapshot-1',
        package_id: 'package-1',
        package_version: 1,
        candidate_id: 'candidate-1',
        willingness: 'willing',
        reason_code: null,
        affected_criteria: [],
        preview_fingerprint: SHA_A_FIXTURE,
      }),
      APPLY_OPTIONS
    );
    await matchingCoordinationClient.applyCustomerDecision(
      'CASE-001',
      ApplyCustomerDecisionRequestSchema.parse({
        ...source,
        reason: '客戶接受媒合',
        criteria_snapshot_id: 'snapshot-1',
        package_id: 'package-1',
        package_version: 1,
        candidate_id: 'candidate-1',
        decision: 'accepted',
        preview_fingerprint: SHA_A_FIXTURE,
      }),
      APPLY_OPTIONS
    );
    await matchingCoordinationClient.applyZeroCandidate(
      'CASE-001',
      ApplyZeroCandidateRequestSchema.parse({
        ...PREVIEW_ZERO_REQUEST,
        alternative_id: 'alternative-1',
        preview_fingerprint: SHA_A_FIXTURE,
        decision: 'agree',
      }),
      APPLY_OPTIONS
    );
    await matchingCoordinationClient.applyZeroCandidateConfirmation(
      'CASE-001',
      ApplyZeroCandidateConfirmationRequestSchema.parse({
        ...PREVIEW_ZERO_CANDIDATE_CONFIRMATION_REQUEST,
        preview_fingerprint: SHA_A_FIXTURE,
      }),
      APPLY_OPTIONS
    );

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      '/api/v1/matching-coordination/CASE-001/apply/leave-impact',
      '/api/v1/matching-coordination/CASE-001/apply/service-date-rematch',
      '/api/v1/matching-coordination/CASE-001/apply/rematch',
      '/api/v1/matching-coordination/CASE-001/apply/initial-criteria',
      '/api/v1/matching-coordination/CASE-001/apply/criteria-diff',
      '/api/v1/matching-coordination/CASE-001/apply/caregiver-selection',
      '/api/v1/matching-coordination/CASE-001/apply/customer-decision',
      '/api/v1/matching-coordination/CASE-001/apply/zero-candidate',
      '/api/v1/matching-coordination/CASE-001/apply/confirm-zero-candidate',
    ]);
    for (const call of fetchMock.mock.calls) {
      const headers = new Headers(call[1]?.headers);
      expect(headers.get('Idempotency-Key')).toBe(APPLY_OPTIONS.idempotencyKey);
      expect(headers.get('X-Correlation-ID')).toBe(APPLY_OPTIONS.correlationId);
    }
  });

  it('Query 可嚴格解碼 current candidate_pool_open package', async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce(
      response(successEnvelope({
        ...MATCHING_QUERY_DATA,
        package: {
          ...MATCHING_PACKAGE,
          candidate_results: [],
          segments: [],
          state: 'candidate_pool_open',
        },
        candidates: [],
      }))
    );

    const result = await matchingCoordinationClient.query(
      'CASE-001',
      MatchingCoordinationQueryRequestSchema.parse(QUERY_REQUEST)
    );

    expect(result.package?.state).toBe('candidate_pool_open');
  });

  it('確認零候選 request 不接受候選數、package state 或 disposition', () => {
    for (const forbidden of ['candidate_count', 'state', 'disposition']) {
      expect(
        PreviewZeroCandidateConfirmationRequestSchema.safeParse({
          ...PREVIEW_ZERO_CANDIDATE_CONFIRMATION_REQUEST,
          [forbidden]: forbidden === 'candidate_count' ? 0 : 'no_candidate',
        }).success
      ).toBe(false);
    }
    expect(
      PreviewZeroCandidateConfirmationRequestSchema.safeParse({
        ...PREVIEW_ZERO_CANDIDATE_CONFIRMATION_REQUEST,
        evidence: ['z-last', 'a-first'],
      }).success
    ).toBe(false);
  });

  it('每次讀取 current Session 並拒絕覆寫 protected headers', async () => {
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(response(successEnvelope(MATCHING_QUERY_DATA)))
    );
    globalThis.fetch = fetchMock;
    const payload = MatchingCoordinationQueryRequestSchema.parse(QUERY_REQUEST);

    await queryMatchingCoordination('CASE-001', payload, {
      headers: {
        Authorization: 'Bearer injected',
        'X-Correlation-ID': 'injected',
      },
      correlationId: 'trusted-correlation',
    });
    setSession('matching-token-b');
    await queryMatchingCoordination('CASE-001', payload);

    const first = new Headers(fetchMock.mock.calls[0][1]?.headers);
    const second = new Headers(fetchMock.mock.calls[1][1]?.headers);
    expect(first.get('Authorization')).toBe('Bearer matching-token-a');
    expect(first.get('X-Correlation-ID')).toBe('trusted-correlation');
    expect(second.get('Authorization')).toBe('Bearer matching-token-b');
  });

  it('缺少 Session 與預先 abort 都在網路前 fail closed', async () => {
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
    const payload = MatchingCoordinationQueryRequestSchema.parse(QUERY_REQUEST);
    sessionClient.clearSession();
    await expect(
      queryMatchingCoordination('CASE-001', payload)
    ).rejects.toBeInstanceOf(MatchingCoordinationUnauthenticatedError);

    setSession('matching-token-a');
    const controller = new AbortController();
    controller.abort();
    await expect(
      queryMatchingCoordination('CASE-001', payload, {
        signal: controller.signal,
      })
    ).rejects.toBeInstanceOf(ApiAbortError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('回應多餘欄位 strict fail closed，typed 409 保留分類與 blocker', async () => {
    const extraResponse = successEnvelope({
      ...MATCHING_QUERY_DATA,
      browser_computed_score: 99,
    });
    globalThis.fetch = vi.fn().mockResolvedValueOnce(response(extraResponse));
    const payload = MatchingCoordinationQueryRequestSchema.parse(QUERY_REQUEST);
    await expect(
      queryMatchingCoordination('CASE-001', payload)
    ).rejects.toBeInstanceOf(ApiDecodeError);

    globalThis.fetch = vi.fn().mockResolvedValueOnce(
      response(
        {
          detail: {
            error: {
              category: 'domain_blocked',
              code: 'matching_criteria_source_stale',
              message: '來源版本已過期',
              field_errors: [],
              domain_blockers: ['orders_service_dates'],
              retryable: false,
              correlation_id: 'matching-error-1',
              current_version: 3,
            },
          },
        },
        409
      )
    );
    const caught = await queryMatchingCoordination('CASE-001', payload).catch(
      (error: unknown) => error
    );
    expect(caught).toBeInstanceOf(MatchingCoordinationClientError);
    expect(caught).toMatchObject({
      category: 'domain_blocked',
      code: 'matching_criteria_source_stale',
      domainBlockers: ['orders_service_dates'],
      correlationId: 'matching-error-1',
    });
  });

  it('adapter 只重命名 transport，不推導或改寫 domain facts', () => {
    const query = toMatchingCoordinationQueryView(MATCHING_QUERY_DATA as never);
    const receipt = toMatchingApplyReceiptView(MATCHING_APPLY_RECEIPT as never);
    expect(query.caseNo).toBe(MATCHING_QUERY_DATA.case_no);
    expect(query.snapshot).toBe(MATCHING_QUERY_DATA.snapshot);
    expect(query.candidates).toBe(MATCHING_QUERY_DATA.candidates);
    expect(receipt.resultState).toBe(MATCHING_APPLY_RECEIPT.result_state);
    expect(receipt.receipt).toBe(MATCHING_APPLY_RECEIPT);
  });
});
