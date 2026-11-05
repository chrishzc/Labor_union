/**
 * File: ServiceDayLogReminderWorkbench.tsx
 * Description: 服務日誌缺漏提醒：依案件群組彙整缺漏，由工會於群組明細逐筆決定是否發送。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { serviceDayLogReminderClient, type ServiceDayLogReminderClient,
  type ServiceDayLogReminder } from '../api/line_order_groups/service_day_log_reminder_client';

const MAX_REMINDER_PAGES = 8;

export interface ServiceDayLogReminderIndex {
  byCase: Record<string, ServiceDayLogReminder[]>;
  error: string;
  reload(): void;
}

/** 讀取全部缺漏提醒並依案件編號分組；讀取本身不建立任何寄送工作。 */
export function useServiceDayLogReminders(client: ServiceDayLogReminderClient = serviceDayLogReminderClient): ServiceDayLogReminderIndex {
  const [byCase, setByCase] = useState<Record<string, ServiceDayLogReminder[]>>({});
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setError('');
    (async () => {
      const grouped: Record<string, ServiceDayLogReminder[]> = {};
      for (let page = 1; page <= MAX_REMINDER_PAGES; page += 1) {
        const value = await client.list(page);
        value.items.forEach(item => { (grouped[item.case_no] ??= []).push(item); });
        if (page * value.page_size >= value.total) break;
      }
      if (active) setByCase(grouped);
    })().catch(() => { if (active) { setByCase({}); setError('日誌提醒讀取失敗，請重新整理。'); } });
    return () => { active = false; };
  }, [client, revision]);
  const reload = useCallback(() => setRevision(value => value + 1), []);
  return { byCase, error, reload };
}

function identity(item: ServiceDayLogReminder) {
  return `${item.case_no}:${item.staff_id}:${item.missing_from}:${item.missing_through}`;
}

/** 單一案件群組的日誌缺漏；連續超過 3 日未填才列出，由工會決定是否提醒案件群組。 */
export function ServiceDayLogCaseReminders({ items, client = serviceDayLogReminderClient, onRefresh }: {
  items: readonly ServiceDayLogReminder[];
  client?: ServiceDayLogReminderClient;
  onRefresh?: () => void;
}) {
  const [pending, setPending] = useState<string | null>(null);
  const [queued, setQueued] = useState<Record<string, boolean>>({});
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const keys = useRef(new Map<string, string>());
  async function send(item: ServiceDayLogReminder) {
    if (pending) return;
    const id = identity(item);
    if (!keys.current.has(id)) keys.current.set(id, crypto.randomUUID());
    setPending(id); setError(''); setMessage('');
    try {
      const result = await client.send(item, keys.current.get(id)!);
      setQueued(value => ({ ...value, [id]: true }));
      setMessage(result.status === 'cancelled' ? '提醒工作已取消，請重新整理缺漏紀錄。' : '已建立案件群組提醒寄送工作。');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '提醒建立失敗，請稍後以原操作重試。');
    } finally { setPending(null); }
  }
  return <section className="order-group-log-reminders" aria-label="服務日誌提醒">
    <h3>服務日誌提醒</h3>
    <p>連續超過 3 日未填才列出，由工會決定是否提醒案件群組。</p>
    {items.length === 0 ? <p>目前沒有連續超過 3 日未填的服務日誌。</p> : <ul>
      {items.map(item => <li key={identity(item)}>
        <span>連續 {item.consecutive_days} 日</span>
        <button type="button" className="order-group-button" disabled={!item.can_send || !!pending || queued[identity(item)]}
          onClick={() => void send(item)}>{queued[identity(item)] ? '已建立寄送工作' : pending === identity(item) ? '建立中…' : '發送提醒'}</button>
        {!item.can_send && <span>尚無可用案件群組</span>}
      </li>)}
    </ul>}
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {onRefresh && <button type="button" className="order-group-button" disabled={!!pending} onClick={onRefresh}>重新整理日誌提醒</button>}
  </section>;
}
