import { createContext, useContext, useEffect, useLayoutEffect, useState, type ReactNode } from 'react';
import type { OrderCoreStageWorkbenchViewModel } from '../adapters/orders/order_core_stage_projection_adapter';
import type { OrderSummaryCardViewModel } from '../adapters/orders/order_summary_adapter';
import type { StaffDirectoryCardViewModel } from '../adapters/staff/staff_directory_adapter';
import type { ImportFieldIssueCase } from '../api/case_import/import_field_issues';
import type { CoreStageCode } from '../api/orders/order_core_stage_projection_schemas';
import type { CaseStatisticsData } from '../api/reports/weekly_operations_report_schemas';
import { subscribeStaffAvailabilityChanges } from '../api/staff_availability/staff_availability_changes';
import type { HolidayRow } from '../adapters/scheduling/holiday_flow_adapter';
import type { CalendarMonthCacheEntry, CalendarCaseOptions, SchedulingViewSelection } from './SchedulingPage';

export const ADMIN_VIEW_FRESH_MS = 30_000;

interface Snapshot<T> {
  data: T;
  updatedAt: number;
  invalidated: boolean;
}

export function keepRecent<K, T>(entries: Map<K, T>, key: K, value: T, capacity: number): Map<K, T> {
  entries.delete(key);
  entries.set(key, value);
  if (entries.size > capacity) {
    const oldest = entries.keys().next();
    if (!oldest.done) entries.delete(oldest.value);
  }
  return entries;
}

class ViewCache<T> {
  private readonly entries = new Map<string, Snapshot<T>>();
  private readonly capacity: number;
  revision = 0;

  constructor(capacity: number) {
    this.capacity = capacity;
  }

  read(key: string): Snapshot<T> | undefined {
    return this.entries.get(key);
  }

  forget(key: string): void {
    this.entries.delete(key);
  }

  write(key: string, data: T, revision: number): Snapshot<T> | undefined {
    if (revision !== this.revision) return undefined;
    const snapshot = { data, updatedAt: Date.now(), invalidated: false };
    keepRecent(this.entries, key, snapshot, this.capacity);
    return snapshot;
  }

  invalidate(matches: (key: string) => boolean = () => true): void {
    this.revision += 1;
    for (const [key, entry] of this.entries) {
      if (matches(key)) this.entries.set(key, { ...entry, invalidated: true });
    }
  }
}

export function isFresh(snapshot: { updatedAt: number; invalidated: boolean } | undefined): boolean {
  return snapshot !== undefined && !snapshot.invalidated && Date.now() - snapshot.updatedAt < ADMIN_VIEW_FRESH_MS;
}

export function isViewAccessDenied(error: unknown): boolean {
  return error instanceof Error && 'status' in error && (error.status === 401 || error.status === 403);
}

export function viewTimestamp(updatedAt: number): string {
  return new Intl.DateTimeFormat('zh-TW', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(updatedAt);
}

export type StatisticsPeriod = Pick<CaseStatisticsData, 'year'> & { quarter: number; month: number };

class AdminOperationsViews {
  readonly workbench = {
    selection: { stage: null as CoreStageCode | null, search: '' },
    core: new ViewCache<OrderCoreStageWorkbenchViewModel>(14),
    summaries: new ViewCache<ReadonlyMap<string, OrderSummaryCardViewModel>>(1),
    intake: new ViewCache<ReadonlyMap<string, ImportFieldIssueCase>>(14),
    statistics: new ViewCache<CaseStatisticsData>(8),
    statisticsPeriods: new Map<'subsidy' | 'non_citizen', StatisticsPeriod>(),
  };
  readonly scheduling = {
    selection: null as SchedulingViewSelection | null,
    directory: new ViewCache<{ staff: StaffDirectoryCardViewModel[]; nextCursor: number | null }>(1),
    options: new ViewCache<CalendarCaseOptions>(1),
    holidays: new ViewCache<readonly HolidayRow[]>(12),
    months: new Map<string, CalendarMonthCacheEntry>(),
  };
  readonly scroll = new Map<'order-workbench-v2' | 'scheduling', number>();

  invalidateWorkbench(): void {
    this.workbench.core.invalidate();
    this.workbench.summaries.invalidate();
    this.workbench.intake.invalidate();
    this.workbench.statistics.invalidate();
  }

  invalidateSchedulingMonths(staffId?: number): void {
    if (staffId === undefined) this.scheduling.options.invalidate();
    for (const [key, entry] of this.scheduling.months) {
      if (staffId === undefined || staffId === entry.target.staff.id) {
        this.scheduling.months.set(key, { ...entry, invalidated: true });
      }
    }
  }
}

const AdminOperationsViewContext = createContext<AdminOperationsViews | null>(null);

export function AdminOperationsViewProvider({ children }: { children: ReactNode }) {
  const [views] = useState(() => new AdminOperationsViews());
  useEffect(() => subscribeStaffAvailabilityChanges(staffId => views.invalidateSchedulingMonths(staffId)), [views]);
  return <AdminOperationsViewContext.Provider value={views}>{children}</AdminOperationsViewContext.Provider>;
}

export function useAdminOperationsViews(): AdminOperationsViews {
  const shared = useContext(AdminOperationsViewContext);
  const [standalone] = useState(() => shared ?? new AdminOperationsViews());
  return shared ?? standalone;
}

export function useOperationsScroll(views: AdminOperationsViews, page: 'order-workbench-v2' | 'scheduling', enabled: boolean) {
  useLayoutEffect(() => {
    if (!enabled) return;
    const saved = views.scroll.get(page);
    if (saved !== undefined && window.scrollY !== saved) window.scrollTo({ top: saved, behavior: 'instant' });
    const save = () => { views.scroll.set(page, window.scrollY); };
    window.addEventListener('scroll', save, { passive: true });
    return () => { window.removeEventListener('scroll', save); };
  }, [views, page, enabled]);
}

type QueryStatus = { kind: 'loading' } | { kind: 'ready' } | { kind: 'failed'; error: unknown };

export function useOperationsQuery<T>({ cache, queryKey, read, refreshKey = 0, enabled = true }: {
  cache: ViewCache<T>;
  queryKey: string;
  read: (signal: AbortSignal) => Promise<T>;
  refreshKey?: number;
  enabled?: boolean;
}) {
  const [status, setStatus] = useState<{ key: string; status: QueryStatus } | null>(null);
  const snapshot = cache.read(queryKey);

  useLayoutEffect(() => {
    if (!enabled) return;
    if (isFresh(cache.read(queryKey))) {
      setStatus({ key: queryKey, status: { kind: 'ready' } });
      return;
    }
    const controller = new AbortController();
    const revision = cache.revision;
    setStatus({ key: queryKey, status: { kind: 'loading' } });
    queueMicrotask(() => {
      if (controller.signal.aborted) return;
      void read(controller.signal).then(data => {
        if (!controller.signal.aborted && cache.write(queryKey, data, revision)) {
          setStatus({ key: queryKey, status: { kind: 'ready' } });
        }
      }).catch((error: unknown) => {
        if (!controller.signal.aborted && revision === cache.revision) {
          if (isViewAccessDenied(error)) cache.forget(queryKey);
          setStatus({ key: queryKey, status: { kind: 'failed', error } });
        }
      });
    });
    return () => controller.abort();
  }, [cache, queryKey, read, refreshKey, enabled]);

  const pending = status?.key === queryKey ? status.status : undefined;
  const currentStatus: QueryStatus = pending ?? (isFresh(snapshot) ? { kind: 'ready' } : { kind: 'loading' });
  return { snapshot, status: currentStatus };
}
