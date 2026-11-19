import { useRef, useState } from 'react';
import { z } from 'zod';
import { lineDeliveryQueryClient } from '../api/line_delivery/line_delivery_query_client';
import { notificationFailure, notificationOptions } from '../api/line_notifications/notification_tasks_client';
import { transport } from '../api/shared/transport';
import { ApiHttpError } from '../api/shared/typed_errors';
import { useUnsavedDraft } from './UnsavedChanges';

const previewSchema = z.strictObject({
  issue_key: z.string().regex(/^ci_[0-9a-f]{64}$/), case_no: z.string(), notification_reason: z.string(),
  owner_snapshot_token: z.string().min(1), preview_fingerprint: z.string().min(1),
  source_event_ids: z.array(z.number().int().positive()),
  tasks: z.array(z.strictObject({ task_id: z.number().int().positive(), status: z.string() })),
});
const targetSchema = z.discriminatedUnion('kind', [
  z.strictObject({ kind: z.literal('delivery_task'), id: z.number().int().positive(), scope: z.string() }),
  z.strictObject({ kind: z.literal('notification_failure'), id: z.string().regex(/^ci_[0-9a-f]{64}$/), scope: z.string(), preview: previewSchema }),
]);
const commandSchema = z.strictObject({
  target: targetSchema, key: z.string().uuid(), reason: z.string().min(1),
  outcome: z.enum(['unknown', 'success', 'conflict', 'failed']), receipt: z.string(),
});
const batchSchema = z.strictObject({ origin: z.string(), commands: z.array(commandSchema).min(1) })
  .refine(batch => batch.commands.every(command => command.target.kind !== 'notification_failure' || command.target.id === command.target.preview.issue_key))
  .refine(batch => new Set(batch.commands.map(command => targetKey(command.target))).size === batch.commands.length);
type Target = z.infer<typeof targetSchema>;
type Batch = z.infer<typeof batchSchema>;
const storageKey = 'line-notification-closure-batch:v1';
const statusLabel = (status: string) => ({ pending: '待寄送', processing: '寄送中', failed: '寄送失敗', retryable_failed: '等待重試', cancelled: '已取消', sent: '已送出' })[status] ?? '待核對';
const sourceLabel = (source: string) => ({ finance: '帳務通知', identity: '身分通知', identity_review: '身分審核', contract: '契約通知', order: '訂單通知', assignment: '排班通知', general_push: '一般通知', matching: '媒合通知', customer_service: '客服通知', group_invitation: '群組邀請', follow_schedule: '追蹤通知', system: '系統通知', webhook_reply: '訊息回覆', rich_menu: '選單設定', rich_menu_link: '選單綁定', rich_menu_unlink: '選單解除' })[source] ?? 'LINE 通知';
const reasonLabel = (reason: string) => reason === 'recipient_unavailable' ? '收件對象待確認' : '通知設定待確認';
const targetKey = (target: Target) => `${target.kind}:${target.id}`;
const displayScope = (target: Target) => target.kind === 'notification_failure'
  ? `案件 ${target.preview.case_no} · ${reasonLabel(target.preview.notification_reason)}。結清本通知及相關寄送工作：${target.preview.tasks.map(task => `#${task.task_id} ${statusLabel(task.status)}`).join('、') || '尚未建立寄送工作'}`
  : target.scope.replace(/來源 ([a-z_]+)/g, (_, source: string) => sourceLabel(source)).replace(/狀態 ([a-z_]+)/g, (_, status: string) => statusLabel(status));
const displayReceipt = (command: z.infer<typeof commandSchema>) => command.outcome === 'success'
  ? command.target.kind === 'delivery_task' ? `寄送工作 #${command.target.id} 已取消` : '原通知及相關工作已結清'
  : command.receipt || '尚未確認結果';


function restore(): { batch: Batch | null; error: string } {
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return { batch: null, error: '' };
    const batch = batchSchema.parse(JSON.parse(raw));
    if (batch.origin !== window.location.origin) throw new Error('origin mismatch');
    return { batch, error: '' };
  } catch {
    return { batch: null, error: '無法驗證前次批次紀錄，已停止建立新命令。請交由管理員核對原操作結果。' };
  }
}

