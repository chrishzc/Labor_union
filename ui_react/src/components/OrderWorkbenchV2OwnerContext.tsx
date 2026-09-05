import { useEffect, useState, type FC } from 'react';
import {
  adaptOrdersCardProjection,
  type OrdersCardProjectionViewModel,
} from '../adapters/orders/order_card_projection_adapter';
import { orderCardProjectionClient } from '../api/orders/order_card_projection_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import type { FormManagementContext } from '../api/orders/order_query_schemas';
import {
  lineNotificationTimelineClient,
  type LineNotificationTimeline,
} from '../api/line/notification_timeline_client';

interface OrderWorkbenchV2OwnerContextProps {
  caseNo: string;
  revision?: number;
}

type ReadState<T> =
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; message: string };

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '正式資料查詢失敗';
}

/** Reuse the same bounded, read-only owner clients as the two legacy pages. */
export const OrderWorkbenchV2OwnerContext: FC<OrderWorkbenchV2OwnerContextProps> = ({ caseNo, revision = 0 }) => {
  const [expanded, setExpanded] = useState(false);
  const [retryRevision, setRetryRevision] = useState(0);
  const [card, setCard] = useState<ReadState<OrdersCardProjectionViewModel>>({ status: 'loading' });
  const [form, setForm] = useState<ReadState<FormManagementContext>>({ status: 'loading' });
  const [notifications, setNotifications] = useState<ReadState<LineNotificationTimeline>>({ status: 'loading' });

  useEffect(() => {
    if (!expanded) return;
    const controller = new AbortController();
    const current = () => !controller.signal.aborted;
    setCard({ status: 'loading' });
    setForm({ status: 'loading' });
    setNotifications({ status: 'loading' });

    void orderCardProjectionClient.getCardProjection(caseNo, { signal: controller.signal })
      .then((data) => {
        if (current()) setCard({ status: 'ready', data: adaptOrdersCardProjection(data, caseNo) });
      })
      .catch((error) => { if (current()) setCard({ status: 'error', message: errorMessage(error) }); });
    void ordersQueryClient.getFormManagementContext(caseNo, { signal: controller.signal })
      .then((data) => {
        if (!current()) return;
        if (data.case_no !== caseNo) throw new Error('客戶服務資料案件識別不一致。');
        setForm({ status: 'ready', data });
      })
      .catch((error) => { if (current()) setForm({ status: 'error', message: errorMessage(error) }); });
    void lineNotificationTimelineClient.query(caseNo, { signal: controller.signal })
      .then((data) => { if (current()) setNotifications({ status: 'ready', data }); })
      .catch((error) => { if (current()) setNotifications({ status: 'error', message: errorMessage(error) }); });

    return () => controller.abort();
  }, [caseNo, expanded, retryRevision, revision]);

  return (
    <section className="order-v2-drawer-section" aria-label="案件聯絡、服務資料與 LINE 歷程">
      <h3>案件聯絡、服務資料與 LINE 歷程</h3>
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => {
          if (expanded) setRetryRevision((value) => value + 1);
          else setExpanded(true);
        }}
      >
        {expanded ? '重新讀取案件聯絡、服務資料與 LINE 歷程' : '讀取案件聯絡、服務資料與 LINE 歷程'}
      </button>
      {expanded && (
        <>
          <section aria-label="正式案件聯絡與帳務投影">
            <h4>案件聯絡與帳務資料</h4>
            {card.status === 'loading' && <p role="status">載入案件聯絡與帳務資料…</p>}
            {card.status === 'error' && <p role="alert">案件聯絡與帳務資料不可用：{card.message}</p>}
            {card.status === 'ready' && (
              <dl className="order-v2-business-summary">
                {card.data.rows.map((row) => (
                  <div key={row.key}>
                    <dt>{row.label}</dt>
                    <dd>{row.valueText}</dd>
                  </div>
                ))}
              </dl>
            )}
          </section>
          <section aria-label="正式客戶服務資料">
            <h4>客戶服務資料</h4>
            {form.status === 'loading' && <p role="status">載入客戶服務資料…</p>}
            {form.status === 'error' && <p role="alert">客戶服務資料不可用：{form.message}</p>}
            {form.status === 'ready' && (
              <dl className="order-v2-business-summary">
                <div><dt>服務時間</dt><dd>{form.data.service_time ?? '未登錄'}</dd></div>
                <div><dt>服務類型</dt><dd>{form.data.service_type ?? '未登錄'}</dd></div>
                <div><dt>生產方式</dt><dd>{form.data.delivery_type ?? '未登錄'}</dd></div>
                <div><dt>住宅類型</dt><dd>{form.data.residence_type ?? '未登錄'}</dd></div>
                <div><dt>服務縣市</dt><dd>{form.data.city ?? '未登錄'}</dd></div>
                <div><dt>身分類別</dt><dd>{form.data.identity_status ?? '未登錄'}</dd></div>
              </dl>
            )}
          </section>
          <section aria-label="LINE 通知唯讀歷程">
            <h4>LINE 通知歷程</h4>
            {notifications.status === 'loading' && <p role="status">載入 LINE 通知歷程…</p>}
            {notifications.status === 'error' && <p role="alert">LINE 通知歷程不可用：{notifications.message}</p>}
            {notifications.status === 'ready' && notifications.data.records.length === 0 && <p>尚無 LINE 通知事件。</p>}
            {notifications.status === 'ready' && notifications.data.records.map((record, index) => (
              <article key={`${record.source_event_id}:${record.rule_id ?? 'none'}:${record.occurrence_number ?? 0}:${index}`}>
                <strong>{record.event_code}</strong>
                <dl>
                  <div><dt>事件時間</dt><dd>{record.occurred_at_utc ?? '尚無事件時間'}</dd></div>
                  <div><dt>通知對象</dt><dd>{record.recipient_identity ?? record.recipient_type ?? '尚無通知對象'}</dd></div>
                  <div><dt>規則決策</dt><dd>{record.decision_status ?? '尚無決策紀錄'}</dd></div>
                  <div><dt>通知排程</dt><dd>{record.intent_status ?? '尚無排程紀錄'}</dd></div>
                  <div><dt>投遞狀態</dt><dd>{record.delivery_status ?? '尚無投遞紀錄'}</dd></div>
                  {record.reason_code && <div><dt>原因</dt><dd>{record.reason_code}</dd></div>}
                </dl>
                {record.historical_silent && <p>歷史靜默事件；不補發通知。</p>}
              </article>
            ))}
          </section>
        </>
      )}
    </section>
  );
};
