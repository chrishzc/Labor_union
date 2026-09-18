import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { clientRegistryClient } from '../../../../../../../api/client_registry/client_registry_client';
import { transport } from '../../../../../../../api/shared/transport';

const response = { success: true, message: 'ok', data: { items: [], next_cursor: null, next_offset: null }, error: null };

describe('clientRegistryClient list query', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('test-token');
  });

  it('serializes structured server filters and preserves explicit false', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValue(response);

    await clientRegistryClient.list({
      query: ' 王 ', multiBirthCount: '雙胞胎', orderStatus: '洽談中', requiresCooking: false,
      sortBy: 'service_days', sortOrder: 'desc', after: 'CASE-001',
    });

    expect(get).toHaveBeenCalledWith('/api/v1/admin/registries/clients', {
      token: 'test-token',
      params: {
        query: '王', multi_birth_count: '雙胞胎', order_status: '洽談中', requires_cooking: false,
        sort_by: 'service_days', sort_order: 'desc', limit: 100, after: 'CASE-001', offset: undefined,
      },
    });
  });

  it('omits all optional filters instead of converting all to false', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValue(response);

    await clientRegistryClient.list();

    expect(get).toHaveBeenCalledWith('/api/v1/admin/registries/clients', {
      token: 'test-token',
      params: {
        query: undefined, multi_birth_count: undefined, order_status: undefined, requires_cooking: undefined,
        sort_by: undefined, sort_order: undefined, limit: 100, after: undefined, offset: undefined,
      },
    });
  });

  it('serializes an offset so every server-side sort can continue to the next page', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValue(response);

    await clientRegistryClient.list({ sortBy: 'customer_name', sortOrder: 'asc', limit: 100, offset: 100 });

    expect(get).toHaveBeenCalledWith('/api/v1/admin/registries/clients', expect.objectContaining({
      params: expect.objectContaining({ sort_by: 'customer_name', sort_order: 'asc', limit: 100, offset: 100 }),
    }));
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
      items: [{ multi_birth_count: null, service_days: null, requires_cooking: null }],
    });
  });

  it('downloads the filtered order-accounting workbook as xlsx', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Blob(['xlsx']), {
      status: 200,
      headers: {
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'Content-Disposition': 'attachment; filename="client-order-accounting.xlsx"',
      },
    }));
    vi.stubGlobal('fetch', fetchMock);

    const artifact = await clientRegistryClient.downloadOrderAccounting({
      query: ' 王 ', multiBirthCount: '雙胞胎', orderStatus: '訂單成立', requiresCooking: false,
      sortBy: 'service_days', sortOrder: 'desc', limit: 100,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/admin/registries/clients/export/order-accounting?query=%E7%8E%8B&multi_birth_count=%E9%9B%99%E8%83%9E%E8%83%8E&order_status=%E8%A8%82%E5%96%AE%E6%88%90%E7%AB%8B&requires_cooking=false&sort_by=service_days&sort_order=desc',
      { method: 'GET', headers: { Authorization: 'Bearer test-token' } },
    );
    expect(artifact.filename).toBe('client-order-accounting.xlsx');
    expect(artifact.blob.size).toBeGreaterThan(0);
  });
});
