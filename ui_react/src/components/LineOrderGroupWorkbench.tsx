import { staffDisplayLabel } from '../adapters/staff/staff_directory_adapter';
/**
 * File: LineOrderGroupWorkbench.tsx
 * Description: 三方服務群組唯讀工作區，以案件清單、加入狀況及可展開歷程呈現正式查詢。
 */
import { useEffect, useRef, useState, type FC } from 'react';
import { RefreshCw, Search } from 'lucide-react';
import { Drawer } from './Drawer';
import { lineOrderGroupQueryClient, type LineOrderGroupWorkspaceClient } from '../api/line_order_groups/line_order_group_query_client';
import { LineOrderGroupQueryError } from '../api/line_order_groups/line_order_group_query_errors';
import type { LineOrderGroupStatus, LineOrderGroupWorkspacePage, LineOrderGroupWorkspaceRecord, LineOrderGroupWorkspaceEventPage } from '../api/line_order_groups/line_order_group_query_schemas';
import { lineOrderGroupEventLabel, lineOrderGroupReason, lineOrderGroupStatusLabel } from '../adapters/line_order_groups/line_order_group_query_adapter';
import './LineOrderGroupWorkbench.css';

interface Props {
  client?: LineOrderGroupWorkspaceClient;
  search: string;
  status: LineOrderGroupStatus | 'all';
  page: number;
  onSearchChange(value: string): void;
  onStatusChange(value: LineOrderGroupStatus | 'all'): void;
  onPageChange(value: number): void;
}
interface QueryState<T> { loading: boolean; value: T | null; error: string | null; }
const pending = <T,>(): QueryState<T> => ({ loading: true, value: null, error: null });
const states: LineOrderGroupStatus[] = ['attention', 'inviting', 'bound', 'active', 'unbound', 'replaced', 'released'];
const memberLabels = { joined: '已加入', left: '已離開', pending: '尚未確認加入', unknown: '無法確認' };

function queryError(error: unknown): string {
  if (error instanceof LineOrderGroupQueryError) {
    if (error.status === 401) return '登入已失效，請重新登入後再試。';
    if (error.status === 403) return '目前帳號沒有查詢服務群組的權限。';
    if (error.status === 404) return '找不到此案件的服務群組，請重新整理清單。';
  }
  return '服務群組資料讀取失敗，請稍後再試。';
}
function time(value: string | null | undefined, full = false): string {
  if (!value) return '尚無紀錄';
  return new Intl.DateTimeFormat('zh-TW', { timeZone: 'Asia/Taipei', ...(full ? { year: 'numeric' as const } : {}), month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value));
}
function Status({ value }: { value: LineOrderGroupStatus }) {
  return <span className={`order-group-status order-group-status-${value}`}>{lineOrderGroupStatusLabel(value)}</span>;
}

