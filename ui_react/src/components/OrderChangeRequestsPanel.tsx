import { useEffect, useState } from 'react';
import {
  orderChangeRequestsClient, type LegacyOrderChangePage, type OrderChangeRequestItem, type OrderChangeRequestPage,
} from '../api/orders/order_change_requests_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import './OrderChangeRequestsPanel.css';

const KIND_LABELS = {
  service_address: '服務地址',
  cooking_requirement: '下廚需求',
  service_days: '服務日期及天數',
  daily_service_window: '每日服務時段',
  other: '其他訂單內容',
};
const FIELD_LABELS: Record<string, string> = {
  service_city: '服務縣市',
  service_address: '服務地址',
  residence_type: '居住型態',
  floor_elevator_notes: '樓層及電梯備註',
  requires_cooking: '是否需要下廚',
  cooking_notes: '下廚需求說明',
  service_start_time: '每日開始時間',
  service_end_time: '每日結束時間',
  service_end_day_offset: '結束日',
  details: '變更說明',
};
const dateTime = new Intl.DateTimeFormat('zh-TW', {
  dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Taipei',
});
const LEGACY_STATUS_LABELS = { waiting: '待處理', handling: '處理中', resolved: '已結案' };

type Props = { caseNo: string; onOpenCase?: never } | { caseNo?: never; onOpenCase: (caseNo: string) => void };

function ContentFields({ values }: { values: Record<string, string> }) {
  if (Object.keys(values).length === 0) return <p>沒有既有欄位</p>;
  return <dl>{Object.entries(values).map(([key, value]) => (
    <div key={key}>
      <dt>{FIELD_LABELS[key] ?? key}</dt>
      <dd>{key === 'service_end_day_offset' ? value === '1' ? '隔天' : '同一天' : value}</dd>
    </div>
  ))}</dl>;
}

function RequestDetails({ item, onComplete }: {
  item: OrderChangeRequestItem;
  onComplete: (item: OrderChangeRequestItem) => void;
}) {
  const [result, setResult] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function complete() {
    if (submitting || item.status !== 'pending' || !result.trim()) return;
    setError(null);
    setSubmitting(true);
    try {
      const observed = await orderChangeRequestsClient.complete(item.request_id, item.version, result.trim());
      if (observed.request_id !== item.request_id || observed.status !== 'completed') {
        throw new Error('申請狀態讀回不一致');
      }
      onComplete(observed);
    } catch (caught) {
      setError(caught instanceof ApiHttpError && caught.status === 409
        ? '此申請已由他人更新。請重新整理後確認辦理結果。'
        : '無法確認結案結果，請重新整理或再次送出。');
    } finally {
      setSubmitting(false);
    }
  }

  return <>
    <div className="order-change-request-comparison">
      <div><h3>送出時的內容</h3><ContentFields values={item.before} /></div>
      <div><h3>客戶申請內容</h3><ContentFields values={item.requested} /></div>
    </div>
    {item.status === 'completed' ? <>
      <p className="order-change-request-result">{item.completion.result}</p>
      <p>經辦人 {item.completion.actor_name}　結案時間 {dateTime.format(new Date(item.completion.completed_at))}</p>
    </> : <form onSubmit={(event) => { event.preventDefault(); void complete(); }}>
      <label>辦理結果
        <textarea value={result} onChange={(event) => setResult(event.target.value)} maxLength={1000} rows={3} required disabled={submitting} />
      </label>
      <p>請先從對應的業務入口辦理，再記錄結果。結案後請在官方帳號回覆客戶。</p>
      {error && <p role="alert">{error}</p>}
      <button type="submit" className="tracker-reload-button" disabled={submitting || !result.trim()}>
        {submitting ? '結案中…' : '記錄結果並結案'}
      </button>
    </form>}
  </>;
}

