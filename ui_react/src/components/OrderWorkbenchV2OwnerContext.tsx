import { useEffect, useState, type FC, type ReactNode } from 'react';
import {
  adaptOrdersCardProjection,
  type OrdersCardProjectionViewModel,
} from '../adapters/orders/order_card_projection_adapter';
import { orderCardProjectionClient } from '../api/orders/order_card_projection_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import type { FormManagementContext } from '../api/orders/order_query_schemas';
import { officialServiceDateCorrectionClient, type OfficialDateQuery } from '../api/orders/official_service_date_correction_client';
import {
  lineNotificationTimelineClient,
  type LineNotificationTimeline,
} from '../api/line/notification_timeline_client';

interface OrderWorkbenchV2OwnerContextProps {
  caseNo: string;
  revision?: number;
  placement?: 'header';
  summary?: { fields: ReactNode; actions: ReactNode };
  disabled?: boolean;
  completedService?: boolean;
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

function serviceDateRanges(dates: string[]): string {
  const ranges: string[] = [];
  let start = dates[0];
  let end = start;
  for (const day of dates.slice(1)) {
    if (Date.parse(day) - Date.parse(end!) === 86400000) end = day;
    else {
      ranges.push(start === end ? start! : `${start} ～ ${end}`);
      start = end = day;
    }
  }
  if (start) ranges.push(start === end ? start : `${start} ～ ${end}`);
  return ranges.length ? `${ranges.join('、')}（${dates.length} 天）` : '原紀錄未登錄服務日期';
}

function recordTime(value: string): string {
  return new Date(value).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei', hour12: false });
}

const EVENT_CODE_LABELS: Record<string, string> = {
  'gateway.identity_mismatch.second_attempt': '身分核對連續兩次失敗',
  'scheduling.leave.extension_requested': '月嫂請假－請客戶確認',
  'staff.retirement.committed': '月嫂辦理退休生效',
  'router.deterministic.reply_committed': 'AI 確定性指令回覆',
  'feedback.resolved.recorded': '客服回答評為已解決',
  'feedback.unresolved.recorded': '客服回答評為未解決',
  'matching.zero_pool.preview_applied': '候選池協調建議',
  'client.leave.extension_agreed': '產婦同意服務順延',
  'client.leave.extension_rejected': '產婦不同意順延需代班',
  'runtime.alert.review_required': '系統重大異常',
  'complaint.ingress.hold_high_ticket': '重大客訴告警',
  'payroll.substitute.obligation_projected': '代班出勤薪資拆帳結算',
  order_lifecycle_transition: '訂單生命週期變更',
  service_time_checkpoint: '服務時間檢查點',
  beclass_completion_changed: 'BeClass 完成狀態變更',
  deposit_confirmed: '訂金確認',
  'order.service_start_day': '服務當天群組繳款與服務狀況',
  'client.second_payment_due': '第二期款到期當天原群組提醒',
  'client.second_payment_settled': '第二期款核銷成功原群組通知',
  'fixture.created': '測試通知事件',
};

function eventCodeLabel(code: string): string {
  return EVENT_CODE_LABELS[code] ?? 'LINE 通知事件';
}

const RECIPIENT_TYPE_LABELS: Record<string, string> = {
  client: '客戶',
  staff: '月嫂',
  assigned_caregiver: '已指派月嫂',
  case_group: '案件群組',
  admin: '管理員',
  'customer_service.ticket_owner': '客服工單專員',
  'client.bound_case': '案件產婦',
  'staff.binding_owner': '綁定月嫂',
  'conversation.bound_actor': '對話使用者',
  'matching.request.participants': '媒合相關對象',
  'assignment.client_snapshot': '指派產婦',
  'assignment.staff_snapshot': '指派月嫂',
  'scheduling.owner': '排班調度負責人',
  'admin.review_actor': '工會幹部審核群',
  'customer_service.claim_owner': '客訴專責處理人',
  'staff_payables.anomaly_owner': '財務核銷專員',
};

function recipientLabel(identity?: string | null, type?: string | null): string {
  if (identity) return RECIPIENT_TYPE_LABELS[identity] ?? identity;
  if (type) return RECIPIENT_TYPE_LABELS[type] ?? type;
  return '尚無通知對象';
}

function decisionStatusLabel(status?: string | null): string {
  if (!status) return '尚無決策紀錄';
  return ({
    matched: '符合規則',
    allowed: '允許發送',
    suppressed: '不發送',
    skipped: '已略過',
    blocked: '受阻',
    pending: '待決策',
  } as Record<string, string>)[status] ?? status;
}

function intentStatusLabel(status?: string | null): string {
  if (!status) return '尚無排程紀錄';
  return ({
    scheduled: '已排程',
    pending: '待排程',
    processing: '處理中',
    sent: '已送出',
    suppressed: '已靜默略過',
    cancelled: '已取消',
    failed: '排程失敗',
    skipped: '已略過',
  } as Record<string, string>)[status] ?? status;
}

function deliveryStatusLabel(status?: string | null): string {
  if (!status) return '尚無投遞紀錄';
  return ({
    pending: '待寄送',
    processing: '寄送中',
    sent: '已送出',
    failed: '寄送失敗',
    retryable_failed: '等待重試',
    cancelled: '已取消',
    skipped: '不寄送',
  } as Record<string, string>)[status] ?? status;
}

function reasonCodeLabel(code: string): string {
  return ({
    historical_silent: '歷史靜默事件',
    recipient_unavailable: '收件對象不可用',
    template_or_schedule_invalid: '範本或排程設定無效',
    duplicate_suppressed: '重複通知已略過',
    rule_disabled: '通知規則已停用',
    predicate_not_matched: '未符合觸發條件',
  } as Record<string, string>)[code] ?? code;
}

function revealRecords(panel: HTMLDivElement | null) {
  if (!panel || !panel.previousElementSibling) return;
  const summaryBottom = panel.previousElementSibling.getBoundingClientRect().bottom;
  const panelTop = panel.getBoundingClientRect().top;
  if (panelTop < summaryBottom) window.scrollBy(0, panelTop - summaryBottom);
}

/** Reuse the same bounded, read-only owner clients as the two legacy pages. */
export const OrderWorkbenchV2OwnerContext: FC<OrderWorkbenchV2OwnerContextProps> = ({ caseNo, revision = 0, placement, summary, disabled = false, completedService = false }) => {
  const [expanded, setExpanded] = useState(false);
  const [retryRevision, setRetryRevision] = useState(0);
  const [card, setCard] = useState<ReadState<OrdersCardProjectionViewModel>>({ status: 'loading' });
  const [form, setForm] = useState<ReadState<FormManagementContext>>({ status: 'loading' });
  const [notifications, setNotifications] = useState<ReadState<LineNotificationTimeline>>({ status: 'loading' });
  const [dateHistory, setDateHistory] = useState<ReadState<OfficialDateQuery['history']>>({ status: 'loading' });

  useEffect(() => {
    if (!expanded || !completedService) return;
    const controller = new AbortController();
    setDateHistory({ status: 'loading' });
    void Promise.resolve().then(() => officialServiceDateCorrectionClient.query(caseNo, { signal: controller.signal }))
      .then((data) => {
        if (controller.signal.aborted) return;
        if (data.case_no !== caseNo) throw new Error('完工與日期更正紀錄案件識別不一致。');
        setDateHistory({ status: 'ready', data: data.history });
      })
      .catch((error) => { if (!controller.signal.aborted) setDateHistory({ status: 'error', message: errorMessage(error) }); });
    return () => controller.abort();
  }, [caseNo, completedService, expanded, retryRevision, revision]);

  useEffect(() => {
    if (!expanded) return;
    const controller = new AbortController();
    const current = () => !controller.signal.aborted;
    setCard({ status: 'loading' });
    setNotifications({ status: 'loading' });

    void Promise.resolve().then(() => orderCardProjectionClient.getCardProjection(caseNo, { signal: controller.signal }))
      .then((data) => {
        if (current()) setCard({ status: 'ready', data: adaptOrdersCardProjection(data, caseNo) });
      })
      .catch((error) => { if (current()) setCard({ status: 'error', message: errorMessage(error) }); });
    void Promise.resolve().then(() => lineNotificationTimelineClient.query(caseNo, { signal: controller.signal }))
      .then((data) => { if (current()) setNotifications({ status: 'ready', data }); })
      .catch((error) => { if (current()) setNotifications({ status: 'error', message: errorMessage(error) }); });

    return () => controller.abort();
  }, [caseNo, expanded, retryRevision, revision]);

  useEffect(() => {
    if (!expanded) return;
    const controller = new AbortController();
    const current = () => !controller.signal.aborted;
    setForm({ status: 'loading' });
    void Promise.resolve().then(() => ordersQueryClient.getFormManagementContext(caseNo, { signal: controller.signal }))
      .then((data) => {
        if (!current()) return;
        if (data.case_no !== caseNo) throw new Error('客戶服務資料案件識別不一致。');
        setForm({ status: 'ready', data });
      })
      .catch((error) => { if (current()) setForm({ status: 'error', message: errorMessage(error) }); });
    return () => controller.abort();
  }, [caseNo, expanded, retryRevision, revision]);

  const inHeader = placement === 'header' || summary !== undefined;
  const recordsToggle = inHeader ? (
    <button type="button" className="order-case-records-toggle" disabled={disabled} aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
      {expanded ? '收起相關資料與通知紀錄' : '查看相關資料與通知紀錄'}
    </button>
  ) : (
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
  );

  return (
    <section className={inHeader ? 'order-case-owner-context-header' : 'order-v2-drawer-section order-case-owner-context'} aria-label="案件聯絡、服務資料與 LINE 歷程">
      {!inHeader && <h3>案件聯絡、服務資料與 LINE 歷程</h3>}
      {summary ? (
        <div className="order-case-summary-row" role="region" aria-label="案件摘要">
          <div className="order-case-context">{summary.fields}</div>
          <div className="order-case-summary-actions">
            {recordsToggle}
            {summary.actions}
          </div>
        </div>
      ) : recordsToggle}
      {expanded && (
        <div ref={summary ? revealRecords : undefined} className={inHeader ? 'order-case-related-records order-v2-drawer-section' : 'order-case-related-records'}>
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
            {completedService && dateHistory.status === 'loading' && <p role="status">載入原完工與日期更正紀錄…</p>}
            {completedService && dateHistory.status === 'error' && <p role="alert">原完工與日期更正紀錄不可用：{dateHistory.message} 請收起後重新開啟此入口重試。</p>}
            <dl className="order-v2-business-summary">
              {form.status === 'ready' && <>
                <div><dt>服務時間</dt><dd>{form.data.service_time ?? '未登錄'}</dd></div>
                <div><dt>服務類型</dt><dd>{form.data.service_type ?? '未登錄'}</dd></div>
                <div><dt>生產方式</dt><dd>{form.data.delivery_type ?? '未登錄'}</dd></div>
                <div><dt>住宅類型</dt><dd>{form.data.residence_type ?? '未登錄'}</dd></div>
                <div><dt>服務縣市</dt><dd>{form.data.city ?? '未登錄'}</dd></div>
                <div><dt>身分類別</dt><dd>{form.data.identity_status ?? '未登錄'}</dd></div>
              </>}
              {completedService && dateHistory.status === 'ready' && dateHistory.data.length === 0 && <div><dt>原完工與日期更正紀錄</dt><dd>尚無可查閱紀錄</dd></div>}
              {completedService && dateHistory.status === 'ready' && dateHistory.data.map((record) => (
                <div key={record.event_id}>
                  <dt>{record.event_type === 'original_completion' ? '原完工紀錄' : '日期更正紀錄'} #{record.event_id}</dt>
                  <dd>
                    記錄時間：{recordTime(record.recorded_at)}；操作人：{record.actor}
                    <br />
                    {record.event_type === 'original_completion' ? <>
                      {record.completion_instant && <>原服務完成時刻：{recordTime(record.completion_instant)}<br /></>}
                      原服務日期：{serviceDateRanges(record.after_dates)}
                    </> : <>
                      移除日期：{record.before_dates.filter((day) => !record.after_dates.includes(day)).join('、') || '無'}；補入日期：{record.after_dates.filter((day) => !record.before_dates.includes(day)).join('、') || '無'}
                      <br />更正原因：{record.reason ?? '原紀錄未登錄原因'}
                    </>}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
          <section aria-label="LINE 通知唯讀歷程">
            <h4>LINE 通知歷程</h4>
            {notifications.status === 'loading' && <p role="status">載入 LINE 通知歷程…</p>}
            {notifications.status === 'error' && <p role="alert">LINE 通知歷程不可用：{notifications.message}</p>}
            {notifications.status === 'ready' && notifications.data.records.length === 0 && <p>尚無 LINE 通知事件。</p>}
            {notifications.status === 'ready' && notifications.data.records.map((record, index) => (
              <article key={`${record.source_event_id}:${record.rule_id ?? 'none'}:${record.occurrence_number ?? 0}:${index}`}>
                <strong>{eventCodeLabel(record.event_code)}</strong>
                <dl>
                  <div><dt>事件時間</dt><dd>{record.occurred_at_utc ?? '尚無事件時間'}</dd></div>
                  <div><dt>通知對象</dt><dd>{recipientLabel(record.recipient_identity, record.recipient_type)}</dd></div>
                  <div><dt>規則決策</dt><dd>{decisionStatusLabel(record.decision_status)}</dd></div>
                  <div><dt>通知排程</dt><dd>{intentStatusLabel(record.intent_status)}</dd></div>
                  <div><dt>投遞狀態</dt><dd>{deliveryStatusLabel(record.delivery_status)}</dd></div>
                  {record.reason_code && <div><dt>原因</dt><dd>{reasonCodeLabel(record.reason_code)}</dd></div>}
                </dl>
                {record.historical_silent && <p>歷史靜默事件；不補發通知。</p>}
              </article>
            ))}
          </section>
        </div>
      )}
    </section>
  );
};
