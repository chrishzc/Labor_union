/**
 * File: leave_substitution_adapter.test.ts
 * Description: 驗證請假代班 React flow 的 Preview、Apply、穩定重試與 receipt 觀察狀態。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  applyLeaveSubstitutionFlow,
  previewLeaveSubstitutionFlow,
  queryLeaveSubstitutionFlow,
  resolveLeaveSubstitutionMachineState,
  retryLeaveSubstitutionApplyFlow,
  retryLeaveSubstitutionObservationFlow,
  setLeaveSubstitutionDraft,
} from '../adapters/scheduling/leave_substitution_flow_adapter';
import {
  leaveSubstitutionFlowStore,
  type LeaveSubstitutionFlowDraft,
} from '../adapters/scheduling/leave_substitution_flow_store';
import type { LeaveSubstitutionClient } from '../api/scheduling/leave_substitution_client';
import {
  LeaveSubstitutionContractError,
  LeaveSubstitutionConflictError,
  LeaveSubstitutionNetworkError,
  LeaveSubstitutionTimeoutError,
  LeaveSubstitutionValidationError,
} from '../api/scheduling/leave_substitution_errors';
import type {
  LeaveSubstitutionPreviewRequest,
  LeaveSubstitutionReceipt,
} from '../api/scheduling/leave_substitution_schemas';
import {
  LEAVE_APPLY_REQUEST,
  LEAVE_ASSIGNMENTS,
  LEAVE_CASE_NO,
  LEAVE_OBSERVED_ASSIGNMENTS,
  LEAVE_PREVIEW,
  LEAVE_PREVIEW_REQUEST,
  LEAVE_RECEIPT,
} from './fixtures/scheduling/leave_substitution_contract_fixtures';

function fakeClient(overrides?: Partial<LeaveSubstitutionClient>): LeaveSubstitutionClient {
  return {
    listAssignments: vi.fn()
      .mockResolvedValueOnce(LEAVE_ASSIGNMENTS)
      .mockResolvedValue(LEAVE_OBSERVED_ASSIGNMENTS),
    preview: vi.fn().mockResolvedValue(LEAVE_PREVIEW),
    apply: vi.fn().mockResolvedValue(LEAVE_RECEIPT),
    ...overrides,
  };
}

async function preparePreview(client: LeaveSubstitutionClient): Promise<void> {
  await queryLeaveSubstitutionFlow(LEAVE_CASE_NO, { client });
  setLeaveSubstitutionDraft(LEAVE_CASE_NO, LEAVE_PREVIEW_REQUEST);
  await previewLeaveSubstitutionFlow(LEAVE_CASE_NO, { client });
}

describe('leave substitution flow adapter', () => {
  beforeEach(() => {
    leaveSubstitutionFlowStore.clearAll();
  });

  it('runs Query -> Preview -> Apply -> receipt -> re-query without leaking the test client into transport options', async () => {
    const client = fakeClient();

    await preparePreview(client);
    const receipt = await applyLeaveSubstitutionFlow(
      LEAVE_CASE_NO,
      LEAVE_APPLY_REQUEST,
      { client },
    );

    expect(receipt).toEqual(LEAVE_RECEIPT);
    expect(client.apply).toHaveBeenCalledTimes(1);
    const applyOptions = vi.mocked(client.apply).mock.calls[0][2];
    expect(applyOptions).not.toHaveProperty('client');
    expect(applyOptions.idempotencyKey).toBeTruthy();
    expect(resolveLeaveSubstitutionMachineState(
      leaveSubstitutionFlowStore.get(LEAVE_CASE_NO),
    )).toMatchObject({ type: 'observed', receipt: LEAVE_RECEIPT });
  });

  it('invalidates an old Preview and idempotency identity when a fresh Query begins', async () => {
    const client = fakeClient();
    await preparePreview(client);
    const oldKey = leaveSubstitutionFlowStore.get(LEAVE_CASE_NO)?.idempotencyKey;

    await queryLeaveSubstitutionFlow(LEAVE_CASE_NO, { client });

    const draft = leaveSubstitutionFlowStore.get(LEAVE_CASE_NO);
    expect(draft).toMatchObject({
      status: 'query_ready',
      previewRequest: null,
      preview: null,
      receipt: null,
    });
    expect(draft?.idempotencyKey).not.toBe(oldKey);
  });

  it('keeps the exact Apply payload and stable idempotency key for an outcome-unknown retry', async () => {
    const apply = vi
      .fn<LeaveSubstitutionClient['apply']>()
      .mockRejectedValueOnce(new LeaveSubstitutionTimeoutError('timeout'))
      .mockResolvedValueOnce(LEAVE_RECEIPT);
    const client = fakeClient({ apply });
    await preparePreview(client);

    await expect(
      applyLeaveSubstitutionFlow(LEAVE_CASE_NO, LEAVE_APPLY_REQUEST, { client }),
    ).rejects.toBeInstanceOf(LeaveSubstitutionTimeoutError);
    const unknown = leaveSubstitutionFlowStore.get(LEAVE_CASE_NO);
    expect(unknown).toMatchObject({
      status: 'outcome_unknown',
      applyRequest: LEAVE_APPLY_REQUEST,
    });

    await retryLeaveSubstitutionApplyFlow(LEAVE_CASE_NO, { client });

    expect(apply).toHaveBeenCalledTimes(2);
    expect(apply.mock.calls[1][1]).toEqual(apply.mock.calls[0][1]);
    expect(apply.mock.calls[1][2].idempotencyKey).toBe(
      apply.mock.calls[0][2].idempotencyKey,
    );
  });

  it('retains a committed receipt when the post-Apply observation fails', async () => {
    const listAssignments = vi
      .fn<LeaveSubstitutionClient['listAssignments']>()
      .mockResolvedValueOnce(LEAVE_ASSIGNMENTS)
      .mockRejectedValueOnce(new LeaveSubstitutionNetworkError('offline'));
    const client = fakeClient({ listAssignments });
    await preparePreview(client);

    await expect(
      applyLeaveSubstitutionFlow(LEAVE_CASE_NO, LEAVE_APPLY_REQUEST, { client }),
    ).rejects.toBeInstanceOf(LeaveSubstitutionNetworkError);

    expect(leaveSubstitutionFlowStore.get(LEAVE_CASE_NO)).toMatchObject({
      status: 'observation_failed',
      receipt: LEAVE_RECEIPT,
    });
  });

  it('coalesces concurrent Apply calls into one mutation and one observation', async () => {
    let resolveApply!: (receipt: LeaveSubstitutionReceipt) => void;
    const pendingApply = new Promise<LeaveSubstitutionReceipt>((resolve) => {
      resolveApply = resolve;
    });
    const apply = vi.fn<LeaveSubstitutionClient['apply']>().mockReturnValue(pendingApply);
    const client = fakeClient({ apply });
    await preparePreview(client);

    const first = applyLeaveSubstitutionFlow(LEAVE_CASE_NO, LEAVE_APPLY_REQUEST, { client });
    const second = applyLeaveSubstitutionFlow(LEAVE_CASE_NO, LEAVE_APPLY_REQUEST, { client });

    expect(apply).toHaveBeenCalledTimes(1);
    resolveApply(LEAVE_RECEIPT);
    await expect(Promise.all([first, second])).resolves.toEqual([LEAVE_RECEIPT, LEAVE_RECEIPT]);
    expect(client.listAssignments).toHaveBeenCalledTimes(2);
  });

  it('does not classify a retryable non-stale 409 as outcome unknown', async () => {
    const client = fakeClient({
      apply: vi.fn().mockRejectedValue(
        new LeaveSubstitutionConflictError('another mutation owns the case', {
          publicCode: 'mutation_in_progress',
          retryable: true,
        }),
      ),
    });
    await preparePreview(client);

    await expect(
      applyLeaveSubstitutionFlow(LEAVE_CASE_NO, LEAVE_APPLY_REQUEST, { client }),
    ).rejects.toBeInstanceOf(LeaveSubstitutionConflictError);
    expect(leaveSubstitutionFlowStore.get(LEAVE_CASE_NO)).toMatchObject({ status: 'typed_error' });
  });

  it('preserves the receipt and locks the payload until re-query observes cancel-old/create-new lineage', async () => {
    const client = fakeClient({
      listAssignments: vi.fn().mockResolvedValue(LEAVE_ASSIGNMENTS),
    });
    await preparePreview(client);

    await expect(
      applyLeaveSubstitutionFlow(LEAVE_CASE_NO, LEAVE_APPLY_REQUEST, { client }),
    ).rejects.toBeInstanceOf(LeaveSubstitutionContractError);
    expect(leaveSubstitutionFlowStore.get(LEAVE_CASE_NO)).toMatchObject({
      status: 'observation_failed',
      receipt: LEAVE_RECEIPT,
      previewRequest: LEAVE_PREVIEW_REQUEST,
    });

    setLeaveSubstitutionDraft(LEAVE_CASE_NO, {
      ...LEAVE_PREVIEW_REQUEST,
      original_assignment_id: 99,
    });
    expect(leaveSubstitutionFlowStore.get(LEAVE_CASE_NO)?.previewRequest).toEqual(LEAVE_PREVIEW_REQUEST);

    vi.mocked(client.listAssignments).mockResolvedValueOnce(LEAVE_OBSERVED_ASSIGNMENTS);
    await expect(retryLeaveSubstitutionObservationFlow(LEAVE_CASE_NO, { client })).resolves.toEqual(
      LEAVE_OBSERVED_ASSIGNMENTS,
    );
  });

  it('rejects a Preview identity that omitted required resolution fields', async () => {
    const previewRequest = {
      original_assignment_id: 31,
      items: [{
        original_schedule_id: 301,
        work_date: '2026-08-03',
        resolution_type: 'substitute',
        substitute_staff_id: 12,
      }],
      leave_request_id: 77,
      expected_leave_request_version: 4,
    } as unknown as LeaveSubstitutionPreviewRequest;
    const client = fakeClient();
    await queryLeaveSubstitutionFlow(LEAVE_CASE_NO, { client });
    setLeaveSubstitutionDraft(LEAVE_CASE_NO, previewRequest);
    await previewLeaveSubstitutionFlow(LEAVE_CASE_NO, { client });

    await expect(
      applyLeaveSubstitutionFlow(LEAVE_CASE_NO, LEAVE_APPLY_REQUEST, { client }),
    ).rejects.toBeInstanceOf(LeaveSubstitutionValidationError);
    expect(client.apply).not.toHaveBeenCalled();
  });

  it('fails closed with a typed contract error when a machine state is structurally incomplete', () => {
    const incomplete: LeaveSubstitutionFlowDraft = {
      caseNo: LEAVE_CASE_NO,
      assignments: LEAVE_ASSIGNMENTS,
      previewRequest: null,
      preview: null,
      applyRequest: null,
      idempotencyKey: 'stable-key',
      correlationId: 'correlation-id',
      receipt: null,
      status: 'preview_loading',
      error: null,
    };

    expect(() => resolveLeaveSubstitutionMachineState(incomplete)).toThrow(
      LeaveSubstitutionContractError,
    );
  });
});
