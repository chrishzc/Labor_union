/**
 * File: LineCustomerServiceReminderWorkbench.tsx
 * Description: 唯讀客服提醒清單，使用 server 來源投影與分頁；不掛載回覆或結案操作。
 */
import { useEffect, useRef, useState } from 'react';
import { RefreshCw, Search } from 'lucide-react';
import type { CustomerServiceReminderClient } from '../api/customer_service/customer_service_client';
import type { CustomerServiceReminderPage, CustomerServiceReminderSource } from '../api/customer_service/customer_service_schemas';
import './LineCustomerServiceReminderWorkbench.css';

const SOURCES: Record<CustomerServiceReminderSource, string> = {
  handoff: 'LINE 轉真人', complaint: 'LINE 明確客訴', feedback: '回答未解決回饋',
  order: '訂單異動申請', service: '服務與問答轉介', binding: '身分綁定協助', unknown: '來源待確認',
};
const REASONS = {
  explicit_human_request: '使用者已確認轉接真人',
  explicit_wrong_answer: '回答未符合需求，已確認轉真人',
  complaint: '明確客訴，需要人員接手',
  unresolved_feedback: '對該次回答選擇「未解決」',
  order_change_requested: '訂單異動申請，待工會確認',
  service_referral: '由服務與問答轉交人工協助',
  binding_failure: '身分綁定失敗達門檻，需要協助',
  unknown: '既有工單尚無明確來源資訊',
};
type ReminderStatus = 'open' | 'waiting' | 'handling';
const statusLabel = { waiting: '待接手', handling: '處理中' };
const pageSize = 25;

