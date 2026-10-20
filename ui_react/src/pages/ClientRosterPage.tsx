import { useUnsavedNavigation } from '../components/UnsavedChanges';
import { useStaffIdentityLabels } from '../components/StaffIdentityProvider';
import React, { useEffect, useRef, useState } from 'react';
import { clientRegistryClient, type ClientRegistryListQuery } from '../api/client_registry/client_registry_client';
import type { ClientRegistryColumnFilter, ClientRegistryDetail, ClientRegistryFilterField, ClientRegistryPage as ClientRegistryPageData, ClientRegistrySortBy, ClientRegistrySortOrder } from '../api/client_registry/client_registry_schemas';
import { ClientRosterColumnFilter } from '../components/ClientRosterColumnFilter';
import { rosterFilterColumns, rosterFilterSummary } from '../components/client_roster_filter_columns';
import { ClientRegistryDetailEditor, type RegistryEditState } from '../components/ClientRegistryDetailEditor';
import { Drawer } from '../components/Drawer';
import './ClientRosterPage.css';

type RosterFilters = {
  query: string;
  columnFilters: ClientRegistryColumnFilter[];
  sortBy: ClientRegistrySortBy;
  sortOrder: ClientRegistrySortOrder;
};

const defaultFilters: RosterFilters = {
  query: '', columnFilters: [], sortBy: 'case_no', sortOrder: 'asc',
};
const pageSize = 100;

function toRequest(filters: RosterFilters, offset?: number): ClientRegistryListQuery {
  return {
    query: filters.query,
    ...(filters.columnFilters.length ? { columnFilters: filters.columnFilters } : {}),
    sortBy: filters.sortBy,
    sortOrder: filters.sortOrder,
    limit: pageSize,
    ...(offset === undefined ? {} : { offset }),
  };
}

function hasActiveFilter(filters: RosterFilters): boolean {
  return Boolean(filters.query.trim() || filters.columnFilters.length || filters.sortBy !== 'case_no' || filters.sortOrder !== 'asc');
}

const displayCooking = (value: boolean | null) => value === true ? '需要' : value === false ? '不需要' : '未登錄';
const displayImportedVirtualAccounts = (values: string[]) => values.length
  ? values.map((value) => <div key={value}>{value}</div>)
  : '—';

type RosterItem = ClientRegistryPageData['items'][number];
const staffObligationLabels: Record<string, string> = {
  service_pay: '薪資', adjustment: '調整', reversal: '沖正',
};

function clientDueDates(item: RosterItem, stage: NonNullable<RosterItem['client_obligation_dates']>[number]['obligation_type']) {
  if (item.client_obligation_dates === undefined) return '未載入';
  const dates = item.client_obligation_dates.filter((entry) => entry.obligation_type === stage);
  return dates.length ? dates.map((entry) => (
    <div key={entry.obligation_identity} title={entry.obligation_identity}>{entry.due_date ?? '無值'}</div>
  )) : '無值';
}

export interface ClientRosterPageProps {
  embedded?: boolean;
  initialCaseNo?: string;
  focusField?: string;
  onEditStateChange?: (state: RegistryEditState) => void;
  onReturnToCase?: (caseNo: string) => void;
  onOpenServiceArrangement?: (caseNo: string, recalculateDates: boolean) => void;
}

