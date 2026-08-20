/**
 * File: hcm_import_result_client.test.ts
 * Description: 驗證 HCM recent-results GET、fresh bearer、strict decode與缺session零fetch。
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { queryHcmImportResults } from '../api/case_import/hcm_import_result_client';
import { detailedHcmResult } from './fixtures/hcm_import_result_fixtures';

function setSession(): void {
  sessionClient.setSession('result-token', { id: 1, username: 'result-test', display_name: 'Result Test', role: 'operator', linked_line_user_id: null, capabilities: [], is_root: false, access_control_version: 1 });
}

describe('HCM import result client', () => {
  afterEach(() => { sessionClient.clearSession(); vi.restoreAllMocks(); });

  it('sends one authenticated GET and strictly decodes the result page', async () => {
    setSession();
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true, message: 'ok', data: { items: [detailedHcmResult], next_cursor: null }, error: null }), { status: 200, headers: { 'content-type': 'application/json' } }));
    const page = await queryHcmImportResults({ limit: 20 });
    expect(page.items[0].receipt_id).toBe(8);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    expect(globalThis.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/v1/case-import/hcm/workbooks/results?limit=20'), expect.objectContaining({ method: 'GET' }));
  });

  it('fails before fetch without a memory session', async () => {
    globalThis.fetch = vi.fn();
    await expect(queryHcmImportResults()).rejects.toMatchObject({ code: 'hcm_result_unauthenticated' });
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('rejects extra response fields', async () => {
    setSession();
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true, message: 'ok', data: { items: [{ ...detailedHcmResult, extra: true }], next_cursor: null }, error: null }), { status: 200, headers: { 'content-type': 'application/json' } }));
    await expect(queryHcmImportResults()).rejects.toThrow();
  });
});
