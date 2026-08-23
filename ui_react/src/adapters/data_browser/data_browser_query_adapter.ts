/**
 * File: data_browser_query_adapter.ts
 * Description: 將 masked Data Browser DTO 映射為安全 table/Drawer model。
 */
import type {
  DataBrowserMaskedCell,
  DataBrowserMaskedPage,
  DataBrowserSourceId,
} from '../../api/data_browser/data_browser_query_schemas';

export type DataBrowserTabId =
  | 'orders_archive'
  | 'clients_archive'
  | 'staff_archive'
  | 'beclass_history'
  | 'hcm_history'
  | 'bank_facts_history';

export interface DataBrowserTab {
  tabId: DataBrowserTabId;
  sourceId: DataBrowserSourceId;
  label: string;
}

export const DATA_BROWSER_TABS: readonly DataBrowserTab[] = [
  { tabId: 'orders_archive', sourceId: 'orders', label: '📦 1. 訂單歷程主表' },
  { tabId: 'clients_archive', sourceId: 'clients', label: '👥 2. 客戶歷史檔案' },
  { tabId: 'staff_archive', sourceId: 'staff', label: '👩‍🍼 3. 月嫂名冊歷史' },
  { tabId: 'beclass_history', sourceId: 'beclass_intake', label: '📜 4. BeClass 原始進件' },
  { tabId: 'hcm_history', sourceId: 'hcm_review', label: '🏢 5. HCM 歷史案件' },
  { tabId: 'bank_facts_history', sourceId: 'bank_facts', label: '🏦 6. 銀行流水根事實' },
] as const;

export interface DataBrowserCellViewModel {
  id: string;
  label: string;
  value: string;
}

export interface DataBrowserRowViewModel {
  id: string;
  sourceId: DataBrowserSourceId;
  title: string;
  summary: DataBrowserCellViewModel[];
  detail: DataBrowserCellViewModel[];
  recordedAt: string;
  actorLabel: string;
  versionIdentity: string;
}

export interface DataBrowserPageViewModel {
  sourceId: DataBrowserSourceId;
  rows: DataBrowserRowViewModel[];
  nextCursor: string | null;
}

export function adaptDataBrowserPage(page: DataBrowserMaskedPage): DataBrowserPageViewModel {
  const rowIds = new Set<string>();
  const rows = page.items.map((row) => {
    if (row.source_id !== page.source_id || rowIds.has(row.row_identity)) {
      throw new Error('data_browser_row_identity_mismatch');
    }
    rowIds.add(row.row_identity);
    return {
      id: row.row_identity,
      sourceId: row.source_id,
      title: row.display_title,
      summary: adaptCells(row.summary_cells),
      detail: adaptCells(row.detail_cells),
      recordedAt: row.recorded_at ?? '—',
      actorLabel: row.source_actor_label ?? '—',
      versionIdentity: row.version_identity,
    };
  });
  if (page.next_cursor !== null && rowIds.has(page.next_cursor) === false && rows.length === 0) {
    throw new Error('data_browser_cursor_without_rows');
  }
  return { sourceId: page.source_id, rows, nextCursor: page.next_cursor };
}

function adaptCells(cells: DataBrowserMaskedCell[]): DataBrowserCellViewModel[] {
  const ids = new Set<string>();
  return cells.map((cell) => {
    if (ids.has(cell.field_id)) throw new Error('data_browser_duplicate_cell');
    ids.add(cell.field_id);
    return {
      id: cell.field_id,
      label: cell.label,
      value: cell.value === null ? '—' : String(cell.value),
    };
  });
}
