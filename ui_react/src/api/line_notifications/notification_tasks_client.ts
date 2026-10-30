/** The desktop and LIFF read the same owner-backed source pages. */
import { z } from 'zod';
import { transport } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';
import { sessionClient } from '../auth/session_client';

export const sourceSchema = z.enum(['registration','identity','customer_binding','staff_binding','profile','information','followup','recommendation',
  'service_start','deposit','group','overdue','log','customer_service','delivery','notification_failure','runtime']);
export type NotificationSource = z.infer<typeof sourceSchema>;
const groupSchema = z.enum(['review','reminder','support']);
const paymentSchema = z.object({case_no:z.string(),payment_stage:z.enum(['deposit','first','second']),obligation_identity:z.string(),
  projection_version:z.number().int(),obligation_event_id:z.number().int(),due_date:z.string(),remaining_amount_ntd:z.number().int()}).strict();
const logSchema = z.object({case_no:z.string(),staff_id:z.number().int(),missing_from:z.string(),missing_through:z.string()}).strict();
export const informationSchema = z.object({question_id:z.number().int(),pool_id:z.number().int(),request_kind:z.enum(['information_question','condition_adjustment']),
  customer_answer_event_id:z.number().int().nullable(),review_completed:z.boolean(),case_no:z.string(),staff_name:z.string(),
  issues:z.array(z.object({label:z.string(),detail:z.string()}).strict()),customer_answer:z.string().nullable(),customer_message:z.string().nullable(),
  customer_available:z.boolean()}).strict();
const itemSchema = z.object({id:z.string(),source:sourceSchema,group:groupSchema,title:z.string(),case_no:z.string().nullable(),
  reference_id:z.number().int().nullable(),person:z.string(),summary:z.string(),reason:z.string(),time:z.string(),tag:z.string(),
  recipient:z.string().nullable(),message:z.string().nullable(),unavailable_reason:z.string().nullable(),expected_version:z.number().int().nullable(),
  delivery_status:z.string().nullable(),payment:paymentSchema.nullable(),log:logSchema.nullable(),information:informationSchema.nullable(),
  failure:z.object({issue_key:z.string().regex(/^ci_[0-9a-f]{64}$/),notification_reason:z.enum(['recipient_unavailable','template_or_schedule_invalid']),related_task_ids:z.array(z.number().int().positive())}).strict().nullable().optional()}).strict();
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
export const notificationTasksClient = {
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
    const path = item.source === 'overdue' ? '/api/v1/line/payment-overdue-reminders/send'
      : item.source === 'log' ? '/api/v1/line/order-groups/log-reminders/send'
      : '/api/v1/line/notification-task-actions/deposit-reminder';
    const body = item.source === 'overdue' ? {...item.payment,idempotency_key:key}
      : item.source === 'log' ? {...item.log,idempotency_key:key}
      : {case_no:item.case_no,expected_version:item.expected_version,idempotency_key:key};
    const raw = await transport.post<{data:unknown}>(path,body,notificationOptions());
    const result = z.union([z.object({task_id:z.number().int().positive(),status:z.string()}).strict(),
      z.object({task_id:z.number().int().positive(),delivery_status:z.string()}).strict()]).parse(raw.data);
    return result.task_id;
  },
};
export function notificationFailure(error:unknown):string {
  if (error instanceof ApiHttpError) {
    if(error.code==='line_binding_current_fact_incomplete')return '客戶的 LINE 綁定資料不完整，請先至身分綁定核對。';
    if(error.code==='payment_overdue_recipient_unavailable')return '尚無可用的 LINE 收件對象，請先核對身分綁定或案件群組。';
    if(error.status===401)return '登入已失效，請重新登入後再試。';
    if(error.status===403)return `${error.message} 請核對目前登入身分，或由有權限的工會人員處理。`;
    return error.message;
  }
  return '目前無法完成操作，請重新整理後再試。';
}
