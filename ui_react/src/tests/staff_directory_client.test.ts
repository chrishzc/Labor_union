/**
 * File: staff_directory_client.test.ts
 * Description: 驗證 Staff 摘要 client 的 strict decode、最新 Session、cursor 與唯讀 GET 邊界。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  createStaffDirectoryClient,
  loadAllStaffDirectoryPages,
} from '../api/staff_directory/staff_directory_client';
import {
  StaffDirectoryUnauthenticatedError,
  StaffDirectoryAbortedError,
  StaffDirectoryValidationError,
} from '../api/staff_directory/staff_directory_errors';
import {
  STAFF_EMPTY_RESPONSE,
  STAFF_RESPONSE_DUPLICATE_IDS,
  STAFF_RESPONSE_EXTRA_FIELD,
  STAFF_RESPONSE_ONE,
  STAFF_RESPONSE_TWO,
} from './fixtures/staff/staff_directory_contract_fixtures';
import { STAFF_PROFILE } from './domains/staff/subsystems/staff/modules/staff-roster-profile/fixtures/staff_profile_contract_fixtures';
import { STAFF_QUALIFICATION_MASTER } from './fixtures/staff/staff_qualification_contract_fixtures';

function response(body: object, ok = true, status = 200) {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
  };
}

describe('staff directory client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    sessionClient.setSession('staff-token-1', {
      id: 7,
      username: 'staff-reader',
      display_name: 'Staff Reader',
      role: 'admin',
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
  });

  it('sends one GET with current memory token and strict cursor params', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response(STAFF_RESPONSE_ONE));
    const client = createStaffDirectoryClient();

    const page = await client.queryPage({ pageSize: 200 });

    expect(page).toEqual(STAFF_RESPONSE_ONE.data);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toBe('/api/v1/staff/summaries?page_size=200');
    expect(options?.method).toBe('GET');
    expect(options?.headers).toMatchObject({ Authorization: 'Bearer staff-token-1' });
  });

  it('uses the authenticated full roster only when the page asks for complete profiles', async () => {
    const body = { ...STAFF_RESPONSE_ONE, data:{ items:[{...STAFF_RESPONSE_ONE.data.items[0],profile:STAFF_PROFILE, service_profile:{...STAFF_QUALIFICATION_MASTER.service_profile,cooking_skills:[]}}],next_cursor:null } };
    globalThis.fetch = vi.fn().mockResolvedValue(response(body));
    const result = await createStaffDirectoryClient().queryPage({pageSize:200,includeProfile:true});
    expect(vi.mocked(globalThis.fetch).mock.calls[0][0]).toBe('/api/v1/staff/roster?page_size=200');
    expect(result.items[0].profile?.bank_accounts).toEqual(STAFF_PROFILE.bank_accounts);
  });

  it.each(['active', 'retired'] as const)('requests the %s roster without changing response fields', async (lifecycleState) => {
    const body = { ...STAFF_RESPONSE_ONE, data: { items: [{ ...STAFF_RESPONSE_ONE.data.items[0], profile: STAFF_PROFILE, service_profile: { ...STAFF_QUALIFICATION_MASTER.service_profile, cooking_skills: [] } }], next_cursor: null } };
    globalThis.fetch = vi.fn().mockResolvedValue(response(body));
    const result = await createStaffDirectoryClient().queryPage({ includeProfile: true, lifecycleState });
    expect(vi.mocked(globalThis.fetch).mock.calls[0][0]).toBe(`/api/v1/staff/roster?page_size=200&lifecycle_state=${lifecycleState}`);
    expect(result).toEqual(body.data);
  });

  it('rejects missing or misbound full profiles instead of presenting incomplete master data', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response(STAFF_RESPONSE_ONE));
    await expect(createStaffDirectoryClient().queryPage({includeProfile:true})).rejects.toThrow();
    globalThis.fetch = vi.fn().mockResolvedValue(response({ ...STAFF_RESPONSE_ONE, data:{ items:[{
      ...STAFF_RESPONSE_ONE.data.items[0], profile:{...STAFF_PROFILE,staff_id:99},
      service_profile:{...STAFF_QUALIFICATION_MASTER.service_profile,cooking_skills:[]},
    }],next_cursor:null } }));
    await expect(createStaffDirectoryClient().queryPage({includeProfile:true})).rejects.toThrow('月嫂主檔與清單對象不一致');
  });

  it('reads the rotated token for every request and rejects caller Authorization', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(STAFF_RESPONSE_ONE))
      .mockResolvedValueOnce(response(STAFF_RESPONSE_TWO));
    const client = createStaffDirectoryClient();
    await client.queryPage({}, { headers: { Authorization: 'Bearer injected' } });
    sessionClient.setSession('staff-token-2', {
      id: 8,
      username: 'rotated',
      display_name: 'Rotated',
      role: 'admin',
    });
    await client.queryPage({ afterId: 12 });

    expect(vi.mocked(globalThis.fetch).mock.calls[1][1]?.headers).toMatchObject({
      Authorization: 'Bearer staff-token-2',
    });
  });

  it('filters selectable summaries while leaving the historical label lookup unfiltered', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response(STAFF_RESPONSE_ONE));
    await createStaffDirectoryClient().queryPage({ lifecycleState: 'active' });
    expect(vi.mocked(globalThis.fetch).mock.calls[0][0]).toBe('/api/v1/staff/summaries?page_size=200&lifecycle_state=active');
    await createStaffDirectoryClient().queryPage();
    expect(vi.mocked(globalThis.fetch).mock.calls[1][0]).toBe('/api/v1/staff/summaries?page_size=200');
  });

  it('fails before fetch without a memory session', async () => {
    globalThis.fetch = vi.fn();
    sessionClient.clearSession();

    await expect(createStaffDirectoryClient().queryPage()).rejects.toBeInstanceOf(
      StaffDirectoryUnauthenticatedError
    );
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('strictly rejects extra fields and duplicate identities', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(STAFF_RESPONSE_EXTRA_FIELD))
      .mockResolvedValueOnce(response(STAFF_RESPONSE_DUPLICATE_IDS));
    const client = createStaffDirectoryClient();

    await expect(client.queryPage()).rejects.toBeInstanceOf(StaffDirectoryValidationError);
    await expect(client.queryPage()).rejects.toBeInstanceOf(StaffDirectoryValidationError);
  });

  it('rejects non-forward and repeated cursors without auto retry', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(STAFF_RESPONSE_ONE))
      .mockResolvedValueOnce(response({
        ...STAFF_RESPONSE_TWO,
        data: { items: STAFF_RESPONSE_TWO.data.items, next_cursor: 12 },
      }));
    const client = createStaffDirectoryClient();
    await client.queryPage();

    await expect(client.queryPage({ afterId: 12 })).rejects.toBeInstanceOf(
      StaffDirectoryValidationError
    );
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it('allows an operator retry after a failed next-page request', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(STAFF_RESPONSE_ONE))
      .mockRejectedValueOnce(new TypeError('temporary network failure'))
      .mockResolvedValueOnce(response(STAFF_RESPONSE_TWO));
    const client = createStaffDirectoryClient();
    await client.queryPage();

    await expect(client.queryPage({ afterId: 12 })).rejects.toBeTruthy();
    await expect(client.queryPage({ afterId: 12 })).resolves.toEqual(STAFF_RESPONSE_TWO.data);
    expect(globalThis.fetch).toHaveBeenCalledTimes(3);
  });

  it('loads every staff page for operator selectors', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(STAFF_RESPONSE_ONE))
      .mockResolvedValueOnce(response(STAFF_RESPONSE_TWO));
    const client = createStaffDirectoryClient();

    const page = await loadAllStaffDirectoryPages(client.queryPage.bind(client), { pageSize: 200 });

    expect(page.items).toEqual([...STAFF_RESPONSE_ONE.data.items, ...STAFF_RESPONSE_TWO.data.items]);
    expect(page.next_cursor).toBeNull();
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it('isolates concurrent list and search cursors while retaining duplicate protection per query', async () => {
    let finishFirst!: (value: ReturnType<typeof response>) => void;
    const delayed = new Promise<ReturnType<typeof response>>((resolve) => { finishFirst = resolve; });
    globalThis.fetch = vi.fn().mockReturnValueOnce(delayed)
      .mockResolvedValueOnce(response(STAFF_RESPONSE_ONE))
      .mockResolvedValueOnce(response(STAFF_RESPONSE_TWO))
      .mockResolvedValueOnce(response(STAFF_RESPONSE_TWO));
    const client = createStaffDirectoryClient();
    const list = { signal: new AbortController().signal };
    const search = { signal: new AbortController().signal };
    const listRequest = client.queryPage({}, list);
    await expect(client.queryPage({}, search)).resolves.toEqual(STAFF_RESPONSE_ONE.data);
    finishFirst(response(STAFF_RESPONSE_ONE));
    await expect(listRequest).resolves.toEqual(STAFF_RESPONSE_ONE.data);
    await expect(client.queryPage({ afterId: 12 }, list)).resolves.toEqual(STAFF_RESPONSE_TWO.data);
    await expect(client.queryPage({ afterId: 12 }, search)).resolves.toEqual(STAFF_RESPONSE_TWO.data);
    await expect(client.queryPage({ afterId: 12 }, list)).rejects.toBeInstanceOf(StaffDirectoryValidationError);
    expect(globalThis.fetch).toHaveBeenCalledTimes(4);
  });

  it('validates bounds and supports an empty page', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response(STAFF_EMPTY_RESPONSE));
    const client = createStaffDirectoryClient();

    await expect(client.queryPage({ pageSize: 0 })).rejects.toBeInstanceOf(
      StaffDirectoryValidationError
    );
    await expect(client.queryPage({ afterId: 1, staffId: 2 })).rejects.toBeInstanceOf(
      StaffDirectoryValidationError
    );
    await expect(client.queryPage()).resolves.toEqual(STAFF_EMPTY_RESPONSE.data);
  });

  it('maps an already-aborted signal without issuing fetch', async () => {
    const controller = new AbortController();
    controller.abort();
    globalThis.fetch = vi.fn();

    await expect(
      createStaffDirectoryClient().queryPage({}, { signal: controller.signal })
    ).rejects.toBeInstanceOf(StaffDirectoryAbortedError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
