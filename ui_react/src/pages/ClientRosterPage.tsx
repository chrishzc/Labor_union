import React, { useEffect, useRef, useState } from 'react';
import { clientRegistryClient, type ClientRegistryListQuery } from '../api/client_registry/client_registry_client';
import type { ClientRegistryDetail, ClientRegistryPage as ClientRegistryPageData, ClientRegistrySortBy, ClientRegistrySortOrder } from '../api/client_registry/client_registry_schemas';
import { Drawer } from '../components/Drawer';
import './ClientRosterPage.css';

type SelectBoolean = '' | 'true' | 'false';
type MultiBirthCount = '' | '單胞胎' | '雙胞胎';
type RosterFilters = {
  query: string;
  multiBirthCount: MultiBirthCount;
  orderStatus: string;
  requiresCooking: SelectBoolean;
  sortBy: ClientRegistrySortBy;
  sortOrder: ClientRegistrySortOrder;
};

const defaultFilters: RosterFilters = {
  query: '', multiBirthCount: '', orderStatus: '', requiresCooking: '', sortBy: 'case_no', sortOrder: 'asc',
};
const pageSize = 100;

function toRequest(filters: RosterFilters, offset?: number): ClientRegistryListQuery {
  return {
    query: filters.query,
    multiBirthCount: filters.multiBirthCount || undefined,
    orderStatus: filters.orderStatus || undefined,
    requiresCooking: filters.requiresCooking === '' ? undefined : filters.requiresCooking === 'true',
    sortBy: filters.sortBy,
    sortOrder: filters.sortOrder,
    limit: pageSize,
    ...(offset === undefined ? {} : { offset }),
  };
}

function hasActiveFilter(filters: RosterFilters): boolean {
  return Boolean(filters.query.trim() || filters.multiBirthCount || filters.orderStatus || filters.requiresCooking || filters.sortBy !== 'case_no' || filters.sortOrder !== 'asc');
}

const orderStatuses = ['待補件', '洽談中', '訂單成立', '服務中', '訂單完成', '訂單取消', '歷史訂單－未服務', '歷史訂單－服務中', '歷史訂單－服務完成', '歷史訂單－帳務完成'];

const displayCooking = (value: boolean | null) => value === true ? '需要' : value === false ? '不需要' : '未登錄';
const displayValue = (value: unknown) => value === null || value === undefined || value === '' ? '未登錄' : typeof value === 'boolean' ? (value ? '是' : '否') : String(value);
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

const profileLabels = {
  name: '姓名', gender: '性別', phone: '手機', city: '縣市', address: '地址', residence_type: '住宅型態',
  delivery_type: '生產方式', baby_info: '寶寶資訊', notes: '行政註記',
} as const;
const beclassLabels = {
  name: '報名姓名', email: 'Email', phone: '手機', tel: '市話', ext: '分機', city: '縣市',
  zip_code: '郵遞區號', address: '報名地址', admin_notes: '報名註記', multi_birth_count: '胎數',
} as const;
const orderInformationLabels = {
  dietary_habits: '飲食習慣與中藥接受度', vegetarian_preference: '可否接受蛋奶素餐食', alcohol_ratio: '餐飲含酒比例',
  cooking_oil_type: '料理用油', maternal_allergy: '過敏體質', special_care_notes: '特殊照護注意事項',
  meal_preferences: '餐點喜忌', cooking_tools: '現有烹煮工具', bath_water_prep: '洗澡水準備',
  breastfeeding_method: '哺乳方式', holiday_pricing_terms: '三節計費約定', multi_birth_count: '胎數',
  stair_floor_fee_mode: '服務樓層方式', parking_space_provided: '停車位', other_babies_present: '服務時間內的其他寶寶',
} as const;
const orderTermLabels = {
  planned_start_date: '計畫服務開始日', service_days: '服務天數', service_hours_per_day: '每日服務時數',
  requires_cooking: '下廚需求', floor_fee_ntd: '樓層加給', start_time: '每日開始時間', end_time: '每日結束時間',
  end_day_offset: '結束日偏移',
} as const;
const financeLabels = {
  virtual_account: '本案專屬虛擬帳號', service_unit_price_ntd: '服務單價', service_hours: '服務總時數',
  customer_payable_total_ntd: '客戶應付總額', deposit_amount_ntd: '訂金金額', first_payment_amount_ntd: '第一期金額',
  second_payment_amount_ntd: '第二期金額', received_total_ntd: '已入帳金額', customer_balance_ntd: '客戶待繳／應退差額',
  subsidy_return_amount_ntd: '補助退款金額', subsidy_return_due_date: '補助退款日期', subsidy_return_status: '補助退款狀態',
} as const;