function LegacyReferences({ caseNo }: { caseNo: string }) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState<LegacyOrderChangePage | null>(null);
  const [beforeId, setBeforeId] = useState<number | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setPage(null);
    setError(false);
    void orderChangeRequestsClient.legacy(caseNo, beforeId, controller.signal)
      .then((loaded) => { if (!controller.signal.aborted) setPage(loaded); })
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [open, caseNo, beforeId]);

  return <details onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>舊訂單異動工單參照</summary>
    {open && <>
      {error && <p role="alert">暫時無法取得舊工單參照。</p>}
      {!error && page === null && <p role="status">舊工單參照載入中…</p>}
      {page?.items.length === 0 && <p>此案沒有符合的舊表單紀錄。</p>}
      {page && <ul className="order-change-request-list">
        {page.items.map((reference) => <li key={reference.event_id}>
          舊工單 #{reference.ticket_id}　事件 #{reference.event_id}　{LEGACY_STATUS_LABELS[reference.ticket_status]}　{dateTime.format(new Date(reference.submitted_at))}
        </li>)}
      </ul>}
      {beforeId !== null && <button type="button" className="tracker-reload-button" onClick={() => setBeforeId(null)}>回到最新舊工單</button>}
      {page?.next_before_id != null && <button type="button" className="tracker-reload-button" onClick={() => setBeforeId(page.next_before_id)}>下一頁舊工單</button>}
    </>}
  </details>;
}

export function OrderChangeRequestsPanel({ caseNo, onOpenCase }: Props) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState<OrderChangeRequestPage | null>(null);
  const [beforeId, setBeforeId] = useState<number | null>(null);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setLoading(true);
    setError(false);
    setPage(null);
    void orderChangeRequestsClient.list(caseNo, beforeId, controller.signal)
      .then((loaded) => { if (!controller.signal.aborted) setPage(loaded); })
      .catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [open, caseNo, beforeId, revision]);

  const refresh = () => setRevision((current) => current + 1);
  const readBack = (observed: OrderChangeRequestItem) => setPage((current) => current === null ? null : {
    ...current, items: current.items.map((item) => item.request_id === observed.request_id ? observed : item),
  });
  const label = caseNo ? '訂單異動申請紀錄' : '待處理訂單異動申請';
  return <details className="order-v2-overview-details order-change-requests" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>{label}</summary>
    {open && <section aria-label={label}>
      <button type="button" className="tracker-reload-button" onClick={refresh} disabled={loading}>重新整理申請</button>
      {loading && <p role="status">申請載入中…</p>}
      {error && <p role="alert">暫時無法取得申請，請重新整理。</p>}
      {page?.items.length === 0 && <p>{caseNo ? '此案尚無訂單異動申請。' : '目前沒有待處理的訂單異動申請。'}</p>}
      {page && <ul className="order-change-request-list">
        {page.items.map((item) => <li key={item.request_id}>
          {onOpenCase ? <div className="order-change-request-summary">
            <span>#{item.request_id}　{item.case_no}　{KIND_LABELS[item.kind]}　{dateTime.format(new Date(item.submitted_at))}</span>
            <button type="button" className="tracker-reload-button" onClick={() => onOpenCase(item.case_no)}>查看案件 {item.case_no}</button>
          </div> : <details>
            <summary>#{item.request_id}　{KIND_LABELS[item.kind]}　{item.status === 'pending' ? '待處理' : '已結案'}　{dateTime.format(new Date(item.submitted_at))}</summary>
            <RequestDetails item={item} onComplete={readBack} />
          </details>}
        </li>)}
      </ul>}
      {beforeId !== null && <button type="button" className="tracker-reload-button" onClick={() => setBeforeId(null)} disabled={loading}>回到最新申請</button>}
      {page?.next_before_id != null && <button type="button" className="tracker-reload-button" onClick={() => setBeforeId(page.next_before_id)}>下一頁</button>}
      {caseNo && <LegacyReferences caseNo={caseNo} />}
    </section>}
  </details>;
}
