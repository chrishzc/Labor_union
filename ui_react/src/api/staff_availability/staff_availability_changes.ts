/** Refresh availability projections after a committed change, including other tabs. */
const listeners = new Set<(staffId: number) => void>();
let channel: BroadcastChannel | null = null;

function emit(staffId: number) {
  for (const listener of listeners) listener(staffId);
}

function openChannel() {
  if (!channel && typeof window.BroadcastChannel === 'function') {
    channel = new window.BroadcastChannel('labor-union:staff-availability');
    channel.onmessage = ({ data }: MessageEvent<unknown>) => {
      if (typeof data === 'number' && Number.isSafeInteger(data) && data > 0) emit(data);
    };
  }
  return channel;
}

export function publishStaffAvailabilityChange(staffId: number) {
  openChannel()?.postMessage(staffId);
  emit(staffId);
  if (listeners.size === 0) {
    channel?.close();
    channel = null;
  }
}

export function subscribeStaffAvailabilityChanges(listener: (staffId: number) => void) {
  listeners.add(listener);
  openChannel();
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      channel?.close();
      channel = null;
    }
  };
}
