import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderGovernmentSubsidyLane } from '../../../../../../../components/OrderGovernmentSubsidyLane';

import { subsidyPeriodClient, type SubsidyPeriod } from '../../../../../../../api/government_subsidy/period_reconciliation_client';
import { orderGovernmentSubsidyProjectionClient } from '../../../../../../../api/orders/order_government_subsidy_projection_client';
import { transport } from '../../../../../../../api/shared/transport';
import { afterEach } from 'vitest';

afterEach(() => vi.restoreAllMocks());

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
    service_end_date: '2026-09-30',
    claim_quarter: 3,
    claim_application_year: 2026,
    claim_application_month: 10,
    claim_submitted_at: missing ? null : '2026-10-05T09:00:00+08:00',
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
    service_end_confirmed: true, estimated_subsidy_amount_ntd: missing ? null : 23100, estimate_unavailable_reason: null, confirmed_approved_amount_ntd: null, outstanding_amount_ntd: null,
    overpayment_identity: null,
    overpayment_remaining_ntd: null,
  };
}

describe('財務中心 Government Subsidy cross-order query', () => {
  beforeEach(() => {
    vi.spyOn(subsidyPeriodClient, 'query').mockImplementation(async (period: SubsidyPeriod) => ({
      period, version: 2, label: `${period.year} 年第 ${period.index} 季`,
      lines: [{ case_no: 'CASE-GAP', service_end_date: '2026-09-30', amount_ntd: null, unavailable_reason: 'scheduling_effective_generation_invalid' },
        { case_no: 'CASE-SUBMITTED', service_end_date: '2026-09-30', amount_ntd: 23100, unavailable_reason: null }],
      total_ntd: null, coverage: [], blocked_cases: [], recorded_lines: [], changed_cases: [], can_reconcile: false,
    }));
    vi.spyOn(subsidyPeriodClient, 'bankRows').mockResolvedValue([]);
    vi.spyOn(subsidyPeriodClient, 'reconcile');
  });

  it('由現行整期查詢顯示計數、資料缺口與 owner 金額，切換期間只重新查詢', async () => {
    render(<OrderGovernmentSubsidyLane />);
    fireEvent.click(await screen.findByRole('button', { name: /政府補助結算支線/ }));
    expect(await screen.findByText('CASE-GAP')).toBeInTheDocument();
    expect(subsidyPeriodClient.query).toHaveBeenCalledWith(
      { unit: 'quarter', year: new Date().getFullYear(), index: Math.floor(new Date().getMonth() / 3) + 1 }, expect.any(AbortSignal));
    expect(screen.getByText('排班資料待確認')).toBeInTheDocument();
    expect(screen.getByText(/・2 件・本期補助總額/)).toBeInTheDocument();
    expect(screen.getByText('CASE-SUBMITTED')).toBeInTheDocument();
    expect(screen.getByText('NT$ 23,100')).toBeInTheDocument();
    expect(screen.getAllByText('2026-09-30')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: /申請草稿 0/ })).not.toBeInTheDocument();
    expect(screen.queryByText('government_subsidy.claim_batches.query')).not.toBeInTheDocument();
    expect(screen.queryByText('技術詳情與資料來源')).not.toBeInTheDocument();
    expect(document.querySelector('a[href^="/api/v1/government-subsidy/"]')).toBeNull();
    expect(screen.getByRole('button', { name: '核銷本期入款' })).toBeDisabled();
    const targetQuarter = Math.floor(new Date().getMonth() / 3) + 1 === 3 ? 4 : 3;
    fireEvent.change(screen.getByLabelText('季度'), { target: { value: String(targetQuarter) } });
    await waitFor(() => expect(subsidyPeriodClient.query).toHaveBeenLastCalledWith(
      { unit: 'quarter', year: new Date().getFullYear(), index: targetQuarter }, expect.any(AbortSignal)));
    expect(subsidyPeriodClient.query).toHaveBeenCalledTimes(2);
    expect(subsidyPeriodClient.reconcile).not.toHaveBeenCalled();
  });

  it('保留舊 typed projection 的計數、77 小時、歸屬季、申請月與實際送件日契約；不把舊狀態冒充整期入款', async () => {
    const get = vi.spyOn(transport, 'get').mockImplementation(async (_path, options) => ({ success: true, message: 'ok', error: null, data: {
      items: options?.params?.substatus_code === 'submitted'
        ? [subsidyItem('CASE-SUBMITTED', 'submitted')]
        : [subsidyItem('CASE-GAP', 'claim_lineage_missing'), subsidyItem('CASE-SUBMITTED', 'submitted')],
      substatus_counts: counts(), next_cursor: null, etag: 'd'.repeat(64),
    } }));
    const controller = new AbortController();
    const page = await orderGovernmentSubsidyProjectionClient.getProjections({ page_size: 200 }, { signal: controller.signal });
    expect(page.substatus_counts).toEqual(counts());
    expect(page.items[0]).toMatchObject({ case_no: 'CASE-GAP', claim_batch_id: null, claim_submitted_at: null,
      blockers: [{ code: 'government_subsidy_claim_lineage_missing' }], net_allocated_ntd: 0 });
    expect(page.items[1]).toMatchObject({ case_no: 'CASE-SUBMITTED', claimed_hours: 77, requested_amount_ntd: 23100,
      service_end_date: '2026-09-30', claim_quarter: 3, claim_application_year: 2026,
      claim_application_month: 10, claim_submitted_at: '2026-10-05T09:00:00+08:00', net_allocated_ntd: 0 });
    const filtered = await orderGovernmentSubsidyProjectionClient.getProjections({ page_size: 200, substatus_code: 'submitted' }, { signal: controller.signal });
    expect(get).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({ params: { page_size: 200, substatus_code: 'submitted' }, signal: controller.signal }));
    expect(filtered.items.map(item => item.case_no)).toEqual(['CASE-SUBMITTED']);
    expect(filtered.substatus_counts).toEqual(counts());
    expect(subsidyPeriodClient.reconcile).not.toHaveBeenCalled();
  });
});
