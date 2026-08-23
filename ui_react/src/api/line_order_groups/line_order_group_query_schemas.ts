/**
 * File: line_order_group_query_schemas.ts
 * Description: 嚴格定義 LINE 訂單群組清單、明細與不可變事件查詢回應，拒絕額外欄位。
 */
import { z } from 'zod';

export const LineOrderGroupStatusSchema = z.enum([
  'unbound',
  'bound',
  'inviting',
  'active',
  'attention',
  'replaced',
  'released',
]);

export const LineOrderGroupRecordSchema = z.strictObject({
  case_no: z.string().min(1),
  group_id: z.string().min(1).nullable(),
  status: LineOrderGroupStatusSchema,
  version: z.number().int().nonnegative(),
});

export const LineOrderGroupPageSchema = z.strictObject({
  items: z.array(LineOrderGroupRecordSchema),
  total: z.number().int().nonnegative(),
});

export const LineOrderGroupEventSchema = z.strictObject({
  event_id: z.number().int().positive(),
  case_no: z.string().min(1),
  event_type: z.string().min(1),
  actor_id: z.string().min(1),
  occurred_at: z.string().datetime({ offset: true }),
  invitation_fingerprint: z.string().min(1).nullable(),
});

export const LineOrderGroupEventsSchema = z.array(LineOrderGroupEventSchema);

export type LineOrderGroupStatus = z.infer<typeof LineOrderGroupStatusSchema>;
export type LineOrderGroupRecord = z.infer<typeof LineOrderGroupRecordSchema>;
export type LineOrderGroupPage = z.infer<typeof LineOrderGroupPageSchema>;
export type LineOrderGroupEvent = z.infer<typeof LineOrderGroupEventSchema>;
