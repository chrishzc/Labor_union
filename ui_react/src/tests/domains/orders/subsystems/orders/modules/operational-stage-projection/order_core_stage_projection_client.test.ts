import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getOrderCoreStageTimelines } from '../../../../../../../api/orders/order_core_stage_projection_client';

const transportMocks = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('../../../../../../../api/shared/transport', () => ({
  transport: { get: transportMocks.get },
}));

vi.mock('../../../../../../../api/auth/session_client', () => ({
  sessionClient: { getToken: vi.fn(() => 'test-token') },
}));

describe('十三核心階段查詢快取', () => {
  beforeEach(() => transportMocks.get.mockReset());

  it('待辦投影不沿用瀏覽器中的舊 304 回應內容', async () => {
    transportMocks.get.mockResolvedValue(null);

    await expect(getOrderCoreStageTimelines({
      workbench_scope: 'in_progress',
      page_size: 200,
      lifecycle_scope: 'all',
    })).rejects.toThrow();

    expect(transportMocks.get).toHaveBeenCalledWith(
      '/api/orders/core-stage-timelines',
      expect.objectContaining({
        token: 'test-token',
        cache: 'no-store',
      }),
    );
  });
});
