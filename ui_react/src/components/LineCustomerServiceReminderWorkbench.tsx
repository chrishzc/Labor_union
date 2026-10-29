/** Six-column customer-service inbox; completion uses the existing owner commands. */
import { useEffect, useRef, useState } from 'react';
import type { CustomerServiceActionsClient, CustomerServiceClient, CustomerServiceReminderClient } from '../api/customer_service/customer_service_client';
import type { CustomerServiceReminderItem, CustomerServiceReminderPage, CustomerServiceResolvePreview, CustomerServiceResolvePreviewRequest } from '../api/customer_service/customer_service_schemas';
import { CustomerServiceClientError } from '../api/customer_service/customer_service_errors';
import './LineCustomerServiceReminderWorkbench.css';
const sources = { handoff: 'LINE 轉真人', complaint: 'LINE 明確客訴', feedback: '回答未解決回饋', order: '訂單異動申請', service: '服務與問答轉介', binding: '身分綁定協助', unknown: '來源待確認' };
type Client = Partial<CustomerServiceClient & CustomerServiceActionsClient & CustomerServiceReminderClient>;
type Operation = { key: string; correlationId: string; payload: CustomerServiceResolvePreviewRequest; preview: CustomerServiceResolvePreview | null };
const dateLabel = (value: string | null) => value ? new Date(value).toLocaleString('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Taipei' }) : '時間待確認';
export function LineCustomerServiceReminderWorkbench({ client }: { client: Client }) {
  const initial = useRef(new URLSearchParams(window.location.hash.split('?', 2)[1] ?? '')).current;
  const [search, setSearch] = useState(initial.get('ticket_q') ?? '');
  const [page, setPage] = useState(() => { const value=Number(initial.get('ticket_page')); return Number.isSafeInteger(value)&&value>0?value:1; });
  const [reload, setReload] = useState(0);
  const [result, setResult] = useState<CustomerServiceReminderPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [pending, setPending] = useState<number | null>(null);
  const operations = useRef(new Map<number, Operation>());
  const busy = useRef(false), mounted = useRef(true), searchInput = useRef<HTMLInputElement>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setResult(null); setError('');
    const timer = window.setTimeout(() => {
      if (!client.listReminders) { setLoading(false); setError('客服案件查詢目前無法使用。'); return; }
      void client.listReminders({ status: 'open', search: search.trim() || undefined, page, page_size: 25 }, { signal: controller.signal })
        .then(value => { if (!controller.signal.aborted) {
          if (!value.items.length && page > 1 && value.total > 0) setPage(Math.max(1, Math.ceil(value.total / value.page_size)));
          else setResult(value);
        } }).catch(() => { if (!controller.signal.aborted) setError('客服案件暫時無法載入，請重新整理後再確認。'); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 150);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [client, search, page, reload]);
  useEffect(() => {
    const [route, query = ''] = window.location.hash.split('?', 2);
    if (!['#line-management', '#/line-management', '#line', '#/line'].includes(route)) return;
    const params = new URLSearchParams(query);
    ['ticket_state', 'ticket_source', 'ticket_category'].forEach(key => params.delete(key));
    if (search) params.set('ticket_q', search); else params.delete('ticket_q');
    if (page > 1) params.set('ticket_page', String(page)); else params.delete('ticket_page');
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}${route}${params.size ? `?${params}` : ''}`);
  }, [search, page]);
  async function complete(ticket: CustomerServiceReminderItem) {
    if (busy.current) return;
    if (!client.getTicketDetail || !client.previewUpdate || !client.applyUpdate) { setError('目前無法完成案件，請重新整理後再試。'); return; }
    busy.current = true; setPending(ticket.ticket_id); setError(''); setNotice('');
    try {
      let intent = operations.current.get(ticket.ticket_id);
      if (!intent) {
        const detail = await client.getTicketDetail(ticket.ticket_id);
        if (!mounted.current) return;
        if (detail.ticket.status === 'resolved') { setReload(value => value + 1); setNotice('案件已完成，已重新查詢清單。'); return; }
        if (detail.ticket.version !== ticket.version) { setReload(value => value + 1); setNotice('案件有新內容，請查看最新留言後再決定是否完成。'); return; }
        intent = { key: crypto.randomUUID(), correlationId: crypto.randomUUID(), payload: { status: 'resolved', internal_note: detail.ticket.internal_note ?? null, expected_version: ticket.version }, preview: null };
        operations.current.set(ticket.ticket_id, intent);
      }
      if (!intent.preview) intent.preview = await client.previewUpdate(ticket.ticket_id, intent.payload, { correlationId: intent.correlationId });
      if (!mounted.current) return;
      await client.applyUpdate(ticket.ticket_id, { ...intent.payload, preview_fingerprint: intent.preview.preview_fingerprint }, { correlationId: intent.correlationId, idempotencyKey: intent.key });
      operations.current.delete(ticket.ticket_id);
      if (!mounted.current) return;
      setNotice('案件完成操作已確認，已重新查詢清單。'); setReload(value => value + 1); searchInput.current?.focus();
    } catch (caught) {
      if (!mounted.current) return;
      if (caught instanceof CustomerServiceClientError && ['conflict', 'domain_blocked', 'idempotency_mismatch'].includes(caught.category)) {
        operations.current.delete(ticket.ticket_id); setReload(value => value + 1); setNotice(caught.category === 'domain_blocked' ? '此客服來源仍有未完成事項，請先完成原綁定或業務作業，再回來結案。' : '案件狀態或留言已更新，請查看最新資料後再操作。');
      } else if (caught instanceof CustomerServiceClientError && ['forbidden', 'unauthenticated'].includes(caught.category)) {
        operations.current.delete(ticket.ticket_id); setError('目前帳號沒有完成客服案件的權限，請確認登入身分。');
      } else setError('完成結果尚未確認；請按「確認完成結果」，會沿用原操作查核，避免重複提交。');
    } finally { busy.current = false; if (mounted.current) setPending(null); }
  }
  async function copy(name: string) {
    try { await navigator.clipboard.writeText(name); if (mounted.current) setNotice(`已複製 LINE 顯示名稱：${name}`); }
    catch { if (mounted.current) setError('無法自動複製，請選取 LINE 顯示名稱後手動複製。'); }
  }
  const totalPages = result ? Math.max(1, Math.ceil(result.total / result.page_size)) : 1;
  return <section className="line-ticket-reminder-workspace" aria-label="客服案件提醒">
    <div className="line-ticket-list-heading"><h2>客服案件</h2><span>{result ? `${result.total} 件待處理` : '—'}</span></div>
    <p className="line-ticket-list-description">只列尚未解決的需求；處理完成後即從清單移除。</p>
    <div className="line-ticket-reminder-card">
      <div className="line-ticket-reminder-filters"><label className="line-ticket-reminder-search"><span className="sr-only">搜尋姓名、工單或案件編號</span><input ref={searchInput} type="search" className="line-search-input" maxLength={191} placeholder="搜尋姓名、工單或案件編號" value={search} onChange={event => { setSearch(event.target.value); setPage(1); }} /></label><button className="line-secondary-btn" disabled={pending !== null} onClick={() => setReload(value => value + 1)}>重新整理</button></div>
      {notice && <p className="line-ticket-list-notice" role="status">{notice}</p>}{error && <div className="line-error" role="alert">{error}</div>}
      {loading && <div className="line-loading" role="status">正在載入客服案件…</div>}
      {!loading && result && (result.items.length === 0 ? <div className="line-empty-state"><h3>{search ? '找不到符合條件的案件' : '目前沒有需要處理的客服案件'}</h3>{search && <button className="line-secondary-btn" onClick={() => { setSearch(''); setPage(1); }}>清除搜尋</button>}</div> : <div className="line-table-scroll"><table className="line-ticket-reminder-table" data-control-id="line.ticket.table"><caption className="sr-only">未解決客服案件清單</caption><thead><tr>{['客服對象', 'LINE 顯示名稱', '進件來源', '內容', '申請時間', '案件完成'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{result.items.map(ticket => <tr key={ticket.ticket_id}>
        <td><strong>{ticket.client_name || '未具名使用者'}</strong><span className="line-ticket-reminder-secondary">{ticket.case_no || `#${ticket.ticket_id}`}</span></td>
        <td><div className="line-ticket-name-copy">{ticket.line_display_name ? <><span>{ticket.line_display_name}</span><button className="line-ticket-copy" aria-label={`複製工單 ${ticket.ticket_id} 的 LINE 顯示名稱`} onClick={() => void copy(ticket.line_display_name!)}>複製</button></> : <span className="line-ticket-reminder-secondary">尚未取得</span>}</div></td>
        <td>{sources[ticket.source]}</td>
        <td>{ticket.messages.length ? <><p className="line-ticket-message">{ticket.messages[0]}</p>{ticket.messages.length > 1 && <details className="line-ticket-more-messages"><summary>另 {ticket.messages.length - 1} 則留言</summary>{ticket.messages.slice(1).map((message, index) => <p key={index}>{message}</p>)}</details>}</> : <span className="line-ticket-reminder-secondary">{ticket.sources.includes('complaint') ? '客訴內容已去敏，請核對原對話。' : '尚未留言'}</span>}</td>
        <td>{dateLabel(ticket.requested_at)}</td>
        <td><button className="line-secondary-btn" disabled={pending !== null} onClick={() => void complete(ticket)}>{pending === ticket.ticket_id ? '確認中…' : operations.current.has(ticket.ticket_id) ? '確認完成結果' : '處理完成'}</button></td>
      </tr>)}</tbody></table></div>)}
      {!loading && result && totalPages > 1 && <nav className="line-ticket-reminder-pagination" aria-label="客服案件分頁"><span>第 {result.page}／{totalPages} 頁</span><div><button className="line-secondary-btn" disabled={result.page <= 1 || pending !== null} onClick={() => setPage(result.page - 1)}>上一頁</button><button className="line-secondary-btn" disabled={result.page >= totalPages || pending !== null} onClick={() => setPage(result.page + 1)}>下一頁</button></div></nav>}
    </div>
  </section>;
}
