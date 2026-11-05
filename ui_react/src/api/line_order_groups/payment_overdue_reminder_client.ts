/** Stage-local overdue facts; recipient selection is server-owned. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';

const payment = z.object({case_no:z.string(),payment_stage:z.enum(['deposit','first','second']),
  obligation_identity:z.string(),projection_version:z.number().int().nonnegative(),obligation_event_id:z.number().int().positive(),
  due_date:z.string(),remaining_amount_ntd:z.number().int().positive()}).strict();
const item = z.object({payment,overdue_days:z.number().int().positive(),recipient_label:z.string(),can_send:z.boolean(),
  unavailable_reason:z.string().nullable(),last_reminder:z.object({requested_at:z.string(),status:z.string()}).strict().nullable()}).strict();
const page = z.object({items:z.array(item),total:z.number().int().nonnegative(),page:z.number().int().positive(),page_size:z.number().int().positive()}).strict();
const receipt = z.object({task_id:z.number().int().positive(),status:z.string()}).strict();
const noticeHistory=z.strictObject({task_id:z.number().int().positive(),requested_at:z.string(),sent_at:z.string().nullable(),status:z.string(),content:z.string().nullable(),actor:z.string().nullable()});
const caseNotice=z.strictObject({case_no:z.string(),payment_stage:z.enum(['deposit','first','second']),payment:payment.extend({remaining_amount_ntd:z.number().int().nonnegative()}).nullable(),recipient_label:z.string(),can_send:z.boolean(),unavailable_reason:z.string().nullable(),message:z.string().nullable(),history:z.array(noticeHistory)});
export type CasePaymentReminder=z.infer<typeof caseNotice>;
export type PaymentOverdueTodo = z.infer<typeof item>;
export type PaymentOverduePage = z.infer<typeof page>;
export interface CasePaymentReminderClient {
  case(caseNo:string,signal?:AbortSignal):Promise<CasePaymentReminder[]>;
  sendCase(item:CasePaymentReminder,key:string):Promise<z.infer<typeof receipt>>;
}
export interface PaymentOverdueReminderClient {
  list(page:number,signal?:AbortSignal):Promise<PaymentOverduePage>;
  send(item:PaymentOverdueTodo,key:string):Promise<z.infer<typeof receipt>>;
}
function options() {
  const token=sessionClient.getToken();
  if (!token) throw new Error('請先登入。');
  return {token};
}
export const paymentOverdueReminderClient:PaymentOverdueReminderClient & CasePaymentReminderClient = {
  async case(caseNo,signal){const raw=await transport.get<{data:unknown}>(`/api/v1/line/payment-overdue-reminders/cases/${encodeURIComponent(caseNo)}`,{...options(),signal});const rows=z.array(caseNotice).parse(raw.data);if(rows.some(row=>row.case_no!==caseNo||row.payment&&row.payment.case_no!==caseNo)||new Set(rows.map(row=>row.payment_stage)).size!==rows.length)throw new Error('通知來源案件或期別不一致');return rows;},
  async sendCase(value,key){if(!value.payment)throw new Error('本期期款來源待確認');const raw=await transport.post<{data:unknown}>('/api/v1/line/payment-overdue-reminders/cases/send',{...value.payment,idempotency_key:key},options());return receipt.parse(raw.data);},

  async list(number,signal) {
    const raw=await transport.get<{data:unknown}>('/api/v1/line/payment-overdue-reminders',{
      ...options(),signal,params:{page:number,page_size:25}});
    return page.parse(raw.data);
  },
  async send(value,key) {
    const raw=await transport.post<{data:unknown}>('/api/v1/line/payment-overdue-reminders/send',{
      ...value.payment,idempotency_key:key},options());
    return receipt.parse(raw.data);
  },
};