const ReadOnlyFields: React.FC<{ labels: Record<string, string>; values: Record<string, unknown>; issues?: Record<string, string> }> = ({ labels, values, issues = {} }) => (
  <dl className="client-roster-detail-fields">
    {Object.entries(labels).map(([field, label]) => <div key={field}><dt>{label}</dt><dd className={issues[field] ? 'source-issue' : undefined}>{issues[field] ? '來源內容無法判定' : displayValue(values[field])}</dd></div>)}
  </dl>
);

const ReadOnlyDetail: React.FC<{ detail: ClientRegistryDetail }> = ({ detail }) => {
  const terms = detail.order_terms.data?.terms;
  const orderTermValues = terms ? {
    planned_start_date: terms.planned_start_date, service_days: terms.service_days,
    service_hours_per_day: terms.service_hours_per_day, requires_cooking: terms.requires_cooking,
    floor_fee_ntd: terms.floor_fee_ntd, start_time: terms.service_time.start_time,
    end_time: terms.service_time.end_time, end_day_offset: terms.service_time.end_day_offset === 1 ? '隔日' : '同日',
  } : {};
  return <div className="client-roster-detail" aria-label={`${detail.case_no} 全部唯讀欄位`}>
    <section><h3>客戶主檔</h3><ReadOnlyFields labels={profileLabels} values={detail.client.values} /></section>
    <section><h3>BeClass 有效資料</h3>{detail.beclass.status === 'ready' && detail.beclass.values
      ? <ReadOnlyFields labels={beclassLabels} values={detail.beclass.values} />
      : <p>{detail.beclass.status === 'duplicate_binding' ? '同一案件綁定多筆 BeClass，無法判定資料。' : '尚未綁定 BeClass 紀錄。'}</p>}</section>
    <section><h3>BeClass 照護與特殊計費</h3>{detail.order_information.status === 'ready' && detail.order_information.values
      ? <ReadOnlyFields labels={orderInformationLabels} values={detail.order_information.values} issues={detail.order_information.field_issues} />
      : <p>{detail.order_information.status === 'duplicate_binding' ? '同一案件綁定多筆 BeClass，無法判定資料。' : '尚無 BeClass 照護資料。'}</p>}</section>
    <section><h3>訂單條件</h3>{terms
      ? <ReadOnlyFields labels={orderTermLabels} values={orderTermValues} />
      : <p>訂單條件目前不可用（{detail.order_terms.code ?? detail.order_terms.status}）。</p>}</section>
    <section><h3>客戶帳務（唯讀）</h3>{detail.finance.status === 'ready' && detail.finance.values
      ? <ReadOnlyFields labels={financeLabels} values={detail.finance.values} />
      : <p>客戶帳務目前不可用（{detail.finance.code ?? detail.finance.status}）。</p>}</section>
  </div>;
};

export interface ClientRosterPageProps {
  embedded?: boolean;
}

