import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { decodePayload } from '../shared/runtime_decoder';

const Time=z.string().regex(/^(?:[01]\d|2[0-3]):[0-5]\d$/);
export const PaymentReminderScheduleSchema=z.strictObject({
  deposit_mode:z.enum(['immediate','daily']),deposit_time:Time,first_time:Time,second_time:Time,overdue_time:Time,
});
export type PaymentReminderSchedule=z.infer<typeof PaymentReminderScheduleSchema>;
const SettingsSchema=z.strictObject({revision:z.number().int().nonnegative(),schedule:PaymentReminderScheduleSchema,
  timezone:z.literal('Asia/Taipei'),followup_after_hours:z.literal(24),followup_limit:z.literal(1)});
const Envelope=z.object({success:z.literal(true),data:SettingsSchema});
export type PaymentReminderSettings=z.infer<typeof SettingsSchema>;
export interface PaymentReminderScheduleClient {
  get(signal?:AbortSignal):Promise<PaymentReminderSettings>;
  save(body:{schedule:PaymentReminderSchedule;expected_revision:number;idempotency_key:string}):Promise<PaymentReminderSettings>;
}
const path='/api/v1/line/payment-overdue-reminders/schedule';
export const paymentReminderScheduleClient:PaymentReminderScheduleClient={
  async get(signal){return decodePayload(Envelope,await transport.get(path,{signal,token:sessionClient.getToken()})).data;},
  async save(body){return decodePayload(Envelope,await transport.put(path,body,{token:sessionClient.getToken()})).data;},
};
