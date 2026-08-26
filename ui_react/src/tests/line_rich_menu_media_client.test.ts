/**
 * File: line_rich_menu_media_client.test.ts
 * Description: 驗證 Rich Menu 背景圖 owner-scoped typed Query、固定分頁與 strict fail-closed。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { lineRichMenuMediaClient } from '../api/line_rich_menu_media/line_rich_menu_media_client';

const ITEM = {
  asset_id: 41,
  menu_definition_id: 'customer_menu',
  original_filename: 'customer-menu.png',
  mime_type: 'image/png',
  file_size: 1024,
  sha256: 'a'.repeat(64),
  width: 2500,
  height: 843,
  created_at: '2026-08-26T00:00:00Z',
  deleted_at: null,
  selectable: true,
  business_reason: null,
  asset_version: 'b'.repeat(64),
};

function response(data: unknown): Response {
  return new Response(JSON.stringify({ success: true, message: 'Success', data, error: null }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

describe('LINE Rich Menu media client', () => {
  beforeEach(() => {
    sessionClient.setSession('media-token', {
      id: 8,
      username: 'media-reader',
      display_name: '背景圖查詢',
      role: 'operator',
      linked_line_user_id: null,
      capabilities: [],
      is_root: false,
      access_control_version: 1,
    });
  });
  afterEach(() => {
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('以目前選單 owner 查詢固定第 1 頁 100 筆並驗證 Session', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({
      items: [ITEM], page: 1, page_size: 100, total: 1, total_pages: 1,
    }));
    globalThis.fetch = fetchMock;

    const page = await lineRichMenuMediaClient.list('customer_menu');

    expect(page.items).toHaveLength(1);
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/v1/line/media-assets/rich-menu?menu_definition_id=customer_menu&page=1&page_size=100',
    );
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization')).toBe(
      'Bearer media-token',
    );
  });

  it('owner 漂移、extra 欄位與非法 asset version 均 fail closed', async () => {
    for (const item of [
      { ...ITEM, menu_definition_id: 'staff_menu' },
      { ...ITEM, storage_key: 'secret/path.png' },
      { ...ITEM, asset_version: 'not-a-version' },
    ]) {
      globalThis.fetch = vi.fn().mockResolvedValue(response({
        items: [item], page: 1, page_size: 100, total: 1, total_pages: 1,
      }));
      await expect(lineRichMenuMediaClient.list('customer_menu')).rejects.toBeInstanceOf(Error);
    }
  });

  it('未登入與非 canonical menu identity 在 request 前拒絕', async () => {
    globalThis.fetch = vi.fn();
    await expect(lineRichMenuMediaClient.list(' customer_menu ')).rejects.toBeInstanceOf(Error);
    sessionClient.clearSession();
    await expect(lineRichMenuMediaClient.list('customer_menu')).rejects.toBeInstanceOf(Error);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
