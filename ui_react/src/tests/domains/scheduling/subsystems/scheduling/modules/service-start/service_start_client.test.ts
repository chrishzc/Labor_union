import { afterEach, beforeEach, describe, expect, expectTypeOf, it, vi } from 'vitest';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { serviceStartClient, type ServiceStartView, type HandoverContext } from '../../../../../../../api/scheduling/service_start_client';
import { transport } from '../../../../../../../api/shared/transport';
import { ApiDecodeError, ApiHttpError } from '../../../../../../../api/shared/typed_errors';

// ServiceStartView defaults mirror api/schemas/service_start.py, not UI guesses.
const requiredView = {
  request_id: 8, case_no: 'CASE-8', staff_id: 7, staff_name: '測試月嫂',
  segment_id: null, order_version: 3, version: 4, status: 'substitute_required',
  requested_start_date: null, selected_staff_id: null, selected_staff_name: null,
  willingness: null, invitation_status: null, joined: false, result: null,
  proposed_start_date: null, proposed_end_date: null,
};
const defaults = { workflow_kind: 'service_start', leave_dates: [], conflict_message: null, handover_dates: [] };
const envelope = (data: unknown) => ({ success: true, message: 'Success', data });

describe('Service start typed transport', () => {
  beforeEach(() => {
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('service-start-test');
    vi.spyOn(transport, 'get');
    vi.spyOn(transport, 'post');
  });
  afterEach(() => vi.restoreAllMocks());

  it('returns the parsed defaults as required output fields', async () => {
    vi.mocked(transport.get).mockResolvedValue(envelope(requiredView));
    const result = await serviceStartClient.detail(8);
    expectTypeOf(result).toEqualTypeOf<ServiceStartView>();
    expectTypeOf(result.workflow_kind).toEqualTypeOf<'service_start' | 'leave' | 'handover'>();
    expect(result).toEqual({ ...requiredView, ...defaults });
    expect(transport.get).toHaveBeenCalledWith('/api/v1/scheduling/service-start/8', { token: 'service-start-test' });
    expect(transport.post).not.toHaveBeenCalled();
  });

  it('decodes nested todo items and handover requests with the same defaults', async () => {
    const context = { case_no: 'CASE-8', assignment_id: 2, staff_id: 7, staff_name: '測試月嫂',
      order_version: 3, scheduling_version: 5, service_dates: ['2026-11-02'], request: requiredView };
    vi.mocked(transport.get)
      .mockResolvedValueOnce(envelope({ items: [requiredView], total: 26, page: 2, page_size: 25 }))
      .mockResolvedValueOnce(envelope(context));
    const page = await serviceStartClient.todos(2, 'CASE-8');
    const handover = await serviceStartClient.handoverContext('CASE-8', 2);
    expectTypeOf(page.items).toEqualTypeOf<ServiceStartView[]>();
    expectTypeOf(handover).toEqualTypeOf<HandoverContext>();
    expect(page).toEqual({ items: [{ ...requiredView, ...defaults }], total: 26, page: 2, page_size: 25 });
    expect(handover.request).toEqual({ ...requiredView, ...defaults });
    expect(transport.post).not.toHaveBeenCalled();
  });

  it.each(['leave', 'handover'] as const)('preserves explicit %s workflow facts', async (workflow_kind) => {
    const facts = { workflow_kind, leave_dates: [{ original_date: '2026-11-02', new_date: null }],
      handover_dates: ['2026-11-04'], conflict_message: '原排班尚未變更' };
    vi.mocked(transport.get).mockResolvedValue(envelope({ ...requiredView, ...facts }));
    expect(await serviceStartClient.detail(8)).toEqual({ ...requiredView, ...facts });
  });

  it.each([
    ['missing data', { success: true, message: 'Success' }],
    ['null data', envelope(null)],
    ['missing required version', envelope({ ...requiredView, version: undefined })],
    ['unknown workflow', envelope({ ...requiredView, workflow_kind: 'retired' })],
    ['null workflow', envelope({ ...requiredView, workflow_kind: null })],
    ['invalid leave dates', envelope({ ...requiredView, leave_dates: [{ original_date: '2026-11-02' }] })],
    ['invalid handover dates', envelope({ ...requiredView, handover_dates: [42] })],
    ['backend rejection', { success: false, message: '此安排目前不可操作。', data: null }],
  ])('rejects %s without returning a usable view', async (_name, payload) => {
    vi.mocked(transport.get).mockResolvedValue(payload);
    await expect(serviceStartClient.detail(8)).rejects.toBeInstanceOf(ApiDecodeError);
    expect(transport.post).not.toHaveBeenCalled();
  });

  it('rejects an unauthenticated read before transport', async () => {
    vi.mocked(sessionClient.getToken).mockReturnValue(null);
    await expect(serviceStartClient.detail(8)).rejects.toBeInstanceOf(ApiHttpError);
    expect(transport.get).not.toHaveBeenCalled();
    expect(transport.post).not.toHaveBeenCalled();
  });
});
