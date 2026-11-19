/**
 * File: notification_tasks_client.ts
 * Description: 提供桌面與 LIFF 共用的待辦通知查詢及入帳待辦已通知標記客戶端。
 */
import { z } from 'zod';
import { transport } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';
import { LineDeliveryQueryError } from '../line_delivery/line_delivery_query_errors';
import { sessionClient } from '../auth/session_client';

export const sourceSchema = z.enum(['registration','identity','customer_binding','staff_binding','staff_profile','followup','recommendation',
  'service_start','deposit','payment_receipt','group','overdue','delivery','notification_failure','runtime']);
export type NotificationSource = z.infer<typeof sourceSchema>;
const groupSchema = z.enum(['review','reminder','support']);
const paymentSchema = z.object({case_no:z.string(),payment_stage:z.enum(['deposit','first','second']),obligation_identity:z.string(),
  projection_version:z.number().int(),obligation_event_id:z.number().int(),due_date:z.string(),remaining_amount_ntd:z.number().int()}).strict();
const logSchema = z.object({case_no:z.string(),staff_id:z.number().int(),missing_from:z.string(),missing_through:z.string()}).strict();
const itemSchema = z.object({id:z.string(),source:sourceSchema,group:groupSchema,title:z.string(),case_no:z.string().nullable(),
  reference_id:z.number().int().nullable(),person:z.string(),summary:z.string(),reason:z.string(),time:z.string(),tag:z.string(),
  recipient:z.string().nullable(),message:z.string().nullable(),unavailable_reason:z.string().nullable(),expected_version:z.number().int().nullable(),
  delivery_status:z.string().nullable(),payment:paymentSchema.nullable(),log:logSchema.nullable(),
  failure:z.object({issue_key:z.string().regex(/^ci_[0-9a-f]{64}$/),notification_reason:z.enum(['recipient_unavailable','template_or_schedule_invalid']),related_task_ids:z.array(z.number().int().positive())}).strict().nullable().optional(),
  receipt:z.object({
    payment_stage:z.enum(['deposit','first','second']),
    settlement_identity:z.string().min(1).max(128),
    amount_ntd:z.number().int().positive().optional(),
    source_version:z.number().int().positive().optional(),
    source_reference:z.string().min(1).max(128).optional(),
  }).strict().nullable().optional()}).strict();
const pageSchema = z.object({items:z.array(itemSchema),total:z.number().int().nonnegative().nullable(),next_cursor:z.union([z.number().int().nonnegative(),z.string().min(1).max(2048)]).nullable()}).strict();
const catalogSchema = z.array(z.object({source:sourceSchema,label:z.string(),group:groupSchema}).strict());
export type NotificationItem = z.infer<typeof itemSchema>;
export type NotificationPage = z.infer<typeof pageSchema>;
export type NotificationCatalog = z.infer<typeof catalogSchema>;

