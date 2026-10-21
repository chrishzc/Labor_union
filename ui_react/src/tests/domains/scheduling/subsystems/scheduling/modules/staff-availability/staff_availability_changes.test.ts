/** Only committed availability receipts trigger local and cross-tab refreshes. */
import { afterEach, expect, it, vi } from 'vitest';
import { staffAvailabilityClient } from '../../../../../../../api/staff_availability/staff_availability_client';
import { publishStaffAvailabilityChange, subscribeStaffAvailabilityChanges } from '../../../../../../../api/staff_availability/staff_availability_changes';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { transport } from '../../../../../../../api/shared/transport';
import { STAFF_AVAILABILITY_APPLY_PAYLOAD, STAFF_AVAILABILITY_RECEIPT_RESPONSE } from '../../../../../../fixtures/staff/staff_availability_contract_fixtures';

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it.each(['create_long_leave', 'create_pause', 'cancel', 'end_pause'] as const)('refreshes after a decoded %s receipt', async action => {
  vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-test-session');
  const receipt = { ...STAFF_AVAILABILITY_RECEIPT_RESPONSE.data!, action };
  vi.spyOn(transport, 'post').mockResolvedValue({ ...STAFF_AVAILABILITY_RECEIPT_RESPONSE, data: receipt });
  const listener = vi.fn();
  const unsubscribe = subscribeStaffAvailabilityChanges(listener);
  try {
    const payload = { ...STAFF_AVAILABILITY_APPLY_PAYLOAD, action,
      start_date: action.startsWith('create_') ? '2026-10-01' : null,
      end_date: action === 'create_long_leave' ? '2026-10-31' : null,
      block_id: action === 'cancel' || action === 'end_pause' ? 92 : null,
      resume_date: action === 'end_pause' ? '2026-10-22' : null,
    };
    await staffAvailabilityClient.applyChange(7, payload, { idempotencyKey: 'synthetic-command' });
    expect(listener).toHaveBeenCalledExactlyOnceWith(7);
  } finally { unsubscribe(); }
});

it('does not publish a failed or undecodable Apply as a successful change', async () => {
  vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-test-session');
  const post = vi.spyOn(transport, 'post').mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ success: true, data: null });
  const listener = vi.fn();
  const unsubscribe = subscribeStaffAvailabilityChanges(listener);
  try {
    for (let i = 0; i < 2; i++) await expect(staffAvailabilityClient.applyChange(7, STAFF_AVAILABILITY_APPLY_PAYLOAD, { idempotencyKey: 'synthetic-command' })).rejects.toThrow();
    expect(post).toHaveBeenCalledTimes(2);
    expect(listener).not.toHaveBeenCalled();
  } finally { unsubscribe(); }
});

it('receives other-tab changes once, sends only staff identity, and releases the channel', () => {
  const close = vi.fn();
  const postMessage = vi.fn();
  let receive: ((event: MessageEvent) => void) | undefined;
  vi.stubGlobal('BroadcastChannel', class {
    postMessage = postMessage;
    close = close;
    set onmessage(listener: (event: MessageEvent) => void) { receive = listener; }
  });
  const listener = vi.fn();
  const unsubscribe = subscribeStaffAvailabilityChanges(listener);
  publishStaffAvailabilityChange(11);
  expect(listener).toHaveBeenCalledExactlyOnceWith(11);
  expect(postMessage).toHaveBeenCalledExactlyOnceWith(11);
  receive?.(new MessageEvent('message', { data: 12 }));
  receive?.(new MessageEvent('message', { data: { invalid: true } }));
  expect(listener.mock.calls).toEqual([[11], [12]]);
  unsubscribe();
  expect(close).toHaveBeenCalledOnce();
});
