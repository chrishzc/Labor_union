/** Typed union log reminders. Reading the list never creates a delivery task. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';

const item = z.object({ case_no: z.string(), staff_id: z.number().int().positive(),
  missing_from: z.string(), missing_through: z.string(), consecutive_days: z.number().int().min(4),
  group_label: z.string(), can_send: z.boolean() }).strict();
const page = z.object({ items: z.array(item), total: z.number().int().nonnegative(),
  page: z.number().int().positive(), page_size: z.number().int().positive() }).strict();
const receipt = z.object({ task_id: z.number().int().positive(), status: z.string() }).strict();
export type ServiceDayLogReminder = z.infer<typeof item>;
export type ServiceDayLogReminderPage = z.infer<typeof page>;
export interface ServiceDayLogReminderClient {
  list(page: number): Promise<ServiceDayLogReminderPage>;
  send(item: ServiceDayLogReminder, key: string): Promise<z.infer<typeof receipt>>;
}
function options() {
  const token = sessionClient.getToken();
  if (!token) throw new Error('請先登入。');
  return { token };
}
export const serviceDayLogReminderClient: ServiceDayLogReminderClient = {
  async list(number) {
    const raw = await transport.get<{data: unknown}>('/api/v1/line/order-groups/log-reminders',
      {...options(), params:{page:number, page_size:25}});
    return page.parse(raw.data);
  },
  async send(value, key) {
    const raw = await transport.post<{data: unknown}>('/api/v1/line/order-groups/log-reminders/send', {
      case_no:value.case_no, staff_id:value.staff_id, missing_from:value.missing_from,
      missing_through:value.missing_through, idempotency_key:key,
    }, options());
    return receipt.parse(raw.data);
  },
};
