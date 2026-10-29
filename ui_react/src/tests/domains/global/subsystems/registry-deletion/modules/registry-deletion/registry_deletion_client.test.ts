/** The destructive client must bind its receipt, versions and operation key to the selected target. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { registryDeletionClient } from '../../../../../../../api/registry_deletion_client';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { transport } from '../../../../../../../api/shared/transport';
import { ApiDecodeError } from '../../../../../../../api/shared/typed_errors';

describe('registry deletion typed transport', () => {
  beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-session'); });

  it('sends the inspected case and both versions with the same operation identity', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValue({ success: true, data: { kind: 'case', identity: 'RD-7', deleted: true, replayed: false } });
    await registryDeletionClient.apply({ kind: 'case', identity: 'RD-7', version: 3, client_version: 8, blockers: [] }, 'operation-7');
    expect(post).toHaveBeenCalledWith('/api/v1/admin/registries/clients/RD-7/deletion/apply',
      { expected_version: 3, expected_client_version: 8 }, {
        token: 'synthetic-session', headers: { 'Idempotency-Key': 'operation-7', 'X-Correlation-ID': 'operation-7' },
      });
  });

  it('rejects an unrelated target returned by eligibility lookup', async () => {
    vi.spyOn(transport, 'get').mockResolvedValue({ success: true, data: { kind: 'case', identity: '8', version: 0, client_version: 4, blockers: [] } });
    await expect(registryDeletionClient.preview('case', '7')).rejects.toBeInstanceOf(ApiDecodeError);
  });

  it.each([
    { kind: 'case', identity: '8', deleted: true, replayed: false },
    { kind: 'case', identity: '7', deleted: false, replayed: false },
  ])('does not report success for mismatched or false deletion receipts', async data => {
    vi.spyOn(transport, 'post').mockResolvedValue({ success: true, data });
    await expect(registryDeletionClient.apply({ kind: 'case', identity: '7', version: 0, client_version: 4, blockers: [] }, 'operation-7')).rejects.toBeInstanceOf(ApiDecodeError);
  });
});
