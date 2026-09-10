import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderGovernmentSubsidyLane } from '../../../../../../../components/OrderGovernmentSubsidyLane';

const mocks = vi.hoisted(() => ({
  getSubsidyProjections: vi.fn(),
}));

vi.mock('../../../../../../../api/orders/order_government_subsidy_projection_client', () => ({
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

describe('財務中心 Government Subsidy cross-order query', () => {
  beforeEach(() => {
    mocks.getSubsidyProjections.mockReset();
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
    render(<OrderGovernmentSubsidyLane />);

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
    expect(screen.queryByRole('button', { name: /申請草稿 0/ })).not.toBeInTheDocument();
    expect(screen.getByText('補助資料尚有待處理項目，請核對申請與入款紀錄。')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: '前往營運與補助報表' }))
      .toEqual(expect.arrayContaining([
        expect.objectContaining({ hash: '#reports' }),
      ]));
    expect(screen.queryByText('government_subsidy.claim_batches.query')).not.toBeInTheDocument();
    expect(screen.queryByText('技術詳情與資料來源')).not.toBeInTheDocument();
    expect(document.querySelector('a[href^="/api/v1/government-subsidy/"]')).toBeNull();
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
