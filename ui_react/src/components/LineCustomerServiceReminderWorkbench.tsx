/** Read-only archive for cases opened before customer-service retirement. */
import { useEffect, useState } from 'react';
import type { CustomerServiceClient } from '../api/customer_service/customer_service_client';
import type { CustomerServiceDetail, CustomerServicePage, CustomerServiceStatus } from '../api/customer_service/customer_service_schemas';
import { formatTaipeiDateTime } from '../shared/taipeiTime';
import './LineCustomerServiceReminderWorkbench.css';

const statusLabels: Record<CustomerServiceStatus, string> = {
  waiting: '移交前待處理',
  handling: '移交前處理中',
  resolved: '已結案',
};

export function LineCustomerServiceReminderWorkbench({ client }: { client: Partial<CustomerServiceClient> }) {
  const [status, setStatus] = useState<CustomerServiceStatus>('resolved');
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<CustomerServicePage | null>(null);
  const [listError, setListError] = useState('');
  const [ticketId, setTicketId] = useState<number | null>(null);
  const [detail, setDetail] = useState<CustomerServiceDetail | null>(null);
  const [detailError, setDetailError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    if (!client.listTickets) {
      setListError('目前無法查閱歷史客服紀錄。');
      return;
    }
    void client.listTickets({ status, page, page_size: 25 }, { signal: controller.signal }).then(
      data => { if (!controller.signal.aborted) setResult(data); },
      () => { if (!controller.signal.aborted) setListError('讀取歷史客服紀錄失敗。'); },
    );
    return () => controller.abort();
  }, [client, status, page]);

  useEffect(() => {
    if (ticketId === null || !client.getTicketDetail) return;
    const controller = new AbortController();
    void client.getTicketDetail(ticketId, { signal: controller.signal }).then(
      data => { if (!controller.signal.aborted) setDetail(data); },
      () => { if (!controller.signal.aborted) setDetailError('讀取這筆紀錄失敗。'); },
    );
    return () => controller.abort();
  }, [client, ticketId]);

  const changePage = (nextPage: number) => {
    setResult(null);
    setListError('');
    setTicketId(null);
    setDetail(null);
    setDetailError('');
    setPage(nextPage);
  };

  return <section className="line-ticket-reminder-workspace" aria-label="歷史客服紀錄">
    <div className="line-ticket-list-heading"><h2>歷史客服紀錄</h2></div>
    <label>原工單狀態 <select value={status} onChange={event => {
      const nextStatus = event.currentTarget.value;
      if (nextStatus === 'waiting' || nextStatus === 'handling' || nextStatus === 'resolved') {
        changePage(1);
        setStatus(nextStatus);
      }
    }}>
      <option value="resolved">{statusLabels.resolved}</option>
      <option value="waiting">{statusLabels.waiting}</option>
      <option value="handling">{statusLabels.handling}</option>
    </select></label>
    {listError && <p role="alert">{listError}</p>}
    {!listError && result === null && <p role="status">載入中…</p>}
    {result && result.items.length === 0 && <p>沒有符合條件的歷史紀錄。</p>}
    {result && result.items.length > 0 && (
      <div className="line-table-scroll">
        <table className="line-ticket-reminder-table">
          <thead><tr><th scope="col">工單編號</th><th scope="col">案號</th><th scope="col">原狀態</th><th scope="col">建立時間</th></tr></thead>
          <tbody>{result.items.map(ticket => <tr key={ticket.ticket_id}>
            <td><button type="button" disabled={!client.getTicketDetail} onClick={() => {
              if (ticket.ticket_id === ticketId) return;
              setDetail(null);
              setDetailError('');
              setTicketId(ticket.ticket_id);
            }}>#{ticket.ticket_id}</button></td>
            <td>{ticket.case_no ?? '—'}</td>
            <td>{statusLabels[ticket.status]}</td>
            <td>{formatTaipeiDateTime(ticket.created_at ?? "")}</td>
          </tr>)}</tbody>
        </table>
      </div>
    )}
    {result && (page > 1 || page * result.page_size < result.total) && (
      <nav className="line-ticket-reminder-pagination" aria-label="紀錄分頁">
        <button type="button" disabled={page === 1} onClick={() => changePage(page - 1)}>上一頁</button>
        <span>第 {page} 頁</span>
        <button type="button" disabled={page * result.page_size >= result.total} onClick={() => changePage(page + 1)}>下一頁</button>
      </nav>
    )}
    {ticketId !== null && <section aria-label={`工單 #${ticketId} 紀錄`}>
      <h3>工單 #{ticketId}</h3>
      {detailError && <p role="alert">{detailError}</p>}
      {!detailError && !detail && <p role="status">載入中…</p>}
      {detail && <>
        {detail.ticket.internal_note && <p>{detail.ticket.internal_note}</p>}
        {detail.events.length === 0 ? <p>沒有留言紀錄。</p> : <ul>{detail.events.map(event => <li key={event.id}>
          <time>{formatTaipeiDateTime(event.created_at)}</time>{' '}{event.message_text ?? '狀態更新'}
        </li>)}</ul>}
      </>}
    </section>}
  </section>;
}
