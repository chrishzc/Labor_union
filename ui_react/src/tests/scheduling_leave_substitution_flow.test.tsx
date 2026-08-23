/**
 * File: scheduling_leave_substitution_flow.test.tsx
 * Description: 定義請假代班 Query、Preview、Apply、receipt 觀察與 typed retry 的 bounded flow 語意。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  applyLeaveSubstitutionFlow,
  previewLeaveSubstitutionFlow,
  queryLeaveSubstitutionFlow,
  resolveLeaveSubstitutionMachineState,
  retryLeaveSubstitutionApplyFlow,
  setLeaveSubstitutionDraft,
} from '../adapters/scheduling/leave_substitution_flow_adapter';
import {
  leaveSubstitutionFlowStore,
  type LeaveSubstitutionFlowDraft,
} from '../adapters/scheduling/leave_substitution_flow_store';
import {
  LeaveSubstitutionConflictError,
  LeaveSubstitutionUnavailableError,
  LeaveSubstitutionValidationError,
} from '../api/scheduling/leave_substitution_errors';
import type { LeaveSubstitutionClient } from '../api/scheduling/leave_substitution_client';
import {
  LEAVE_APPLY_REQUEST,
  LEAVE_ASSIGNMENTS,
  LEAVE_CASE_NO,
  LEAVE_OBSERVED_ASSIGNMENTS,
  LEAVE_PREVIEW,
  LEAVE_PREVIEW_REQUEST,
  LEAVE_RECEIPT,
} from './fixtures/scheduling/leave_substitution_contract_fixtures';

function fakeClient(): LeaveSubstitutionClient {
  return {
    listAssignments: vi.fn(),
    preview: vi.fn(),
    apply: vi.fn(),
  };
}

function state(): LeaveSubstitutionFlowDraft | undefined {
  return leaveSubstitutionFlowStore.get(LEAVE_CASE_NO);
}

describe('Scheduling leave/substitution bounded flow', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    leaveSubstitutionFlowStore.clearAll();
  });

  afterEach(() => {
    leaveSubstitutionFlowStore.clearAll();
    vi.restoreAllMocks();
  });

  it('遵循 query → official schedule selection → Preview → explicit Apply confirmation → receipt → re-query', async () => {
    const client = fakeClient();
    vi.mocked(client.listAssignments)
      .mockResolvedValueOnce(LEAVE_ASSIGNMENTS)
      .mockResolvedValueOnce(LEAVE_OBSERVED_ASSIGNMENTS);
    vi.mocked(client.preview).mockResolvedValue(LEAVE_PREVIEW);
    vi.mocked(client.apply).mockResolvedValue(LEAVE_RECEIPT);

    await queryLeaveSubstitutionFlow(LEAVE_CASE_NO, { client });
    expect(resolveLeaveSubstitutionMachineState(state())).toMatchObject({
      type: 'query_ready',
      assignments: LEAVE_ASSIGNMENTS,
    });

    setLeaveSubstitutionDraft(LEAVE_CASE_NO, LEAVE_PREVIEW_REQUEST);
    await previewLeaveSubstitutionFlow(LEAVE_CASE_NO, { client });
    expect(resolveLeaveSubstitutionMachineState(state())).toMatchObject({
      type: 'preview_ready',
      preview: LEAVE_PREVIEW,
    });

    // The component must ask for confirmation before invoking this mutation boundary.
    await applyLeaveSubstitutionFlow(LEAVE_CASE_NO, LEAVE_APPLY_REQUEST, { client });

    expect(vi.mocked(client.listAssignments)).toHaveBeenCalledTimes(2);
    expect(vi.mocked(client.preview)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(client.apply)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(client.preview).mock.calls[0]?.[1]).toEqual(LEAVE_PREVIEW_REQUEST);
    expect(vi.mocked(client.apply).mock.calls[0]?.[1]).toEqual(LEAVE_APPLY_REQUEST);
    expect(resolveLeaveSubstitutionMachineState(state())).toMatchObject({
      type: 'observed',
      assignments: LEAVE_OBSERVED_ASSIGNMENTS,
      receipt: LEAVE_RECEIPT,
    });
  });

  it('沒有 assignments 時不得進入 Preview，並保留 query_ready 的空資料狀態', async () => {
    const client = fakeClient();
    vi.mocked(client.listAssignments).mockResolvedValue([]);
    vi.mocked(client.preview).mockResolvedValue(LEAVE_PREVIEW);
    await queryLeaveSubstitutionFlow(LEAVE_CASE_NO, { client });
    expect(resolveLeaveSubstitutionMachineState(state())).toMatchObject({
      type: 'query_ready',
      assignments: [],
    });

    setLeaveSubstitutionDraft(LEAVE_CASE_NO, LEAVE_PREVIEW_REQUEST);
    await expect(
      previewLeaveSubstitutionFlow(LEAVE_CASE_NO, { client }),
    ).rejects.toBeInstanceOf(LeaveSubstitutionValidationError);
    expect(client.preview).not.toHaveBeenCalled();
  });

  it('stale Preview 只能進入 stale，不能自動 Apply', async () => {
    const client = fakeClient();
    vi.mocked(client.listAssignments).mockResolvedValue(LEAVE_ASSIGNMENTS);
    vi.mocked(client.preview).mockRejectedValue(
      new LeaveSubstitutionConflictError('Preview facts are stale.', {
        publicCode: 'stale_preview',
      }),
    );
    await queryLeaveSubstitutionFlow(LEAVE_CASE_NO, { client });

    setLeaveSubstitutionDraft(LEAVE_CASE_NO, LEAVE_PREVIEW_REQUEST);
    await expect(
      previewLeaveSubstitutionFlow(LEAVE_CASE_NO, { client }),
    ).rejects.toBeInstanceOf(LeaveSubstitutionConflictError);
    expect(resolveLeaveSubstitutionMachineState(state())).toMatchObject({
      type: 'stale',
      requiresFreshPreview: true,
    });
    expect(client.apply).not.toHaveBeenCalled();
  });

  it('503 outcome_unknown 只能用相同 payload 與相同 idempotency key 重試，成功後才 re-query', async () => {
    const client = fakeClient();
    vi.mocked(client.listAssignments)
      .mockResolvedValueOnce(LEAVE_ASSIGNMENTS)
      .mockResolvedValueOnce(LEAVE_OBSERVED_ASSIGNMENTS);
    vi.mocked(client.preview).mockResolvedValue(LEAVE_PREVIEW);
    vi.mocked(client.apply)
      .mockRejectedValueOnce(new LeaveSubstitutionUnavailableError('temporary outage'))
      .mockResolvedValueOnce(LEAVE_RECEIPT);
    await queryLeaveSubstitutionFlow(LEAVE_CASE_NO, { client });
    setLeaveSubstitutionDraft(LEAVE_CASE_NO, LEAVE_PREVIEW_REQUEST);
    await previewLeaveSubstitutionFlow(LEAVE_CASE_NO, { client });

    await expect(
      applyLeaveSubstitutionFlow(LEAVE_CASE_NO, LEAVE_APPLY_REQUEST, { client }),
    ).rejects.toBeInstanceOf(LeaveSubstitutionUnavailableError);
    const unknownState = resolveLeaveSubstitutionMachineState(state());
    expect(unknownState).toMatchObject({ type: 'outcome_unknown' });
    if (unknownState.type !== 'outcome_unknown') throw new Error('expected outcome_unknown');
    const stableKey = unknownState.idempotencyKey;
    const stableRequest = unknownState.applyRequest;

    await retryLeaveSubstitutionApplyFlow(LEAVE_CASE_NO, { client });

    expect(client.apply).toHaveBeenCalledTimes(2);
    const applyCalls = vi.mocked(client.apply).mock.calls;
    expect(applyCalls[1]?.[1]).toEqual(stableRequest);
    expect(applyCalls[0]?.[2]?.idempotencyKey).toBe(stableKey);
    expect(applyCalls[1]?.[2]?.idempotencyKey).toBe(stableKey);
    expect(client.listAssignments).toHaveBeenCalledTimes(2);
    expect(resolveLeaveSubstitutionMachineState(state())).toMatchObject({
      type: 'observed',
      receipt: LEAVE_RECEIPT,
    });
  });
});
