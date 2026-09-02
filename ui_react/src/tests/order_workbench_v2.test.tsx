import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderWorkbenchV2Page } from '../pages/OrderWorkbenchV2Page';

const clientMocks = vi.hoisted(() => ({
  loadTimelines: vi.fn(),
  loadSummaries: vi.fn(),
}));

vi.mock('../api/orders/order_stage_projection_client', () => ({
  loadAllOrderOperationalTimelines: clientMocks.loadTimelines,
  orderStageProjectionClient: { getOperationalTimelines: vi.fn() },
}));

vi.mock('../api/orders/order_query_client', () => ({
  loadAllOrderSummaries: clientMocks.loadSummaries,
  ordersQueryClient: { getOrderSummaries: vi.fn() },
}));

const source = { owner: 'test-owner', identity: 'test:1', version: 1 };
const makeStage = (ordinal: number, code: string, status: string, settlement: unknown[] = []) => ({
  ordinal,
  code,
  label: code,
  owner: 'test-owner',
  status,
  source,
  occurred_at: null,
  blockers: [],
  warnings: [],
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

function timelinePage(items: unknown[]) {
  return {
    items,
    stage_counts: {
      intake_terms: 0,
      matching_willingness: 0,
      client_review: 0,
      contract_deposit: 0,
      date_confirmation: 0,
      active_service: items.length,
      settlement_payout: 0,
    },
    next_cursor: null,
    etag: 'b'.repeat(64),
  };
}

function orderSummary(caseNo: string, clientName: string, staffName: string | null, startDate: string, endDate: string) {
  return {
    case_no: caseNo,
    client_name: clientName,
    order_status: '服務中',
    staff_name: staffName,
    identity_status: '一般市民',
    start_date: startDate,
    end_date: endDate,
    actual_start_date: null,
    actual_end_date: null,
    service_days: 20,
    total_employer_self_pay_payable: 12000,
  };
}

function summaryPage(items: unknown[]) {
  return {
    items,
    next_cursor: null,
    etag: 'c'.repeat(64),
  };
}

function cardFor(caseNo: string): HTMLElement {
  const card = screen.getByText(caseNo).closest('article');
  if (!(card instanceof HTMLElement)) throw new Error(`找不到 ${caseNo} 案件卡`);
  return card;
}

describe('待辦看板 Beta dry-run', () => {
  beforeEach(() => {
    clientMocks.loadTimelines.mockReset();
    clientMocks.loadSummaries.mockReset();
  });

  it('以 case_no 配對正式摘要，保留缺摘要案件與第 10 階子狀態篩選', async () => {
    clientMocks.loadTimelines.mockResolvedValue(timelinePage([
      timeline('CASE-ACTIVE', '服務中', 10, 'in_progress'),
      timeline('CASE-PLANNED', '訂單成立', 10, 'not_started'),
      timeline('CASE-MISSING', '服務中', 10, 'in_progress'),
      timeline('CASE-HISTORY', '歷史訂單－服務完成', 11, 'completed'),
    ]));
    clientMocks.loadSummaries.mockResolvedValue(summaryPage([
      orderSummary('CASE-PLANNED', '林小芳', null, '2026-10-01', '2026-10-20'),
      orderSummary('CASE-ACTIVE', '王小明', '陳月嫂', '2026-09-01', '2026-09-20'),
    ]));

    render(<OrderWorkbenchV2Page />);

    await waitFor(() => expect(screen.getByRole('button', { name: /10 排班\/服務 3/ })).toBeInTheDocument());
    expect(screen.getByText('歷史訂單支線')).toBeInTheDocument();
    expect(screen.getByText('政府補助結算支線')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /13 月嫂結算/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /10 排班\/服務 3/ }));

    await waitFor(() => {
      expect(within(cardFor('CASE-ACTIVE')).getByText('王小明')).toBeInTheDocument();
      expect(within(cardFor('CASE-ACTIVE')).getByText('2026-09-01 ~ 2026-09-20')).toBeInTheDocument();
      expect(within(cardFor('CASE-ACTIVE')).getByText('陳月嫂')).toBeInTheDocument();
      expect(within(cardFor('CASE-PLANNED')).getByText('林小芳')).toBeInTheDocument();
      expect(within(cardFor('CASE-PLANNED')).getByText('尚未正式指派')).toBeInTheDocument();
    });

    const missingCard = cardFor('CASE-MISSING');
    expect(within(missingCard).getByText('案件摘要不可用')).toBeInTheDocument();
    expect(within(missingCard).getByText('未取得與此案件編號相符的正式摘要。')).toBeInTheDocument();

    expect(screen.getByRole('button', { name: /服務進行中 2/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /待開工 1/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /服務進行中 2/ }));
    expect(screen.getByText('CASE-ACTIVE')).toBeInTheDocument();
    expect(screen.getByText('CASE-MISSING')).toBeInTheDocument();
    expect(screen.queryByText('CASE-PLANNED')).not.toBeInTheDocument();
  });

  it('摘要 Query 失敗時仍顯示 operational timeline 並標示摘要不可用', async () => {
    clientMocks.loadTimelines.mockResolvedValue(timelinePage([
      timeline('CASE-ACTIVE', '服務中', 10, 'in_progress'),
    ]));
    clientMocks.loadSummaries.mockRejectedValue(new Error('summary unavailable'));

    render(<OrderWorkbenchV2Page />);

    await waitFor(() => expect(screen.getByRole('button', { name: /10 排班\/服務 1/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /10 排班\/服務 1/ }));

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('案件摘要查詢失敗'));
    expect(screen.getByText('CASE-ACTIVE')).toBeInTheDocument();
    expect(within(cardFor('CASE-ACTIVE')).getByText('案件摘要不可用')).toBeInTheDocument();
    expect(within(cardFor('CASE-ACTIVE')).getByText('正式案件摘要查詢失敗；目前只顯示階段投影。')).toBeInTheDocument();
    expect(within(cardFor('CASE-ACTIVE')).getByText('Lifecycle：服務中')).toBeInTheDocument();
  });
});