export const ClientRosterPage: React.FC<ClientRosterPageProps> = ({ embedded = false, initialCaseNo = '', focusField = '', onEditStateChange, onReturnToCase, onOpenServiceArrangement }) => {
  const staffIdentity = useStaffIdentityLabels();
  const [filters, setFilters] = useState<RosterFilters>(defaultFilters);
  const [appliedFilters, setAppliedFilters] = useState<RosterFilters>(defaultFilters);
  const [page, setPage] = useState<ClientRegistryPageData | null>(null);
  const [pageOffset, setPageOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCaseNo, setSelectedCaseNo] = useState<string | null>(null);
  const [detail, setDetail] = useState<ClientRegistryDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [editState, setEditState] = useState<RegistryEditState>({ dirty: false, busy: false });
  useEffect(() => { onEditStateChange?.(editState); }, [editState, onEditStateChange]);
  const detailRequest = useRef(0);
  const listRequest = useRef(0);

  const load = async (nextFilters: RosterFilters, nextOffset = 0) => {
    const requestId = ++listRequest.current;
    const request = toRequest(nextFilters, nextOffset || undefined);
    setLoading(true);
    setError(null);
    try {
      const result = await clientRegistryClient.list(request);
      if (requestId !== listRequest.current) return;
      setPage(result);
      setAppliedFilters(nextFilters);
      setPageOffset(nextOffset);
    } catch (caught) {
      if (requestId !== listRequest.current) return;
      setError(caught instanceof Error ? caught.message : '客戶名冊清單載入失敗。');
    } finally {
      if (requestId === listRequest.current) setLoading(false);
    }
  };

  useEffect(() => { void load(defaultFilters); }, []);

  const applyFilters = (event: React.FormEvent) => {
    event.preventDefault();
    void load(filters);
  };
  const clearFilters = () => {
    setFilters(defaultFilters);
    void load(defaultFilters);
  };
  const changeSort = (sortBy: ClientRegistrySortBy, order?: ClientRegistrySortOrder) => {
    const sortOrder: ClientRegistrySortOrder = order ?? (appliedFilters.sortBy === sortBy && appliedFilters.sortOrder === 'asc' ? 'desc' : 'asc');
    const nextFilters = { ...appliedFilters, sortBy, sortOrder };
    setFilters({ ...nextFilters, query: filters.query });
    void load(nextFilters);
  };
  const applyColumn = (field: ClientRegistryFilterField, predicate?: ClientRegistryColumnFilter) => {
    const columnFilters = appliedFilters.columnFilters.filter((item) => item.field !== field);
    if (predicate) columnFilters.push(predicate);
    const nextFilters = { ...appliedFilters, columnFilters };
    setFilters({ ...nextFilters, query: filters.query });
    void load(nextFilters);
  };
  const columnHeading = (field: ClientRegistryFilterField, sortBy?: ClientRegistrySortBy) => {
    const column = rosterFilterColumns.find((item) => item.field === field)!;
    return <div className="client-roster-column-heading">
      {sortBy ? <button type="button" disabled={loading} onClick={() => changeSort(sortBy)}>{column.label}{sortLabel(sortBy)}</button> : <span>{column.label}</span>}
      <ClientRosterColumnFilter column={column} active={appliedFilters.columnFilters.find((item) => item.field === field)} disabled={loading}
        onApply={(predicate) => applyColumn(field, predicate)} onSort={sortBy ? (order) => changeSort(sortBy, order) : undefined} />
    </div>;
  };
  const previousPage = () => void load(appliedFilters, Math.max(0, pageOffset - pageSize));
  const nextPage = () => {
    if (page?.next_offset !== null && page?.next_offset !== undefined) {
      void load(appliedFilters, page.next_offset);
    }
  };
  const sortLabel = (sortBy: ClientRegistrySortBy) => appliedFilters.sortBy === sortBy ? (appliedFilters.sortOrder === 'asc' ? ' ↑' : ' ↓') : '';
  const readDetail = async (caseNo: string) => {
    const request = ++detailRequest.current;
    setSelectedCaseNo(caseNo); setDetail(null); setDetailError(null); setDetailLoading(true);
    try {
      const result = await clientRegistryClient.query(caseNo);
      if (detailRequest.current === request) setDetail(result);
    } catch (caught) {
      if (detailRequest.current === request) setDetailError(caught instanceof Error ? caught.message : '完整客戶資料載入失敗。');
    } finally {
      if (detailRequest.current === request) setDetailLoading(false);
    }
  };
  const openDetail = (caseNo: string) => requestLeave(() => { void readDetail(caseNo); });
  useEffect(() => {
    if (initialCaseNo) void openDetail(initialCaseNo);
  }, [initialCaseNo]);
  useEffect(() => () => { ++detailRequest.current; ++listRequest.current; }, []);
  const refreshDetail = async () => {
    if (!selectedCaseNo) throw new Error('未選取案件。');
    const request = ++detailRequest.current;
    const result = await clientRegistryClient.query(selectedCaseNo);
    if (request !== detailRequest.current) throw new Error('案件已切換，請重新開啟。');
    setDetail(result);
    const listId = ++listRequest.current;
    const refreshedPage = await clientRegistryClient.list(toRequest(appliedFilters, pageOffset || undefined));
    if (listId === listRequest.current) setPage(refreshedPage);
    return result;
  };
  const { requestLeave } = useUnsavedNavigation();
  const closeDetail = () => {
    if (editState.busy) return;
    requestLeave(() => {
    setEditState({ dirty: false, busy: false });
    detailRequest.current += 1;
    setSelectedCaseNo(null); setDetail(null); setDetailError(null); setDetailLoading(false);
    });
  };
  const exportWorkbook = async (kind: 'order-accounting' | 'case-inspection') => {
    const label = kind === 'case-inspection' ? '案件資料檢查' : '訂單帳務';
    setExporting(true); setExportMessage(null); setExportError(null);
    try {
      const request = toRequest(appliedFilters);
      const artifact = kind === 'case-inspection'
        ? await clientRegistryClient.downloadCaseInspection(request)
        : await clientRegistryClient.downloadOrderAccounting(request);
      const objectUrl = URL.createObjectURL(artifact.blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl; anchor.download = artifact.filename; anchor.click();
      URL.revokeObjectURL(objectUrl);
      setExportMessage(`${label} Excel 已下載。`);
    } catch (caught) {
      setExportError(caught instanceof Error ? caught.message : `${label}匯出失敗。`);
    } finally {
      setExporting(false);
    }
  };

  return <div className={`client-roster-page${embedded ? ' client-roster-page--embedded' : ''}`}>
    {!embedded && <header><div><h1>客戶名冊清單</h1><p>以案件為單位快速瀏覽與比較；點選案件即可查看與編輯詳細資料。</p></div></header>}
    {!error && page && <nav className="client-roster-pagination" aria-label="客戶名冊分頁">
      <button type="button" disabled={loading || pageOffset === 0} onClick={previousPage}>上一頁</button>
      <span aria-live="polite">第 {Math.floor(pageOffset / pageSize) + 1} 頁<span className="client-roster-page-count">（本頁 {page.items.length} 筆）</span></span>
      <button type="button" disabled={loading || page.next_offset == null} onClick={nextPage}>下一頁</button>
    </nav>}
    <form className="client-roster-filters" onSubmit={applyFilters}>
      <label>搜尋<input aria-label="搜尋客戶名冊清單" value={filters.query} placeholder="案件編號、姓名或電話" onChange={(event) => setFilters((value) => ({ ...value, query: event.target.value }))} /></label>
      <div className="client-roster-filter-actions"><button type="submit" disabled={loading}>搜尋</button><button type="button" disabled={loading} onClick={clearFilters}>清除全部篩選</button><button type="button" disabled={exporting || loading || !!error} onClick={() => void exportWorkbook('order-accounting')}>{exporting ? '匯出中…' : '匯出訂單帳務'}</button><button type="button" disabled={exporting || loading || !!error} onClick={() => void exportWorkbook('case-inspection')}>案件資料檢查匯出</button></div>
    </form>
    <div className="client-roster-active-filters" aria-label="已套用篩選">
      <span className="client-roster-filter-help">點欄名旁的 ▾ 篩選；不同欄位的條件會同時套用。</span>
      {appliedFilters.query.trim() && <span className="client-roster-filter-chip">搜尋：{appliedFilters.query}<button type="button" disabled={loading} aria-label="清除搜尋條件" onClick={() => { const next = { ...appliedFilters, query: '' }; setFilters(next); void load(next); }}>×</button></span>}
      {appliedFilters.columnFilters.map((predicate) => <span className="client-roster-filter-chip" key={predicate.field}>{rosterFilterSummary(predicate)}<button type="button" disabled={loading} aria-label={`清除${rosterFilterColumns.find((item) => item.field === predicate.field)!.label}篩選`} onClick={() => applyColumn(predicate.field)}>×</button></span>)}
      {filters.query !== appliedFilters.query && <span role="status">搜尋文字已變更，尚未套用。</span>}
    </div>
    {exportMessage && <p role="status" className="client-roster-message">{exportMessage}</p>}
    {exportError && <p role="alert" className="client-roster-message">{exportError}</p>}
    {error && <p role="alert" className="client-roster-message">{error}</p>}
    {loading && <p role="status" className="client-roster-message">正在載入客戶名冊清單…</p>}
    {!loading && !error && page?.items.length === 0 && <p role="status" className="client-roster-message">{hasActiveFilter(appliedFilters) ? '沒有符合篩選條件的案件。' : '目前沒有可顯示的案件。'}</p>}
    {!error && page && <div className="client-roster-table-wrap" aria-busy={loading}><table>
      <caption>客戶名冊清單（第 {Math.floor(pageOffset / pageSize) + 1} 頁）</caption>
      <thead><tr>
        <th scope="col" aria-sort={appliedFilters.sortBy === 'case_no' ? appliedFilters.sortOrder === 'asc' ? 'ascending' : 'descending' : undefined}>{columnHeading('case_no', 'case_no')}</th>
        <th scope="col">匯入虛擬帳號</th>
        <th scope="col">內建虛擬帳號</th>
        <th scope="col" aria-sort={appliedFilters.sortBy === 'customer_name' ? appliedFilters.sortOrder === 'asc' ? 'ascending' : 'descending' : undefined}>{columnHeading('name', 'customer_name')}</th>
        <th scope="col">{columnHeading('phone')}</th><th scope="col">{columnHeading('district')}</th><th scope="col">{columnHeading('multi_birth_count')}</th>
        <th scope="col" aria-sort={appliedFilters.sortBy === 'service_days' ? appliedFilters.sortOrder === 'asc' ? 'ascending' : 'descending' : undefined}>{columnHeading('service_days', 'service_days')}</th>
        <th scope="col">{columnHeading('service_type')}</th>
        <th scope="col">{columnHeading('requires_cooking')}</th>
        <th scope="col" aria-sort={appliedFilters.sortBy === 'expected_start_date' ? appliedFilters.sortOrder === 'asc' ? 'ascending' : 'descending' : undefined}>{columnHeading('planned_start_date', 'expected_start_date')}</th>
        <th scope="col">{columnHeading('order_status')}</th>
        <th scope="col" title="client_obligations.due_date（deposit）">{columnHeading('deposit_due_date')}</th>
        <th scope="col" title="client_obligations.due_date（first）">{columnHeading('first_due_date')}</th>
        <th scope="col" title="client_obligations.due_date（second）">{columnHeading('second_due_date')}</th>
        <th scope="col" title="orders.staff_payment_due_date">{columnHeading('staff_payment_due_date')}</th>
        <th scope="col" title="staff_obligations.due_date">月嫂義務應付日</th>
        <th scope="col" title="client_obligations.due_date（subsidy_return）">{columnHeading('subsidy_return_due_date')}</th>
        <th scope="col" title="既有 _claim_schedule(actual_end_date) 投影；非實際送件日">補助預計申請年月</th>
      </tr></thead>
      <tbody>{page.items.map((item) => <tr
        key={item.case_no}
        className={selectedCaseNo === item.case_no ? 'is-selected' : undefined}
        tabIndex={0}
        aria-haspopup="dialog"
        aria-expanded={selectedCaseNo === item.case_no}
        aria-label={`開啟案件 ${item.case_no} 詳細資料`}
        onClick={(event) => { event.currentTarget.focus(); void openDetail(item.case_no); }}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            void openDetail(item.case_no);
          }
        }}
      >
        <td>{item.case_no}</td><td>{displayImportedVirtualAccounts(item.imported_virtual_accounts)}</td><td>{item.built_in_virtual_account ?? '—'}</td><td>{item.name ?? '—'}</td><td>{item.phone ?? '—'}</td><td>{item.district ?? ''}</td>
        <td>{item.multi_birth_count ?? '—'}</td><td>{item.service_days ?? '—'}</td><td>{item.service_type ?? '尚未登錄'}</td><td>{displayCooking(item.requires_cooking)}</td>
        <td>{item.planned_start_date ?? '—'}</td><td>{item.order_status ?? '—'}</td>
        <td>{clientDueDates(item, 'deposit')}</td>
        <td>{clientDueDates(item, 'first')}</td>
        <td>{clientDueDates(item, 'second')}</td>
        <td>{item.staff_payment_due_date === undefined ? '未載入' : item.staff_payment_due_date ?? '無值'}</td>
        <td>{item.staff_obligation_dates === undefined ? '未載入' : item.staff_obligation_dates.length ? item.staff_obligation_dates.map((entry) => (
          <div key={entry.obligation_identity} title={entry.obligation_identity}>
            {staffIdentity.label(entry.staff_id, entry.staff_name)}／{staffObligationLabels[entry.obligation_kind] ?? entry.obligation_kind}：{entry.due_date ?? '無值'}
          </div>
        )) : '無值'}</td>
        <td>{clientDueDates(item, 'subsidy_return')}</td>
        <td>{item.claim_application_year === undefined || item.claim_application_month === undefined ? '未載入'
          : item.claim_application_year !== null && item.claim_application_month !== null
          ? `${item.claim_application_year}-${String(item.claim_application_month).padStart(2, '0')}`
          : '無值'}</td>
      </tr>)}</tbody>
    </table></div>}
    <Drawer
      isOpen={selectedCaseNo !== null}
      onClose={closeDetail}
      title={selectedCaseNo ? `案件 ${selectedCaseNo} 詳細資料` : '案件詳細資料'}
      size="wide"
      closeLabel="關閉案件詳細資料"
      className="client-roster-detail-drawer"
      closeDisabled={editState.busy}
    >
      {onReturnToCase && selectedCaseNo && <div className="registry-return-row"><button type="button" disabled={editState.busy} onClick={() => {
        if (editState.busy) return;
        onReturnToCase(selectedCaseNo);
      }}>返回案件處理 →</button></div>}
      {detailLoading && <p role="status" className="client-roster-message">正在載入完整客戶資料…</p>}
      {detailError && <p role="alert" className="client-roster-message">{detailError}</p>}
      {detail?.case_no === selectedCaseNo && <ClientRegistryDetailEditor key={detail.case_no} detail={detail} focusField={focusField} onRefresh={refreshDetail} onStateChange={setEditState} onOpenServiceArrangement={recalculateDates => {
        if (editState.busy) return;
        if (onOpenServiceArrangement) onOpenServiceArrangement(detail.case_no, recalculateDates);
        else window.location.hash = `#order-workbench-v2?case=${encodeURIComponent(detail.case_no)}&work=service&from=clients${recalculateDates ? '&recalculate=1' : ''}`;
      }} />}
    </Drawer>
  </div>;
};

export default ClientRosterPage;
