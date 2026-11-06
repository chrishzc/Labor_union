import { useEffect, useRef, useState } from 'react';
import {
  cancellationNotificationClient, type CancellationNotice, type CancellationNoticeKind,
} from '../api/line_order_groups/cancellation_notification_client';
import { ApiHttpError } from '../api/shared/typed_errors';

const labels: Record<CancellationNoticeKind, string> = {
  settlement: '通知客戶結算明細',
  refund: '通知客戶退款完成',
  collection: '通知客戶補收入帳',
};
const statuses: Record<string, string> = {
  pending: '待發送',
  processing: '寄送中',
  sent: '發送成功',
  retryable_failed: '寄送失敗，等待重試',
  failed: '寄送失敗',
  cancelled: '寄送已取消',
  uncertain: '寄送結果未確認',
};

export function CancellationSettlementNotices({
  caseNo, settlementOnly = false,
}: { caseNo: string; settlementOnly?: boolean }) {
  const [notices, setNotices] = useState<CancellationNotice[]>([]);
  const [selected, setSelected] = useState<CancellationNoticeKind | null>(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState('');
  const [sendFeedback, setSendFeedback] = useState('');
  const sendingRef = useRef(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    void cancellationNotificationClient.previews(caseNo, controller.signal).then(items => {
      if (!controller.signal.aborted) setNotices(settlementOnly ? items.filter(item => item.kind === 'settlement') : items);
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) {
        setNotices([]);
        setError(failure instanceof ApiHttpError ? failure.message : '暫時無法取得取消結算通知。');
      }
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [caseNo, revision, settlementOnly]);

  function refresh() {
    setSelected(null);
    setLoading(true);
    setRevision(value => value + 1);
  }

  async function send(notice: CancellationNotice) {
    if (!notice.fingerprint || sendingRef.current) return;
    sendingRef.current = true;
    setSending(true);
    setSendFeedback('');
    try {
      const result = await cancellationNotificationClient.send(caseNo, notice.kind, notice.fingerprint);
      setNotices(items => items.map(item => item.kind === notice.kind
        ? { ...item, fingerprint: null, delivery_status: result.status }
        : item));
    } catch (failure) {
      setSendFeedback(failure instanceof ApiHttpError
        ? failure.message
        : '寄送工作結果未確認，請先重新查詢通知狀態。');
      refresh();
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  }

  if (!notices.length && !error && !settlementOnly && !loading) return null;
  const preview = notices.find(item => item.kind === selected);
  return <section aria-label="取消結算 LINE 通知">
    <h4>LINE 通知</h4>
    {loading && <p role="status">正在查詢通知狀態…</p>}
    {error && <p role="alert">{error}</p>}
    {settlementOnly && !loading && !error && !notices.length && <p>本案沒有可通知的正式取消結算。</p>}
    {sendFeedback && <p role="alert">{sendFeedback}</p>}
    {!loading && notices.map(notice => <div key={notice.kind}>
      <button type="button" aria-expanded={selected === notice.kind} disabled={sending} onClick={() => {
        setSelected(notice.kind);
        setSendFeedback('');
      }}>{labels[notice.kind]}</button>
      {notice.delivery_status && <span role="status"> · {statuses[notice.delivery_status] ?? '寄送結果待確認'}</span>}
      {notice.unavailable_reason && <small> · {notice.unavailable_reason}</small>}
    </div>)}
    {preview && !loading && <div role="region" aria-label="LINE 通知預覽">
      <p><strong>LINE 通知預覽</strong> · {caseNo} · 本案客戶 LINE 私訊</p>
      {preview.delivery_status && <small>{preview.fingerprint
        ? '上次寄送已在投遞前取消。可確認目前內容後重新發送。'
        : '以下為目前帳務內容。上方狀態依原寄送工作顯示。'}</small>}
      {preview.text && <p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{preview.text}</p>}
      <button type="button" onClick={() => void send(preview)} disabled={sending || !preview.fingerprint}>
        {sending ? '建立寄送工作中…' : '發送 LINE 通知'}
      </button>
      {' '}
      <button type="button" disabled={sending} onClick={() => setSelected(null)}>關閉預覽</button>
      {' '}
      <a href={`#payment-reminder-settings?view=reminder-content&message=cancellation-notice-${preview.kind}`}>調整 LINE 通知範本</a>
    </div>}
    {(notices.length > 0 || error) && <button type="button" disabled={sending || loading} onClick={() => {
      setSendFeedback('');
      refresh();
    }}>重新查詢通知狀態</button>}
  </section>;
}