export function notificationOptions(signal?:AbortSignal) {
  const token = sessionClient.getToken();
  if (!token) throw new Error('請先登入。');
  return {token,signal};
}
export const NOTIFICATION_TASKS_CHANGED = 'notification-tasks-changed';
export function notifyNotificationTasksChanged() {
  window.dispatchEvent(new Event(NOTIFICATION_TASKS_CHANGED));
}
export const notificationTasksClient = {
  async dismissCustomerBinding(item:NotificationItem,reason:string,key:string) {
    if(item.source!=='customer_binding' || !item.reference_id || !item.case_no)throw new Error('提醒對象不完整，請重新整理。');
    const raw=await transport.post<{data:unknown}>('/api/v1/line/notification-task-actions/customer-binding-reminder/dismiss',{
      subject_reference:item.reference_id,case_no:item.case_no,reason,idempotency_key:key,
    },notificationOptions());
    const result=z.object({dismissed:z.literal(true),replayed:z.boolean()}).strict().parse(raw.data);
    notifyNotificationTasksChanged();
    return result;
  },
  async pendingCount(signal?:AbortSignal):Promise<number> {
    const sources = await notificationTasksClient.catalog(signal);
    const items = new Map<string,NotificationItem>();
    await Promise.all(sources.map(async ({source}) => {
      let cursor:number|string = 0;
      const visited = new Set<string>();
      while (true) {
        signal?.throwIfAborted();
        const key = `${typeof cursor}:${cursor}`;
        if (visited.has(key)) throw new Error('通知事項分頁無法確認。');
        visited.add(key);
        const page = await notificationTasksClient.list(source,cursor,signal);
        for (const item of page.items) {
          if (item.source !== source) throw new Error('通知事項來源無法確認。');
          items.set(item.id,item);
        }
        if (page.next_cursor === null) break;
        cursor = page.next_cursor;
      }
    }));
    const covered = new Set([...items.values()].flatMap(item => item.failure?.related_task_ids ?? []));
    return [...items.values()].filter(item => item.source !== 'delivery' || !covered.has(item.reference_id!)).length;
  },
  async catalog(signal?:AbortSignal) {
    const raw = await transport.get<{data:unknown}>('/api/v1/line/notification-tasks',notificationOptions(signal));
    return catalogSchema.parse(raw.data);
  },
  async list(source:NotificationSource,cursor:number|string=0,signal?:AbortSignal) {
    const raw = await transport.get<{data:unknown}>(`/api/v1/line/notification-tasks/${source}`,{
      ...notificationOptions(signal),params:{cursor}});
    return pageSchema.parse(raw.data);
  },
  async send(item:NotificationItem,key:string) {
    if(item.source==='payment_receipt') {
      if(!item.case_no || !item.receipt || item.receipt.amount_ntd == null || item.receipt.source_version == null || !item.receipt.source_reference) {
        throw new Error('請前往帳務頁面確認並標記已通知。');
      }
      const raw = await transport.post<{data:unknown}>('/api/v1/line/payment-overdue-reminders/receipts/send',{
        case_no:item.case_no,
        payment_stage:item.receipt.payment_stage,
        settlement_identity:item.receipt.settlement_identity,
        amount_ntd:item.receipt.amount_ntd,
        source_version:item.receipt.source_version,
        source_reference:item.receipt.source_reference,
      },notificationOptions());
      const result = z.object({task_id:z.number().int().positive(),status:z.string()}).strict().parse(raw.data);
      return result.task_id;
    }
    const path = item.source === 'overdue' ? '/api/v1/line/payment-overdue-reminders/send'
      : '/api/v1/line/notification-task-actions/deposit-reminder';
    const body = item.source === 'overdue' ? {...item.payment,idempotency_key:key}
      : {case_no:item.case_no,expected_version:item.expected_version,idempotency_key:key};
    const raw = await transport.post<{data:unknown}>(path,body,notificationOptions());
    const result = z.union([z.object({task_id:z.number().int().positive(),status:z.string()}).strict(),
      z.object({task_id:z.number().int().positive(),delivery_status:z.string()}).strict()]).parse(raw.data);
    return result.task_id;
  },
};
export function notificationFailure(error:unknown):string {
  if(error instanceof LineDeliveryQueryError && error.status===410 && error.code==='line_delivery_history_expired') {
    return '此寄送紀錄已超過六個月，內容與嘗試明細已清除；必要處理憑證仍保留。';
  }
  if (error instanceof ApiHttpError) {
    if(error.code==='line_binding_current_fact_incomplete')return '客戶的 LINE 綁定資料不完整，請先至身分綁定核對。';
    if(error.code==='payment_overdue_recipient_unavailable')return '尚無可用的 LINE 收件對象，請先核對身分綁定或案件群組。';
    if(error.status===401)return '登入已失效，請重新登入後再試。';
    if(error.status===403)return `${error.message} 請核對目前登入身分，或由有權限的工會人員處理。`;
    return error.message;
  }
  return '目前無法完成操作，請重新整理後再試。';
}