export function LineNotificationClosureBatch({ onCommitted }: { onCommitted: () => Promise<void> }) {
  const [restored] = useState(restore);
  const [batch, setBatch] = useState(restored.batch);
  const [targets, setTargets] = useState<Target[]>([]);
  const [blocked, setBlocked] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [reason, setReason] = useState('');
  const [error, setError] = useState(restored.error);
  const [busy, setBusy] = useState(false);
  const [pages, setPages] = useState({ failed: 1, retryable_failed: 1 });
  const [more, setMore] = useState({ failed: true, retryable_failed: true });
  const lock = useRef(false);
  const unresolved=batch?.commands.filter(command=>command.outcome!=='success').length ?? 0;
  useUnsavedDraft('批次結清', { reason, selected, unresolved }, { busy, enabled:batch===null || unresolved>0 });
  const persist = (next: Batch) => {
    sessionStorage.setItem(storageKey, JSON.stringify(next));
    setBatch(next);
  };
  const load = async () => {
    if (lock.current || batch || restored.error) return;
    lock.current = true; setBusy(true); setError('');
    try {
      const additions: Target[] = [];
      const unavailable: string[] = [];
      const nextPages = { ...pages }, nextMore = { ...more };
      const statuses = ['failed', 'retryable_failed'] satisfies Array<'failed' | 'retryable_failed'>;
      for (const status of statuses) {
        if (!more[status]) continue;
        const page = await lineDeliveryQueryClient.list({ status, page: pages[status], pageSize: 25 });
        for (const item of page.items) {
          const detail = await lineDeliveryQueryClient.detail(item.task_id);
          const handling = detail.handling;
          if (!handling.allowed_actions.some(action => action === 'close' || action === 'cancel')) {
            unavailable.push(`工作 #${item.task_id}：${handling.blocked_reason ?? '目前不允許結清，需重新核對。'}`);
            continue;
          }
          if (handling.target_kind === 'notification_failure') {
            if (!handling.allowed_actions.includes('close') || !/^ci_[0-9a-f]{64}$/.test(handling.target_identity)) {
              unavailable.push(`工作 #${item.task_id}：原通知結清範圍無法確認。`); continue;
            }
            if ([...targets, ...additions].some(target => targetKey(target) === `notification_failure:${handling.target_identity}`)) continue;
            const raw = await transport.post<{ data: unknown }>(`/api/v1/line/notification-rules/failures/${handling.target_identity}/skip/preview`, {}, notificationOptions());
            const preview = previewSchema.parse(raw.data);
            if (preview.issue_key !== handling.target_identity) throw new Error('scope mismatch');
            additions.push({ kind: 'notification_failure', id: preview.issue_key, preview,
              scope: `案件 ${preview.case_no} · ${reasonLabel(preview.notification_reason)}。結清本通知及相關寄送工作：${preview.tasks.map(task => `#${task.task_id} ${statusLabel(task.status)}`).join('、') || '尚未建立寄送工作'}` });
          } else {
            if (handling.target_identity !== String(item.task_id)) { unavailable.push(`工作 #${item.task_id}：目標識別不符。`); continue; }
            additions.push({ kind: 'delivery_task', id: item.task_id,
              scope: `僅寄送工作 #${item.task_id} · ${sourceLabel(detail.task.source_type)} · ${statusLabel(detail.task.status)}` });
          }
        }
        nextPages[status] = pages[status] + 1;
        nextMore[status] = page.page < page.total_pages;
      }
      setTargets(previous => Array.from(new Map([...previous, ...additions].map(target => [targetKey(target), target])).values()));
      setBlocked(previous => [...new Set([...previous, ...unavailable])]);
      setPages(nextPages); setMore(nextMore);
    } catch (failure) { setError(`候選載入失敗，未套用任何結清。${notificationFailure(failure)}`); }
    finally { lock.current = false; setBusy(false); }
  };
  const apply = async () => {
    if (lock.current || restored.error) return;
    let current = batch;
    if (!current) {
      const chosen = targets.filter(target => selected.includes(targetKey(target)));
      if (!reason.trim() || !chosen.length) return;
      current = { origin: window.location.origin, commands: chosen.map(target => ({ target, key: crypto.randomUUID(), reason: reason.trim(), outcome: 'unknown', receipt: '' })) };
    }
    lock.current = true; setBusy(true); setError('');
    try {
      persist(current);
      for (let index = 0; index < current.commands.length; index++) {
        const command = current.commands[index];
        if (command.outcome === 'success') continue;
        let outcome: z.infer<typeof commandSchema>['outcome'] = 'unknown';
        let receipt = '';
        try {
          const target = command.target;
          if (target.kind === 'delivery_task') {
            const raw = await transport.post<{ data: unknown }>(`/api/v1/line/tasks/${target.id}/cancel`, {
              reason: command.reason, idempotency_key: command.key, correlation_id: command.key,
            }, notificationOptions());
            const result = z.object({ task_id: z.number().int().positive(), status: z.literal('cancelled') }).parse(raw.data);
            if (result.task_id !== target.id) throw new Error('receipt mismatch');
            receipt = `寄送工作 #${result.task_id} 已取消`;
          } else {
            const raw = await transport.post<{ data: unknown }>(`/api/v1/line/notification-rules/failures/${target.id}/skip/apply`, {
              reason: command.reason, idempotency_key: command.key,
              owner_snapshot_token: target.preview.owner_snapshot_token, preview_fingerprint: target.preview.preview_fingerprint,
            }, notificationOptions());
            const result = z.strictObject({ issue_key: z.string(), replayed: z.boolean() }).parse(raw.data);
            if (result.issue_key !== target.id) throw new Error('receipt mismatch');
            receipt = result.replayed ? '已讀回原結清紀錄' : '原通知及相關工作已結清';
          }
          outcome = 'success';
        } catch (failure) {
          outcome = failure instanceof ApiHttpError ? failure.status === 409 ? 'conflict' : failure.status < 500 ? 'failed' : 'unknown' : 'unknown';
          receipt = `${outcome === 'unknown' ? '結果未知，重送沿用原命令。' : ''}${notificationFailure(failure)}`;
        }
        current = { ...current, commands: current.commands.map((item, position) => position === index ? { ...item, outcome, receipt } : item) };
        persist(current);
      }
      if (current.commands.some(command => command.outcome === 'success')) {
        try { await onCommitted(); } catch { setError('結清收據已保留，寄送清單更新失敗。'); }
      }
    } catch { setError('批次紀錄無法儲存，已停止後續操作。請先核對已顯示的收據。'); }
    finally { lock.current = false; setBusy(false); }
  };
  const complete = batch !== null && batch.commands.every(command => command.outcome === 'success');
  return <section className="notification-closure-batch" aria-label="批次結清通知">
    <h3>批次不再寄送／結清</h3>
    <p>勾選不需再寄送的事項，填寫原因後結清。歷史紀錄會保留。</p>
    {error && <p role="alert">{error}</p>}
    {!batch && <>
      <button className="np-button" disabled={busy || !!restored.error || (!more.failed && !more.retryable_failed)} onClick={() => void load()}>{targets.length || blocked.length ? '載入更多候選' : '載入結清候選'}</button>
      {targets.map(target => <label key={targetKey(target)} className="notification-closure-choice">
        <input type="checkbox" checked={selected.includes(targetKey(target))} disabled={busy} onChange={event => setSelected(previous => event.target.checked ? [...previous, targetKey(target)] : previous.filter(key => key !== targetKey(target)))} />
        {displayScope(target)}
      </label>)}
      {blocked.length > 0 && <details className="notification-closure-blocked"><summary>{blocked.length} 項暫時無法結清</summary>{blocked.map(message => <p key={message}>{message}</p>)}</details>}
      <label className="notification-closure-reason">批次共同結清原因<textarea rows={2} placeholder="例如：已人工通知，不需再寄送" value={reason} disabled={busy} onChange={event => setReason(event.target.value)} /></label>
      <p>已選 {selected.length} 項，僅結清勾選範圍。每項結果會分別顯示。</p>
      <button className="np-button primary" disabled={busy || !!restored.error || !selected.length || !reason.trim()} onClick={() => void apply()}>確認批次結清</button>
    </>}
    {batch && <>
      <p>結清原因：{batch.commands[0]?.reason}</p>
      <ul>{batch.commands.map(command => <li key={targetKey(command.target)}>
        {displayScope(command.target)}，{({ unknown: '結果未知', success: '成功', conflict: '衝突', failed: '失敗' })[command.outcome]}。
        {displayReceipt(command)}。
      </li>)}</ul>
      {!complete && <button className="np-button" disabled={busy} onClick={() => void apply()}>僅重送未成功項目</button>}
      {complete && <button className="np-button" disabled={busy} onClick={() => { sessionStorage.removeItem(storageKey); setBatch(null); setTargets([]); setSelected([]); setBlocked([]); setReason(''); setPages({ failed: 1, retryable_failed: 1 }); setMore({ failed: true, retryable_failed: true }); }}>建立下一批</button>}
    </>}
    {busy && <p role="status">正在處理批次，請稍候…</p>}
  </section>;
}
