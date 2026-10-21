import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { staffAvailabilityClient } from '../../../../../../../api/staff_availability/staff_availability_client';
import { transport } from '../../../../../../../api/shared/transport';
import { sessionClient } from '../../../../../../../api/auth/session_client';

const block = (id: number, staff_id = 11) => ({ block_id: id, staff_id, kind: 'long_leave', start_date: id === 1 ? '2020-01-01' : '2030-01-01', end_date: '2030-01-31', status: 'effective', reason: '' });
const envelope = (data: unknown[]) => ({ success: true, message: 'ok', data, error: null });
afterEach(() => vi.restoreAllMocks());
beforeEach(() => { vi.spyOn(sessionClient, 'getToken').mockReturnValue('mock-records-session'); });

describe('all availability records', () => {
  it('reads every page without date filters and includes historical and future records', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValueOnce(envelope(Array.from({ length: 100 }, (_, i) => block(i + 1)))).mockResolvedValueOnce(envelope([block(101)]));
    const records = await staffAvailabilityClient.getAllBlocks(11);
    expect(records).toHaveLength(101);
    expect(records[0].start_date).toBe('2020-01-01');
    expect(records[100].start_date).toBe('2030-01-01');
    expect(get.mock.calls.map(call => call[1]?.params)).toEqual([{ after_id: 0, limit: 100 }, { after_id: 100, limit: 100 }]);
  });
  it.each(['wrong-person', 'non-advancing-cursor'])('rejects %s rather than returning a misleading partial list', async issue => {
    const get = vi.spyOn(transport, 'get').mockResolvedValue(envelope(issue === 'wrong-person' ? [block(1, 12)] : [block(2), block(1)]));
    await expect(staffAvailabilityClient.getAllBlocks(11)).rejects.toThrow(issue === 'wrong-person' ? 'identity' : '游標');
    expect(get).toHaveBeenCalledOnce();
  });
});
