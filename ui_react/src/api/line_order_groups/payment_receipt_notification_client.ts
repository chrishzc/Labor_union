import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
const payment=z.strictObject({case_no:z.string(),payment_stage:z.enum(['deposit','second']),settlement_identity:z.string(),amount_ntd:z.number().int().positive(),source_version:z.number().int().nonnegative(),source_reference:z.string()});
const item=z.strictObject({payment,can_send:z.boolean(),unavailable_reason:z.string().nullable(),delivery_status:z.string().nullable()});
const page=z.strictObject({items:z.array(item),total:z.number().int().nonnegative(),page:z.number().int().positive(),page_size:z.number().int().positive()});
const result=z.strictObject({task_id:z.number().int().positive(),status:z.string()});
export type PaymentReceiptTodo=z.infer<typeof item>;
export type PaymentReceiptPage=z.infer<typeof page>;
export interface PaymentReceiptClient { list(page:number,signal?:AbortSignal):Promise<PaymentReceiptPage>;send(item:PaymentReceiptTodo):Promise<z.infer<typeof result>>; }
function options(){const token=sessionClient.getToken();if(!token)throw new Error('請先登入。');return {token};}
export const paymentReceiptClient:PaymentReceiptClient={
  async list(number,signal){const raw=await transport.get<{data:unknown}>('/api/v1/line/payment-overdue-reminders/receipts',{...options(),signal,params:{page:number,page_size:25}});return page.parse(raw.data);},
  async send(item){const raw=await transport.post<{data:unknown}>('/api/v1/line/payment-overdue-reminders/receipts/send',item.payment,options());return result.parse(raw.data);},
};
