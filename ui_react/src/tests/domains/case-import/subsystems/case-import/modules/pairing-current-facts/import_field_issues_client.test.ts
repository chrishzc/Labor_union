import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { loadCurrentImportFieldIssuesForCases, type ImportFieldIssueCase } from '../../../../../../../api/case_import/import_field_issues';
import { transport } from '../../../../../../../api/shared/transport';
import { ApiDecodeError, ApiHttpError } from '../../../../../../../api/shared/typed_errors';

function issueCase(caseNo: string): ImportFieldIssueCase {
  return { case_no: caseNo, issues: [{ source: 'hcm', owner: 'client_profile', field: 'phone', source_field: 'phone', code: 'invalid_phone', message: '電話格式有誤' }] };
}

function page(items: ImportFieldIssueCase[], nextPage: number | null) {
  return { data: { items, next_page: nextPage } };
}

describe('current import field issue client pagination', () => {
  beforeEach(() => {
    sessionClient.setSession('import-field-issues-test-token', { id: 1, username: 'tester', display_name: '測試', role: 'operator', linked_line_user_id: null, capabilities: [], is_root: false, access_control_version: 1 });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
  });

  it('continues past an empty current-fact page when its cursor advances', async () => {
    const target = issueCase('case-target');
    const get = vi.spyOn(transport, 'get')
      .mockResolvedValueOnce(page([], 2))
      .mockResolvedValueOnce(page([target], null));

    await expect(loadCurrentImportFieldIssuesForCases(['case-target'])).resolves.toEqual([target]);
    expect(get).toHaveBeenCalledTimes(2);
    expect(get).toHaveBeenNthCalledWith(1, '/api/v1/case-import/field-issues', { token: 'import-field-issues-test-token', params: { page: 1, page_size: 100 }, signal: undefined });
    expect(get).toHaveBeenNthCalledWith(2, '/api/v1/case-import/field-issues', { token: 'import-field-issues-test-token', params: { page: 2, page_size: 100 }, signal: undefined });
  });

  it('skips unrelated cases and repeated matches, stopping when all unique cases are found', async () => {
    const first = issueCase('case-first');
    const second = issueCase('case-second');
    const get = vi.spyOn(transport, 'get')
      .mockResolvedValueOnce(page([issueCase('unrelated'), first], 2))
      .mockResolvedValueOnce(page([first, issueCase('also-unrelated')], 3))
      .mockResolvedValueOnce(page([second, second], 4));

    await expect(loadCurrentImportFieldIssuesForCases(['case-first', 'case-first', 'case-second'])).resolves.toEqual([first, second]);
    expect(get).toHaveBeenCalledTimes(3);
    expect(get.mock.calls.map(([, options]) => options?.params?.page)).toEqual([1, 2, 3]);
  });

  it.each([1, 0])('rejects a non-increasing next cursor %s', async (nextPage) => {
    const get = vi.spyOn(transport, 'get').mockResolvedValueOnce(page([issueCase('unrelated')], nextPage));

    await expect(loadCurrentImportFieldIssuesForCases(['case-target'])).rejects.toThrow('進件欄位問題分頁無法繼續');
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('propagates HTTP 503 after a partial match instead of returning partial or empty results', async () => {
    const failure = new ApiHttpError(503, 'unavailable', '暫時無法讀取', true);
    const get = vi.spyOn(transport, 'get')
      .mockResolvedValueOnce(page([issueCase('case-first')], 2))
      .mockRejectedValueOnce(failure);

    await expect(loadCurrentImportFieldIssuesForCases(['case-first', 'case-second'])).rejects.toBe(failure);
    expect(get).toHaveBeenCalledTimes(2);
  });

  it('propagates runtime decoding errors instead of treating invalid data as an empty page', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValueOnce({ data: { items: [], next_page: '2' } });

    await expect(loadCurrentImportFieldIssuesForCases(['case-target'])).rejects.toBeInstanceOf(ApiDecodeError);
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('passes the abort signal and stops before fetching the next page after cancellation', async () => {
    const controller = new AbortController();
    const reason = new DOMException('cancelled', 'AbortError');
    const get = vi.spyOn(transport, 'get').mockImplementationOnce(async () => {
      controller.abort(reason);
      return page([issueCase('unrelated')], 2);
    });

    await expect(loadCurrentImportFieldIssuesForCases(['case-target'], { signal: controller.signal })).rejects.toBe(reason);
    expect(get).toHaveBeenCalledTimes(1);
    expect(get.mock.calls[0]?.[1]?.signal).toBe(controller.signal);
  });

  it('makes no request for an empty case list, including when signed out', async () => {
    sessionClient.clearSession();
    const get = vi.spyOn(transport, 'get');

    await expect(loadCurrentImportFieldIssuesForCases([])).resolves.toEqual([]);
    expect(get).not.toHaveBeenCalled();
  });
});
