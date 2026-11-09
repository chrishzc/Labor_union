/** Committed case changes invalidate accounting views in this window and other tabs. */
const eventName = 'case-accounting-committed';
let channel: BroadcastChannel | undefined;
function changesChannel() {
  if (typeof BroadcastChannel === 'undefined') return undefined;
  return channel ??= new BroadcastChannel(eventName);
}
export function notifyCaseAccountingChanged(caseNo: string) {
  window.dispatchEvent(new CustomEvent(eventName, { detail: caseNo }));
  changesChannel()?.postMessage(caseNo);
}
export function subscribeCaseAccountingChanges(listener: (caseNo: string) => void) {
  const local = (event: Event) => listener((event as CustomEvent<string>).detail);
  const remote = (event: MessageEvent<unknown>) => {
    if (typeof event.data === 'string' && event.data.length > 0 && event.data.length <= 50) listener(event.data);
  };
  window.addEventListener(eventName, local);
  const broadcast = changesChannel();
  broadcast?.addEventListener('message', remote);
  return () => {
    window.removeEventListener(eventName, local);
    broadcast?.removeEventListener('message', remote);
  };
}