export function LineCustomerServiceReminderWorkbench({ client }: { client: Partial<CustomerServiceReminderClient> }) {
  const initial = useRef(new URLSearchParams(window.location.hash.split('?', 2)[1] ?? '')).current;
  const [status, setStatus] = useState<ReminderStatus>(() => initial.get('ticket_state') === 'waiting' ? 'waiting' : initial.get('ticket_state') === 'handling' ? 'handling' : 'open');
  const [source, setSource] = useState<CustomerServiceReminderSource | 'all'>(() => {
    const value = initial.get('ticket_source');
    return value && Object.hasOwn(SOURCES, value) ? value as CustomerServiceReminderSource : 'all';
  });
  const [search, setSearch] = useState(initial.get('ticket_q') ?? '');
  const [page, setPage] = useState(() => {
    const value = Number(initial.get('ticket_page'));
    return Number.isSafeInteger(value) && value > 0 ? value : 1;
  });
  const [reload, setReload] = useState(0);
  const [result, setResult] = useState<CustomerServiceReminderPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const current = ++generation.current;
    setLoading(true); setResult(null); setError(null);
    const timer = window.setTimeout(() => {
      if (!client.listReminders) {
        setLoading(false); setError('客服提醒查詢目前無法使用，請稍後重新整理。'); return;
      }
      void client.listReminders({ status, source: source === 'all' ? undefined : source, search: search.trim() || undefined, page, page_size: pageSize }, { signal: controller.signal })
        .then(value => { if (!controller.signal.aborted && current === generation.current) setResult(value); })
        .catch(() => { if (!controller.signal.aborted && current === generation.current) setError('客服案件暫時無法載入，請重新整理後再確認。'); })
        .finally(() => { if (!controller.signal.aborted && current === generation.current) setLoading(false); });
    }, 150);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [client, status, source, search, page, reload]);

  useEffect(() => {
    const [route, query = ''] = window.location.hash.split('?', 2);
    if (!['#line-management', '#/line-management', '#line', '#/line'].includes(route)) return;
    const params = new URLSearchParams(query);
    const set = (key: string, value: string, fallback: string) => value === fallback || !value ? params.delete(key) : params.set(key, value);
    set('ticket_state', status, 'open'); set('ticket_source', source, 'all'); set('ticket_q', search, ''); set('ticket_page', String(page), '1');
    params.delete('ticket_category');
    const next = params.toString();
    window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}${route}${next ? `?${next}` : ''}`);
  }, [status, source, search, page]);

  const counts = result ? { open: result.summary.waiting + result.summary.handling, waiting: result.summary.waiting, handling: result.summary.handling } : null;
  const totalPages = result ? Math.max(1, Math.ceil(result.total / result.page_size)) : 1;
  const clear = () => { setSearch(''); setSource('all'); setPage(1); };
  return <section className="line-ticket-reminder-workspace" aria-label="客服案件提醒">
    <h2>客服案件</h2>
    <div className="line-ticket-reminder-card">
      <div className="line-ticket-reminder-top">
        <nav className="line-ticket-status-tabs" aria-label="客服案件處理狀態">
          {([['open', '需要處理'], ['waiting', '待接手'], ['handling', '處理中']] as const).map(([key, label]) => <button type="button" key={key} aria-pressed={status === key} onClick={() => { setStatus(key); setPage(1); }}>{label}<span>{counts?.[key] ?? '—'}</span></button>)}
        </nav>
        <button type="button" className="line-secondary-btn" onClick={() => setReload(value => value + 1)}><RefreshCw aria-hidden="true" />重新整理</button>
      </div>
      <div className="line-ticket-reminder-filters">
        <label className="line-ticket-reminder-search"><span className="sr-only">搜尋工單或案件編號</span><Search aria-hidden="true" /><input type="search" maxLength={191} className="line-search-input" placeholder="搜尋工單或案件編號" value={search} onChange={event => { setSearch(event.target.value); setPage(1); }} /></label>
        <select aria-label="篩選客服進件來源" className="line-filter-select" value={source} onChange={event => { setSource(event.target.value as CustomerServiceReminderSource | 'all'); setPage(1); }}><option value="all">全部進件來源</option>{Object.entries(SOURCES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
      </div>
      {loading && <div className="line-loading" role="status">正在載入客服案件…</div>}
      {error && <div className="line-error" role="alert">{error}</div>}
      {!loading && result && (result.items.length === 0 ? <div className="line-empty-state"><h3>{search || source !== 'all' ? '找不到符合條件的案件' : '目前沒有待處理案件'}</h3>{(search || source !== 'all') && <button type="button" className="line-secondary-btn" onClick={clear}>清除篩選</button>}</div> : <div className="line-table-scroll"><table className="line-ticket-reminder-table" data-control-id="line.ticket.table"><caption className="sr-only">客服提醒清單</caption><thead><tr><th scope="col">客服對象</th><th scope="col">進件來源</th><th scope="col">處理狀態</th><th scope="col">更新時間</th></tr></thead><tbody>{result.items.map(ticket => <tr key={ticket.ticket_id}>
        <td><strong>{ticket.client_name || '未具名使用者'}</strong><span className="line-ticket-reminder-secondary">{ticket.case_no || `#${ticket.ticket_id}`}</span></td>
        <td><div className="line-ticket-reminder-source">{SOURCES[ticket.source]}{ticket.is_priority && <span className="line-ticket-priority">優先</span>}</div><span className="line-ticket-reminder-secondary">{REASONS[ticket.reason]}</span></td>
        <td><span className={`line-status line-status-${ticket.status}`}>{statusLabel[ticket.status]}</span>{ticket.assigned_admin_name && <span className="line-ticket-reminder-secondary">{ticket.assigned_admin_name}</span>}</td>
        <td>{ticket.updated_at ? new Date(ticket.updated_at).toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Taipei' }) : '—'}</td>
      </tr>)}</tbody></table></div>)}
      {!loading && result && totalPages > 1 && <nav className="line-ticket-reminder-pagination" aria-label="客服案件分頁"><span>第 {result.page}／{totalPages} 頁</span><div><button type="button" className="line-secondary-btn" disabled={result.page <= 1} onClick={() => setPage(result.page - 1)}>上一頁</button><button type="button" className="line-secondary-btn" disabled={result.page >= totalPages} onClick={() => setPage(result.page + 1)}>下一頁</button></div></nav>}
    </div>
  </section>;
}
