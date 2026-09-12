import React, { useEffect, useState } from 'react';
import { clientRegistryClient, type ClientRegistryListQuery } from '../api/client_registry/client_registry_client';
import type { ClientRegistryPage as ClientRegistryPageData, ClientRegistrySortBy, ClientRegistrySortOrder } from '../api/client_registry/client_registry_schemas';
import './ClientRosterPage.css';

type SelectBoolean = '' | 'true' | 'false';
type RosterFilters = {
  query: string;
  hasBabyInfo: SelectBoolean;
  serviceDays: string;
  requiresCooking: SelectBoolean;
  sortBy: ClientRegistrySortBy;
  sortOrder: ClientRegistrySortOrder;
};

const defaultFilters: RosterFilters = {
  query: '', hasBabyInfo: '', serviceDays: '', requiresCooking: '', sortBy: 'case_no', sortOrder: 'asc',
};

function toRequest(filters: RosterFilters): ClientRegistryListQuery | null {
  const serviceDaysText = filters.serviceDays.trim();
  const serviceDays = serviceDaysText ? Number(serviceDaysText) : undefined;
  if (serviceDays !== undefined && (!Number.isInteger(serviceDays) || serviceDays <= 0)) return null;
  return {
    query: filters.query,
    hasBabyInfo: filters.hasBabyInfo === '' ? undefined : filters.hasBabyInfo === 'true',
    serviceDays,
    requiresCooking: filters.requiresCooking === '' ? undefined : filters.requiresCooking === 'true',
    sortBy: filters.sortBy,
    sortOrder: filters.sortOrder,
    limit: 100,
  };
}

function hasActiveFilter(filters: RosterFilters): boolean {
  return Boolean(filters.query.trim() || filters.hasBabyInfo || filters.serviceDays.trim() || filters.requiresCooking || filters.sortBy !== 'case_no' || filters.sortOrder !== 'asc');
}

const displayCooking = (value: boolean | null) => value === true ? '需要' : value === false ? '不需要' : '未登錄';

export interface ClientRosterPageProps {
  embedded?: boolean;
}

export const ClientRosterPage: React.FC<ClientRosterPageProps> = ({ embedded = false }) => {
  const [filters, setFilters] = useState<RosterFilters>(defaultFilters);
  const [appliedFilters, setAppliedFilters] = useState<RosterFilters>(defaultFilters);
  const [page, setPage] = useState<ClientRegistryPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async (nextFilters: RosterFilters) => {
    const request = toRequest(nextFilters);
    if (!request) {
      setError('服務天數請輸入正整數。');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await clientRegistryClient.list(request);
      setPage(result);
      setAppliedFilters(nextFilters);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '客戶名冊清單載入失敗。');
    } finally {
      setLoading(false);
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
  const changeSort = (sortBy: ClientRegistrySortBy) => {
    const sortOrder: ClientRegistrySortOrder = filters.sortBy === sortBy && filters.sortOrder === 'asc' ? 'desc' : 'asc';
    const nextFilters = { ...filters, sortBy, sortOrder };
    setFilters(nextFilters);
    void load(nextFilters);
  };
  const sortLabel = (sortBy: ClientRegistrySortBy) => filters.sortBy === sortBy ? (filters.sortOrder === 'asc' ? ' ↑' : ' ↓') : '';

  return <div className={`client-roster-page${embedded ? ' client-roster-page--embedded' : ''}`}>
    {!embedded && <header><div><h1>客戶名冊清單</h1><p>以案件為單位快速瀏覽與比較；此頁只會查詢，不會修改客戶或訂單資料。</p></div></header>}
    <form className="client-roster-filters" onSubmit={applyFilters}>
      <label>搜尋<input aria-label="搜尋客戶名冊清單" value={filters.query} placeholder="案件編號、姓名或電話" onChange={(event) => setFilters((value) => ({ ...value, query: event.target.value }))} /></label>
      <label>寶寶資訊<select aria-label="寶寶資訊篩選" value={filters.hasBabyInfo} onChange={(event) => setFilters((value) => ({ ...value, hasBabyInfo: event.target.value as SelectBoolean }))}><option value="">全部</option><option value="true">有寶寶資訊</option><option value="false">無寶寶資訊</option></select></label>
      <label>服務天數<input aria-label="服務天數篩選" type="number" min="1" step="1" inputMode="numeric" value={filters.serviceDays} onChange={(event) => setFilters((value) => ({ ...value, serviceDays: event.target.value }))} /></label>
      <label>下廚需求<select aria-label="下廚需求篩選" value={filters.requiresCooking} onChange={(event) => setFilters((value) => ({ ...value, requiresCooking: event.target.value as SelectBoolean }))}><option value="">全部</option><option value="true">需要</option><option value="false">不需要</option></select></label>
      <div className="client-roster-filter-actions"><button type="submit">套用篩選</button><button type="button" onClick={clearFilters}>清除篩選</button></div>
    </form>
    {error && <p role="alert" className="client-roster-message">{error}</p>}
    {loading && <p role="status" className="client-roster-message">正在載入客戶名冊清單…</p>}
    {!loading && !error && page?.items.length === 0 && <p role="status" className="client-roster-message">{hasActiveFilter(appliedFilters) ? '沒有符合篩選條件的案件。' : '目前沒有可顯示的案件。'}</p>}
    {!loading && !error && page && page.items.length > 0 && <div className="client-roster-table-wrap"><table>
      <caption>客戶名冊清單（最多顯示 100 筆符合條件的案件）</caption>
      <thead><tr>
        <th scope="col"><button type="button" onClick={() => changeSort('case_no')}>案件編號{sortLabel('case_no')}</button></th>
        <th scope="col"><button type="button" onClick={() => changeSort('customer_name')}>客戶姓名{sortLabel('customer_name')}</button></th>
        <th scope="col">電話</th><th scope="col">地區</th><th scope="col">寶寶資訊</th>
        <th scope="col"><button type="button" onClick={() => changeSort('service_days')}>服務天數{sortLabel('service_days')}</button></th>
        <th scope="col">下廚需求</th>
        <th scope="col"><button type="button" onClick={() => changeSort('expected_start_date')}>預計服務日期{sortLabel('expected_start_date')}</button></th>
        <th scope="col">案件／訂單狀態</th>
      </tr></thead>
      <tbody>{page.items.map((item) => <tr key={item.case_no}>
        <td>{item.case_no}</td><td>{item.name ?? '—'}</td><td>{item.phone ?? '—'}</td><td>{item.city ?? '—'}</td>
        <td>{item.baby_info ?? '—'}</td><td>{item.service_days ?? '—'}</td><td>{displayCooking(item.requires_cooking)}</td>
        <td>{item.planned_start_date ?? '—'}</td><td>{item.order_status ?? '—'}</td>
      </tr>)}</tbody>
    </table></div>}
  </div>;
};

export default ClientRosterPage;