export const LineOrderGroupWorkbench: FC<Props> = ({ client = lineOrderGroupQueryClient, search, status, page, onSearchChange, onStatusChange, onPageChange }) => {
  const [list, setList] = useState<QueryState<LineOrderGroupWorkspacePage>>(pending);
  const [reload, setReload] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<QueryState<LineOrderGroupWorkspaceRecord>>(pending);
  const [detailReload, setDetailReload] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [eventPage, setEventPage] = useState(1);
  const [eventReload, setEventReload] = useState(0);
  const [events, setEvents] = useState<QueryState<LineOrderGroupWorkspaceEventPage>>(pending);
  const listGeneration = useRef(0);
  const detailGeneration = useRef(0);
  const eventGeneration = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const generation = ++listGeneration.current;
    setList(pending());
    const timer = window.setTimeout(() => {
      void client.workspaceList({ search: search.trim() || undefined, status: status === 'all' ? undefined : status, page, pageSize: 25 }, { signal: controller.signal }).then(value => {
        if (controller.signal.aborted || generation !== listGeneration.current) return;
        if (page > Math.max(1, value.total_pages)) { onPageChange(Math.max(1, value.total_pages)); return; }
        setList({ loading: false, value, error: null });
      }).catch(error => {
        if (!controller.signal.aborted && generation === listGeneration.current) setList({ loading: false, value: null, error: queryError(error) });
      });
    }, 150);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [client, search, status, page, reload, onPageChange]);

  useEffect(() => {
    if (selected === null) return;
    const controller = new AbortController();
    const generation = ++detailGeneration.current;
    setDetail(pending());
    void client.workspaceDetail(selected, { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted && generation === detailGeneration.current) setDetail({ loading: false, value, error: null });
    }).catch(error => {
      if (!controller.signal.aborted && generation === detailGeneration.current) setDetail({ loading: false, value: null, error: queryError(error) });
    });
    return () => controller.abort();
  }, [client, selected, detailReload]);

  useEffect(() => {
    if (selected === null || !historyOpen || !detail.value) return;
    const controller = new AbortController();
    const generation = ++eventGeneration.current;
    setEvents(pending());
    void client.workspaceEvents(selected, { page: eventPage, pageSize: 25 }, { signal: controller.signal }).then(value => {
      if (controller.signal.aborted || generation !== eventGeneration.current) return;
      if (eventPage > Math.max(1, value.total_pages)) { setEventPage(Math.max(1, value.total_pages)); return; }
      setEvents({ loading: false, value, error: null });
    }).catch(error => {
      if (!controller.signal.aborted && generation === eventGeneration.current) setEvents({ loading: false, value: null, error: queryError(error) });
    });
    return () => controller.abort();
  }, [client, selected, historyOpen, eventPage, eventReload, detail.value]);

  const open = (caseNo: string) => {
    setDetail(pending()); setEvents(pending()); setHistoryOpen(false); setEventPage(1); setSelected(caseNo);
  };
  const record = detail.value;
  const clear = () => { onSearchChange(''); onStatusChange('all'); onPageChange(1); };

  return <section className="order-group-workbench">
    <div className="order-group-heading"><div><h2>三方服務群組</h2><p>查看案件的服務群組與加入狀況。</p></div><button type="button" className="order-group-button" disabled={list.loading} onClick={() => setReload(value => value + 1)}><RefreshCw aria-hidden="true" />重新整理</button></div>
    <div className="order-group-card">
      <div className="order-group-filters">
        <label className="order-group-search"><span className="sr-only">搜尋案件編號</span><Search aria-hidden="true" /><input type="search" aria-label="搜尋案件編號" placeholder="搜尋案件編號" maxLength={50} value={search} onChange={event => { onSearchChange(event.target.value); onPageChange(1); }} /></label>
        <label><span className="sr-only">群組狀態</span><select aria-label="群組狀態" value={status} onChange={event => { onStatusChange(event.target.value as Props['status']); onPageChange(1); }}><option value="all">全部狀態</option>{states.map(value => <option key={value} value={value}>{lineOrderGroupStatusLabel(value)}</option>)}</select></label>
      </div>
      {list.loading && <p className="order-group-empty" role="status">正在載入三方服務群組…</p>}
      {list.error && <div className="order-group-empty" role="alert"><p>{list.error}</p><button className="order-group-button" type="button" onClick={() => setReload(value => value + 1)}>重試查詢</button></div>}
      {list.value && <>
        {list.value.items.length === 0 ? <div className="order-group-empty"><h3>{search.trim() || status !== 'all' ? '沒有符合條件的群組' : '目前沒有服務群組綁定紀錄'}</h3><p>{search.trim() || status !== 'all' ? '可調整案件編號或群組狀態再查詢。' : '由工會人員在 LINE 群組內綁定案件後，會顯示在這裡。'}</p>{(search.trim() || status !== 'all') && <button type="button" className="order-group-button" onClick={clear}>清除條件</button>}</div> : <table className="order-group-table" data-control-id="line.order-groups.table"><caption className="sr-only">案件的服務群組與加入狀況</caption><thead><tr><th scope="col">案件</th><th scope="col">群組狀態</th><th scope="col">最近動態</th></tr></thead><tbody>{list.value.items.map(item => <tr key={item.case_no} data-attention={item.status === 'attention'}><td><button type="button" className="order-group-case" data-group-case={item.case_no} aria-label={`查看案件 ${item.case_no} 群組明細`} onClick={() => open(item.case_no)}>{item.case_no}</button><span className="order-group-person">{item.customer_name || '客戶資料待確認'}</span></td><td><Status value={item.status} /><span className={`order-group-secondary ${item.status === 'attention' ? 'order-group-attention' : ''}`}>{lineOrderGroupReason(item)}</span></td><td><span>{item.latest_event ? lineOrderGroupEventLabel(item.latest_event) : '尚無群組動態紀錄'}</span>{item.latest_event && <time className="order-group-secondary" dateTime={item.latest_event.occurred_at}>{time(item.latest_event.occurred_at)}</time>}</td></tr>)}</tbody></table>}
        {list.value.total > 0 && <div className="order-group-pagination"><span>共 {list.value.total} 筆群組</span>{list.value.total_pages > 1 && <div><button type="button" className="order-group-button" aria-label="上一頁三方服務群組" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>‹</button><span>第 {list.value.page} / {list.value.total_pages} 頁</span><button type="button" className="order-group-button" aria-label="下一頁三方服務群組" disabled={page >= list.value.total_pages} onClick={() => onPageChange(page + 1)}>›</button></div>}</div>}
      </>}
    </div>
    <Drawer isOpen={selected !== null} onClose={() => setSelected(null)} title={selected ? `案件 ${selected}` : '三方服務群組'} className="order-group-drawer" size="normal" closeLabel="關閉群組明細">
      {detail.loading && <p role="status">正在載入群組明細…</p>}
      {detail.error && <div role="alert"><p>{detail.error}</p><button className="order-group-button" type="button" onClick={() => setDetailReload(value => value + 1)}>重試明細</button></div>}
      {record && <>
        <section className="order-group-current" aria-label="目前群組狀況"><Status value={record.status} /><p className={record.status === 'attention' ? 'order-group-attention' : ''}>{lineOrderGroupReason(record)}。</p></section>
        <dl className="order-group-facts"><div><dt>客戶</dt><dd>{record.customer_name || '資料待確認'}</dd></div><div><dt>最近動態</dt><dd>{time(record.latest_event?.occurred_at)}</dd></div><div><dt>群組綁定時間</dt><dd>{time(record.bound_at, true)}</dd></div><div><dt>最近邀請時間</dt><dd>{record.last_invitation_at ? time(record.last_invitation_at, true) : '尚無本次邀請紀錄'}</dd></div></dl>
        <section className="order-group-members"><h3>客戶與月嫂</h3><p>依本次綁定後收到的群組加入／離開紀錄顯示。</p>{record.members.length === 0 ? <p>目前無法確認本案成員資料。</p> : <ul>{record.members.map((member, index) => <li key={`${member.role}-${index}`}><div><strong>{member.role === 'staff' ? staffDisplayLabel(member.staff_union_no, member.name || '姓名未設定') : member.name || '客戶資料待確認'}</strong><span>{member.role === 'customer' ? '客戶' : '月嫂'}</span></div><span className={`order-group-member-${member.membership_status}`}>{memberLabels[member.membership_status]}</span></li>)}</ul>}<p className="order-group-note">工會人員於 LINE 群組內管理；此處不代表完整群組成員名單。邀請排入發送不代表已送達或已加入。</p></section>
        <details className="order-group-history" open={historyOpen} onToggle={event => setHistoryOpen(event.currentTarget.open)}><summary>群組歷程</summary>{historyOpen && <>
          {events.loading && <p role="status">正在載入群組歷程…</p>}
          {events.error && <div role="alert"><p>{events.error}</p><button className="order-group-button" type="button" onClick={() => setEventReload(value => value + 1)}>重試歷程</button></div>}
          {events.value && <>{events.value.items.length === 0 ? <p>尚無群組歷程。</p> : <ol>{events.value.items.map(event => <li key={event.event_key}><span>{lineOrderGroupEventLabel(event)}</span><time dateTime={event.occurred_at}>{time(event.occurred_at, true)}</time></li>)}</ol>}{events.value.total_pages > 1 && <div className="order-group-pagination"><span>共 {events.value.total} 筆紀錄</span><div><button className="order-group-button" type="button" aria-label="上一頁群組事件" disabled={eventPage <= 1} onClick={() => setEventPage(value => value - 1)}>‹</button><span>第 {events.value.page} / {events.value.total_pages} 頁</span><button className="order-group-button" type="button" aria-label="下一頁群組事件" disabled={eventPage >= events.value.total_pages} onClick={() => setEventPage(value => value + 1)}>›</button></div></div>}</>}
        </>}</details>
        <details className="order-group-help"><summary>綁定與邀請方式</summary><p>由已綁定 LINE 且有權限的工會人員，在服務群組內輸入：</p><code>綁定訂單 {record.case_no} 〈本群組邀請網址〉</code><p>請將佔位文字換成從本群組複製的邀請網址。三段之間可用空白或換行，網址中間不能拆行。</p><p>綁定完成後，再於同一群組輸入：</p><code>發送邀請</code><p>更新網址時，重新輸入完整綁定指令；不會自動發送。案件訂金須已確認核銷，客戶與指派月嫂須完成 LINE 身分綁定。</p></details>
      </>}
    </Drawer>
  </section>;
};
