import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { OrderWorkbenchV2Page } from '../pages/OrderWorkbenchV2Page';

const source = { owner: 'test-owner', identity: 'test:1', version: 1 };
const emptyNotice: never[] = [];
const makeStage = (ordinal: number, code: string, status: string, settlement: unknown[] = []) => ({
  ordinal,
  code,
  label: code,
  owner: 'test-owner',
  status,
  source,
  occurred_at: null,
  blockers: emptyNotice,
  warnings: emptyNotice,
  available_actions: [],
  availability_reason: null,
  settlement,
});
const makeStep = (ordinal: number, status: string) => ({
  ordinal,
  code: `step_${ordinal}`,
  label: `step ${ordinal}`,
  owner: 'test-owner',
  status,
  occurred_at: null,
  blockers: [],
  warnings: [],
  available_actions: [],
  availability_reason: null,
});

function timeline(caseNo: string, lifecycle: string, currentStep: number | null, serviceStatus: string) {
  const stepStatuses = Array.from({ length: 11 }, (_, index) => {
    const ordinal = index + 1;
    if (currentStep === null) return 'completed';
    if (ordinal < currentStep) return 'completed';
    if (ordinal === currentStep) return serviceStatus;
    return 'not_started';
  });
  return {
    case_no: caseNo,
    base_revision: 1,
    lifecycle_status: lifecycle,
    current_stage_code: currentStep === 10 ? 'active_service' : currentStep === 11 ? 'settlement_payout' : currentStep === null ? null : 'intake_terms',
    current_step_ordinal: currentStep,
    stages: [
      makeStage(1, 'intake_terms', currentStep === 1 ? serviceStatus : 'completed'),
      makeStage(2, 'matching_willingness', 'completed'),
      makeStage(3, 'client_review', 'completed'),
      makeStage(4, 'contract_deposit', 'completed'),
      makeStage(5, 'date_confirmation', 'completed'),
      makeStage(6, 'active_service', currentStep === 10 ? serviceStatus : 'completed'),
      makeStage(7, 'settlement_payout', currentStep === 11 ? serviceStatus : 'completed', [
        { code: 'service_completion', status: 'unavailable', source, occurred_at: null, availability_reason: 'service_completion_projection_missing' },
        { code: 'client_settlement', status: 'blocked', source, occurred_at: null, availability_reason: null },
        { code: 'staff_payout', status: 'blocked', source, occurred_at: null, availability_reason: null },
      ]),
    ],
    sop_steps: stepStatuses.map((status, index) => makeStep(index + 1, status)),
    projection_digest: 'a'.repeat(64),
  };
}

describe('待辦看板 Beta dry-run', () => {
  afterEach(() => vi.restoreAllMocks());

  it('保留 13 階段並可在第 10 階只看服務進行中', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      success: true,
      message: 'ok',
      error: null,
      data: {
        items: [
          timeline('CASE-ACTIVE', '服務中', 10, 'in_progress'),
          timeline('CASE-PLANNED', '訂單成立', 10, 'not_started'),
          timeline('CASE-HISTORY', '歷史訂單－服務完成', 11, 'completed'),
        ],
        stage_counts: {
          intake_terms: 0,
          matching_willingness: 0,
          client_review: 0,
          contract_deposit: 0,
          date_confirmation: 0,
          active_service: 2,
          settlement_payout: 1,
        },
        next_cursor: null,
        etag: 'b'.repeat(64),
      },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));

    render(<OrderWorkbenchV2Page />);

    await waitFor(() => expect(screen.getByText('CASE-ACTIVE')).toBeInTheDocument());
    expect(screen.getByText('13')).toBeInTheDocument();
    expect(screen.getByText('歷史訂單支線')).toBeInTheDocument();
    expect(screen.getByText('政府補助結算支線')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /10 排班\/服務 2/ }));
    expect(screen.getByRole('button', { name: /服務進行中 1/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /待開工 1/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /服務進行中 1/ }));
    expect(screen.getByText('CASE-ACTIVE')).toBeInTheDocument();
    expect(screen.queryByText('CASE-PLANNED')).not.toBeInTheDocument();
  });
});
