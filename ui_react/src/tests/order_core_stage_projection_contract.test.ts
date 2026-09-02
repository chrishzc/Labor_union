import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  getOrderCoreStageTimelines,
  type OrderCoreStageProjectionQueryParams,
} from '../api/orders/order_core_stage_projection_client';
import {
  CORE_STAGE_CODES,
  OrderCoreStageTimelinePageSchema,
  SUBSTATUS_BY_STAGE_STATUS,
  substatusCodesForStage,
  type CoreStageCode,
  type CoreStageStatus,
} from '../api/orders/order_core_stage_projection_schemas';
import {
  adaptOrderCoreStageTimelinePage,
  OrderCoreStageProjectionAdapterError,
} from '../adapters/orders/order_core_stage_projection_adapter';

const transportMocks = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('../api/shared/transport', () => ({
  transport: { get: transportMocks.get },
}));

vi.mock('../api/auth/session_client', () => ({
  sessionClient: { getToken: vi.fn(() => 'test-token') },
}));

function stage(code: CoreStageCode, status: CoreStageStatus, caseNo: string) {
  return {
    ordinal: CORE_STAGE_CODES.indexOf(code) + 1,
    code,
    label: code,
    owner: `owner-${code}`,
    status,
    substatus_code: SUBSTATUS_BY_STAGE_STATUS[code][status],
    source: { owner: `source-${code}`, identity: `${code}:${caseNo}`, version: 1 },
    occurred_at: null,
    blockers: [],
    warnings: [],
    available_read_actions: [],
    availability_reason: status === 'unavailable' ? `${code}_missing` : null,
  };
}

function timeline(caseNo = 'CASE-001', currentCode: CoreStageCode = 'formal_service') {
  const currentStatus: CoreStageStatus = 'in_progress';
  return {
    case_no: caseNo,
    base_revision: 1,
    lifecycle_status: '服務中',
    branch_type: 'normal',
    current_core_stage_code: currentCode,
    current_core_stage_ordinal: CORE_STAGE_CODES.indexOf(currentCode) + 1,
    core_stages: CORE_STAGE_CODES.map((code) => stage(
      code,
      code === currentCode ? currentStatus : 'completed',
      caseNo,
    )),
    source_projection_digest: 'a'.repeat(64),
  };
}

function page(currentCode: CoreStageCode = 'formal_service') {
  const counts = Object.fromEntries(CORE_STAGE_CODES.map((code) => [code, 0]));
  counts[currentCode] = 1;
  return {
    items: [timeline('CASE-001', currentCode)],
    stage_counts: counts,
    substatus_counts: Object.fromEntries(
      substatusCodesForStage(currentCode).map((code) => [
        code,
        code === SUBSTATUS_BY_STAGE_STATUS[currentCode].in_progress ? 1 : 0,
      ]),
    ),
    next_cursor: null,
    etag: 'b'.repeat(64),
  };
}

describe('十三核心階段 React contract', () => {
  beforeEach(() => transportMocks.get.mockReset());

  it('strict schema 接受完整 contract，拒絕額外欄位與錯誤 stage/status/substatus mapping', () => {
    expect(OrderCoreStageTimelinePageSchema.parse(page()).items).toHaveLength(1);

    const withExtra = { ...page(), unexpected: true };
    expect(() => OrderCoreStageTimelinePageSchema.parse(withExtra)).toThrow();

    const invalid = page();
    invalid.items[0].core_stages[9] = {
      ...invalid.items[0].core_stages[9],
      substatus_code: 'waiting_to_start',
    };
    expect(() => OrderCoreStageTimelinePageSchema.parse(invalid)).toThrow();
  });

  it('adapter 拒絕與 requested stage 不一致的 server response', () => {
    const parsed = OrderCoreStageTimelinePageSchema.parse(page('intake_validation'));
    expect(() => adaptOrderCoreStageTimelinePage(parsed, {
      stage: 'formal_service',
      branch_type: 'normal',
    })).toThrow(OrderCoreStageProjectionAdapterError);
  });

  it('typed client 拒絕跨階段 substatus，並原樣送出合法正式 query', async () => {
    const invalidParams = {
      stage: 'formal_service',
      substatus_code: 'intake_pending',
    } as unknown as OrderCoreStageProjectionQueryParams;
    await expect(getOrderCoreStageTimelines(invalidParams)).rejects.toThrow();
    expect(transportMocks.get).not.toHaveBeenCalled();

    transportMocks.get.mockResolvedValue({
      success: true,
      message: 'ok',
      data: page(),
      error: null,
    });
    await expect(getOrderCoreStageTimelines({
      page_size: 200,
      lifecycle_scope: 'all',
      stage: 'formal_service',
      substatus_code: 'service_in_progress',
      blocker_only: true,
      warning_only: true,
      branch_type: 'normal',
    })).resolves.toMatchObject({ items: [{ case_no: 'CASE-001' }] });

    expect(transportMocks.get).toHaveBeenCalledWith(
      '/api/orders/core-stage-timelines',
      expect.objectContaining({
        token: 'test-token',
        params: expect.objectContaining({
          page_size: 200,
          lifecycle_scope: 'all',
          stage: 'formal_service',
          substatus_code: 'service_in_progress',
          blocker_only: true,
          warning_only: true,
          branch_type: 'normal',
        }),
      }),
    );
  });
});