export const ClientRosterPage: React.FC<ClientRosterPageProps> = ({ embedded = false }) => {
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
  const detailRequest = useRef(0);

  const load = async (nextFilters: RosterFilters, nextOffset = 0) => {
    const request = toRequest(nextFilters, nextOffset || undefined);
    setLoading(true);
    setError(null);
    try {
      const result = await clientRegistryClient.list(request);
      setPage(result);
      setAppliedFilters(nextFilters);
      setPageOffset(nextOffset);
      setSelectedCaseNo(null);
      setDetail(null);
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
  const previousPage = () => void load(appliedFilters, Math.max(0, pageOffset - pageSize));
  const nextPage = () => {
    if (page?.next_offset !== null && page?.next_offset !== undefined) {
      void load(appliedFilters, page.next_offset);
    }
  };
  const sortLabel = (sortBy: ClientRegistrySortBy) => filters.sortBy === sortBy ? (filters.sortOrder === 'asc' ? ' ↑' : ' ↓') : '';
  const openDetail = async (caseNo: string) => {
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
  const closeDetail = () => {
    detailRequest.current += 1;
    setSelectedCaseNo(null); setDetail(null); setDetailError(null); setDetailLoading(false);
  };
  const exportOrderAccounting = async () => {
    setExporting(true); setExportMessage(null); setExportError(null);
    try {
      const artifact = await clientRegistryClient.downloadOrderAccounting(toRequest(appliedFilters));
      const objectUrl = URL.createObjectURL(artifact.blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl; anchor.download = artifact.filename; anchor.click();
      URL.revokeObjectURL(objectUrl);
      setExportMessage('訂單帳務 Excel 已下載。');
    } catch (caught) {
      setExportError(caught instanceof Error ? caught.message : '訂單帳務匯出失敗。');
    } finally {
      setExporting(false);
    }
  };

  return <div className={`client-roster-page${embedded ? ' client-roster-page--embedded' : ''}`}>
    {!embedded && <header><div><h1>客戶名冊清單</h1><p>以案件為單位快速瀏覽與比較；此頁只會查詢，不會修改客戶或訂單資料。</p></div></header>}
    <form className="client-roster-filters" onSubmit={applyFilters}>
      <label>搜尋<input aria-label="搜尋客戶名冊清單" value={filters.query} placeholder="案件編號、姓名或電話" onChange={(event) => setFilters((value) => ({ ...value, query: event.target.value }))} /></label>
      <label>BeClass 胎數<select aria-label="BeClass 胎數篩選" value={filters.multiBirthCount} onChange={(event) => setFilters((value) => ({ ...value, multiBirthCount: event.target.value as MultiBirthCount }))}><option value="">全部</option><option value="單胞胎">單胞胎</option><option value="雙胞胎">雙胞胎</option></select></label>
      <label>案件／訂單狀態<select aria-label="案件／訂單狀態篩選" value={filters.orderStatus} onChange={(event) => setFilters((value) => ({ ...value, orderStatus: event.target.value }))}><option value="">全部</option>{orderStatuses.map((status) => <option key={status} value={status}>{status}</option>)}</select></label>
      <label>下廚需求<select aria-label="下廚需求篩選" value={filters.requiresCooking} onChange={(event) => setFilters((value) => ({ ...value, requiresCooking: event.target.value as SelectBoolean }))}><option value="">全部</option><option value="true">需要</option><option value="false">不需要</option></select></label>
      <div className="client-roster-filter-actions"><button type="submit">套用篩選</button><button type="button" onClick={clearFilters}>清除篩選</button><button type="button" disabled={exporting} onClick={() => void exportOrderAccounting()}>{exporting ? '匯出中…' : '匯出訂單帳務'}</button></div>
    </form>
    {exportMessage && <p role="status" className="client-roster-message">{exportMessage}</p>}
    {exportError && <p role="alert" className="client-roster-message">{exportError}</p>}
    {error && <p role="alert" className="client-roster-message">{error}</p>}
    {loading && <p role="status" className="client-roster-message">正在載入客戶名冊清單…</p>}
    {!loading && !error && page?.items.length === 0 && <p role="status" className="client-roster-message">{hasActiveFilter(appliedFilters) ? '沒有符合篩選條件的案件。' : '目前沒有可顯示的案件。'}</p>}
    {!error && page && <nav className="client-roster-pagination" aria-label="客戶名冊分頁">
      <button type="button" disabled={loading || pageOffset === 0} onClick={previousPage}>上一頁</button>
      <span aria-live="polite">第 {Math.floor(pageOffset / pageSize) + 1} 頁<span className="client-roster-page-count">（本頁 {page.items.length} 筆）</span></span>
      <button type="button" disabled={loading || page.next_offset == null} onClick={nextPage}>下一頁</button>
    </nav>}
    {!loading && !error && page && page.items.length > 0 && <div className="client-roster-table-wrap"><table>
      <caption>客戶名冊清單（第 {Math.floor(pageOffset / pageSize) + 1} 頁）</caption>
      <thead><tr>
        <th scope="col"><button type="button" onClick={() => changeSort('case_no')}>案件編號{sortLabel('case_no')}</button></th>
        <th scope="col">匯入虛擬帳號</th>
        <th scope="col">內建虛擬帳號</th>
        <th scope="col"><button type="button" onClick={() => changeSort('customer_name')}>客戶姓名{sortLabel('customer_name')}</button></th>
        <th scope="col">電話</th><th scope="col">行政區</th><th scope="col">BeClass 胎數</th>
        <th scope="col"><button type="button" onClick={() => changeSort('service_days')}>服務天數{sortLabel('service_days')}</button></th>
        <th scope="col">下廚需求</th>
        <th scope="col"><button type="button" onClick={() => changeSort('expected_start_date')}>預計服務日期{sortLabel('expected_start_date')}</button></th>
        <th scope="col">案件／訂單狀態</th>
        <th scope="col" title="client_obligations.due_date（deposit）">訂金應繳日</th>
        <th scope="col" title="client_obligations.due_date（first）">第一期應繳日</th>
        <th scope="col" title="client_obligations.due_date（second）">第二期應繳日</th>
        <th scope="col" title="orders.staff_payment_due_date">訂單月嫂應付日</th>
        <th scope="col" title="staff_obligations.due_date">月嫂義務應付日</th>
        <th scope="col" title="client_obligations.due_date（subsidy_return）">客戶補助退還日</th>
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
        <td>{item.case_no}</td><td>{displayImportedVirtualAccounts(item.imported_virtual_accounts)}</td><td>{item.built_in_virtual_account ?? '—'}</td><td>{item.name ?? '—'}</td><td>{item.phone ?? '—'}</td><td>{item.district ?? '未登錄'}</td>
        <td>{item.multi_birth_count ?? '—'}</td><td>{item.service_days ?? '—'}</td><td>{displayCooking(item.requires_cooking)}</td>
        <td>{item.planned_start_date ?? '—'}</td><td>{item.order_status ?? '—'}</td>
        <td>{clientDueDates(item, 'deposit')}</td>
        <td>{clientDueDates(item, 'first')}</td>
        <td>{clientDueDates(item, 'second')}</td>
        <td>{item.staff_payment_due_date === undefined ? '未載入' : item.staff_payment_due_date ?? '無值'}</td>
        <td>{item.staff_obligation_dates === undefined ? '未載入' : item.staff_obligation_dates.length ? item.staff_obligation_dates.map((entry) => (
          <div key={entry.obligation_identity} title={entry.obligation_identity}>
            {entry.staff_name ?? `月嫂 #${entry.staff_id}`}／{staffObligationLabels[entry.obligation_kind] ?? entry.obligation_kind}：{entry.due_date ?? '無值'}
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
    >
      {detailLoading && <p role="status" className="client-roster-message">正在載入完整客戶資料…</p>}
      {detailError && <p role="alert" className="client-roster-message">{detailError}</p>}
      {detail?.case_no === selectedCaseNo && <ReadOnlyDetail detail={detail} />}
    </Drawer>
  </div>;
};

export default ClientRosterPage;
