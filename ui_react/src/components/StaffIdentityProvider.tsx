import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { createStaffDirectoryClient, loadAllStaffDirectoryPages } from '../api/staff_directory/staff_directory_client';
import { compareStaffUnionNumbers, staffDisplayLabel } from '../adapters/staff/staff_directory_adapter';

type Identity = { id: number; name: string | null; unionNo: string | null };
type Snapshot = { status: 'loading' | 'ready' | 'error'; people: ReadonlyMap<number, Identity> };
const StaffIdentityContext = createContext<Snapshot | null>(null);

/** One authenticated, read-only directory per mounted administrative page. */
export function StaffIdentityProvider({ children, enabled = true }: { children: ReactNode; enabled?: boolean }) {
  const [snapshot, setSnapshot] = useState<Snapshot>({ status: 'loading', people: new Map() });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    const client = createStaffDirectoryClient();
    setSnapshot({ status: 'loading', people: new Map() });
    void Promise.resolve().then(() => loadAllStaffDirectoryPages(client.queryPage.bind(client), { pageSize: 200 }, { signal: controller.signal }))
      .then(page => {
        if (controller.signal.aborted) return;
        setSnapshot({ status: 'ready', people: new Map(page.items.map(person => [person.id, {
          id: person.id, name: person.name, unionNo: person.union_no ?? null,
        }])) });
      })
      .catch(() => { if (!controller.signal.aborted) setSnapshot({ status: 'error', people: new Map() }); });
    return () => controller.abort();
  }, [enabled, revision]);
  return <StaffIdentityContext.Provider value={enabled ? snapshot : null}>
    {enabled && snapshot.status === 'error' && <p role="status">公會編號暫時無法讀取。<button type="button" onClick={() => setRevision(value => value + 1)}>重新讀取公會編號</button></p>}
    {children}
  </StaffIdentityContext.Provider>;
}

export function useStaffIdentityLabels() {
  const snapshot = useContext(StaffIdentityContext);
  return useMemo(() => ({
    label(staffId: number | null | undefined, name?: string | null, unionNo?: string | null): string {
      if (staffId == null) return name || '月嫂尚未確認';
      const person = snapshot?.people.get(staffId);
      const displayName = person?.name || name || '姓名未設定';
      if (person || unionNo !== undefined || snapshot === null) return staffDisplayLabel(person ? person.unionNo : unionNo, displayName);
      const state = snapshot.status === 'loading' ? '編號讀取中' : snapshot.status === 'error' ? '編號暫無法讀取' : '編號未查得';
      return `${state} ${displayName}`;
    },
    compare(leftId: number, rightId: number): number {
      return compareStaffUnionNumbers(snapshot?.people.get(leftId) ?? { id: leftId }, snapshot?.people.get(rightId) ?? { id: rightId });
    },
  }), [snapshot]);
}
