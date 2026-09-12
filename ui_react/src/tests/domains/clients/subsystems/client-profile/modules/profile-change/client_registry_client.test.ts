import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { clientRegistryClient } from '../../../../../../../api/client_registry/client_registry_client';
import { transport } from '../../../../../../../api/shared/transport';

const response = { success: true, message: 'ok', data: { items: [], next_cursor: null }, error: null };

describe('clientRegistryClient list query', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('test-token');
  });

  it('serializes structured server filters and preserves explicit false', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValue(response);

    await clientRegistryClient.list({
      query: ' 王 ', hasBabyInfo: false, serviceDays: 26, requiresCooking: false,
      sortBy: 'service_days', sortOrder: 'desc', after: 'CASE-001',
    });

    expect(get).toHaveBeenCalledWith('/api/v1/admin/registries/clients', {
      token: 'test-token',
      params: {
        query: '王', has_baby_info: false, service_days: 26, requires_cooking: false,
        sort_by: 'service_days', sort_order: 'desc', limit: 100, after: 'CASE-001',
      },
    });
  });

  it('omits all optional filters instead of converting all to false', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValue(response);

    await clientRegistryClient.list();

    expect(get).toHaveBeenCalledWith('/api/v1/admin/registries/clients', {
      token: 'test-token',
      params: {
        query: undefined, has_baby_info: undefined, service_days: undefined, requires_cooking: undefined,
        sort_by: undefined, sort_order: undefined, limit: 100, after: undefined,
      },
    });
  });

  it('accepts the previous list shape while the additive roster fields are not yet present', async () => {
    vi.spyOn(transport, 'get').mockResolvedValue({
      success: true,
      message: 'ok',
      data: {
        items: [{
          client_id: 7,
          case_no: 'CASE-001',
          name: '王小明',
          phone: '0912345678',
          city: '新竹市',
          planned_start_date: null,
          order_status: 'matching',
        }],
        next_cursor: null,
      },
      error: null,
    });

    await expect(clientRegistryClient.list()).resolves.toMatchObject({
      items: [{ baby_info: null, service_days: null, requires_cooking: null }],
    });
  });
});
