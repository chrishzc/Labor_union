import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CORE_STAGE_CODES,
  SUBSTATUS_BY_STAGE_STATUS,
  type CoreStageCode,
} from '../api/orders/order_core_stage_projection_schemas';
import { OrderWorkbenchV2Page } from '../pages/OrderWorkbenchV2Page';

const mocks = vi.hoisted(() => ({
  getCoreStageTimelines: vi.fn(),
  loadSummaries: vi.fn(),
  getSubsidyProjections: vi.fn(),
}));

vi.mock('../api/orders/order_core_stage_projection_client', () => ({
  orderCoreStageProjectionClient: {
    getCoreStageTimelines: mocks.getCoreStageTimelines,
  },
}));

vi.mock('../api/orders/order_query_client', () => ({
  loadAllOrderSummaries: mocks.loadSummaries,
  ordersQueryClient: { getOrderSummaries: vi.fn() },
}));

vi.mock('../api/orders/order_government_subsidy_projection_client', () => ({
  GOVERNMENT_SUBSIDY_SUBSTATUS_CODES: [
    'claim_lineage_missing',
    'draft',
    'submitted',
    'approved',
    'partially_paid',
    'paid',
    'pending_review',
    'offset_reserved',
    'offset_applied',
    'return_payable',
    'partially_returned',
    'returned',
  ],
  orderGovernmentSubsidyProjectionClient: {
    getProjections: mocks.getSubsidyProjections,
  },
}));

function stage(code: CoreStageCode) {
  const status: 'in_progress' | 'completed' = code === 'intake_validation' ? 'in_progress' : 'completed';
  return {
    ordinal: CORE_STAGE_CODES.indexOf(code) + 1,
    code,
    label: code,
    owner: `owner-${code}`,
    status,
    substatus_code: SUBSTATUS_BY_STAGE_STATUS[code][status],
    source: { owner: `owner-${code}`, identity: `${code}:CASE-CORE`, version: 1 },
    occurred_at: null,
    blockers: [],
    warnings: [],
    available_read_actions: [],
    availability_reason: null,
  };
}

function corePage() {
  const counts = Object.fromEntries(CORE_STAGE_CODES.map((code) => [code, 0]));
  counts.intake_validation = 1;
  return {
    items: [{
      case_no: 'CASE-CORE',
      base_revision: 1,
      lifecycle_status: '服務中',
      branch_type: 'normal',
      current_core_stage_code: 'intake_validation',
      current_core_stage_ordinal: 1,
      historical_current_owner_stage_code: null,
      historical_current_owner_stage_ordinal: null,
      core_stages: CORE_STAGE_CODES.map(stage),
      source_projection_digest: 'a'.repeat(64),
    }],
    stage_counts: counts,
    substatus_counts: {
      intake_pending: 0,
      intake_in_progress: 1,
      intake_blocked: 0,
      data_complete: 0,
      intake_unavailable: 0,
    },
    historical_lifecycle_counts: {
      unserved: 0,
      in_service: 0,
      service_completed: 0,
      accounting_completed: 0,
    },
    next_cursor: null,
    etag: 'b'.repeat(64),
  };
}

function counts(overrides: Record<string, number> = {}) {
  return {
    claim_lineage_missing: 1,
    draft: 0,
    submitted: 1,
    approved: 0,
    partially_paid: 0,
    paid: 0,
    pending_review: 0,
    offset_reserved: 0,
    offset_applied: 0,
    return_payable: 0,
    partially_returned: 0,
    returned: 0,
    ...overrides,
  };
}

function subsidyItem(caseNo: string, substatus: 'claim_lineage_missing' | 'submitted') {
  const missing = substatus === 'claim_lineage_missing';
  return {
    case_no: caseNo,
    substatus_code: substatus,
    identity_status: '一般市民',
    source: {
      owner: 'Government Subsidy',
      identity: missing ? null : 'claim-batch:8',
      version: missing ? null : 2,
    },
    occurred_at: null,
    blockers: missing
      ? [{
        code: 'government_subsidy_claim_lineage_missing',
        message: '正常訂單尚未找到正式 Government Subsidy claim 關聯。',
      }]
      : [],
    warnings: [],
    available_read_actions: [{
      action_id: missing
        ? 'government_subsidy.claim_batches.query'
        : 'government_subsidy.claim_batch.query',
      method: 'GET',
      path: missing
        ? '/api/v1/government-subsidy/claim-batches'
        : '/api/v1/government-subsidy/claim-batches/8',
    }],
    claim_batch_id: missing ? null : 8,
    claim_item_count: missing ? 0 : 1,
    claimed_hours: missing ? 0 : 77,
    unit_price_ntd: missing ? null : 300,
    requested_amount_ntd: missing ? 0 : 23100,
    approved_amount_ntd: 0,
    net_allocated_ntd: 0,
    overpayment_identity: null,
    overpayment_remaining_ntd: null,
  };
}

describe('待辦看板 Beta Government Subsidy side lane', () => {
  beforeEach(() => {
    mocks.getCoreStageTimelines.mockReset();
    mocks.loadSummaries.mockReset();
    mocks.getSubsidyProjections.mockReset();
    mocks.getCoreStageTimelines.mockResolvedValue(corePage());
    mocks.loadSummaries.mockResolvedValue({ items: [], next_cursor: null, etag: 'c'.repeat(64) });
    mocks.getSubsidyProjections.mockImplementation(async (params) => ({
      items: params.substatus_code === 'submitted'
        ? [subsidyItem('CASE-SUBMITTED', 'submitted')]
        : [
          subsidyItem('CASE-GAP', 'claim_lineage_missing'),
          subsidyItem('CASE-SUBMITTED', 'submitted'),
        ],
      substatus_counts: counts(),
      next_cursor: null,
      etag: 'd'.repeat(64),
    }));
  });

  it('由 server projection 顯示計數、資料缺口、owner readback 並以 substatus 重新查詢', async () => {
    render(<OrderWorkbenchV2Page />);

    const lane = await screen.findByRole('button', { name: /政府補助結算支線/ });
    fireEvent.click(lane);

    await waitFor(() => expect(mocks.getSubsidyProjections).toHaveBeenCalledWith(
      {
        page_size: 200,
        case_no_search: undefined,
        substatus_code: undefined,
      },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));

    expect(await screen.findByText('CASE-GAP')).toBeInTheDocument();
    expect(screen.getByText('正常訂單尚未找到正式 Government Subsidy claim 關聯。')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'government_subsidy.claim_batches.query' }))
      .toHaveAttribute('href', '/api/v1/government-subsidy/claim-batches');
    expect(screen.getByText('CASE-SUBMITTED')).toBeInTheDocument();
    expect(screen.getByText('77 小時')).toBeInTheDocument();
    expect(screen.getByText(/23,100/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /已送件 1/ }));

    await waitFor(() => expect(mocks.getSubsidyProjections).toHaveBeenLastCalledWith(
      expect.objectContaining({ substatus_code: 'submitted' }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    await waitFor(() => expect(screen.queryByText('CASE-GAP')).not.toBeInTheDocument());
    expect(screen.getByText('CASE-SUBMITTED')).toBeInTheDocument();
  });
});
