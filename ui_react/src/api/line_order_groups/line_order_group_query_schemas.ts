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
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  total_pages: z.number().int().nonnegative(),
});

export const LineOrderGroupEventSchema = z.strictObject({
  event_id: z.number().int().positive(),
  case_no: z.string().min(1),
  event_type: z.string().min(1),
  actor_id: z.string().min(1),
  occurred_at: z.string().datetime({ offset: true }),
  invitation_fingerprint: z.string().min(1).nullable(),
});

export const LineOrderGroupEventPageSchema = z.strictObject({
  items: z.array(LineOrderGroupEventSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  total_pages: z.number().int().nonnegative(),
});

export type LineOrderGroupStatus = z.infer<typeof LineOrderGroupStatusSchema>;
export type LineOrderGroupRecord = z.infer<typeof LineOrderGroupRecordSchema>;
export type LineOrderGroupPage = z.infer<typeof LineOrderGroupPageSchema>;
export type LineOrderGroupEvent = z.infer<typeof LineOrderGroupEventSchema>;
export type LineOrderGroupEventPage = z.infer<typeof LineOrderGroupEventPageSchema>;

export const LineOrderGroupParticipantSchema = z.strictObject({
  role: z.enum(['customer', 'staff']),
  name: z.string().nullable(),
  staff_union_no: z.string().max(50).nullable().optional(),
  membership_status: z.enum(['joined', 'left', 'pending', 'unknown']),
});
export const LineOrderGroupWorkspaceEventSchema = z.strictObject({
  event_key: z.string().min(1),
  case_no: z.string().min(1),
  event_type: z.string().min(1),
  occurred_at: z.string().datetime({ offset: true }),
  participant_role: z.enum(['customer', 'staff']).nullable(),
  participant_name: z.string().nullable(),
  participant_union_no: z.string().nullable().optional(),
});
export const LineOrderGroupWorkspaceRecordSchema = z.strictObject({
  case_no: z.string().min(1),
  status: LineOrderGroupStatusSchema,
  customer_name: z.string().nullable(),
  bound_at: z.string().datetime({ offset: true }).nullable(),
  last_invitation_at: z.string().datetime({ offset: true }).nullable(),
  members: z.array(LineOrderGroupParticipantSchema),
  latest_event: LineOrderGroupWorkspaceEventSchema.nullable(),
}).refine(value => value.latest_event === null || value.latest_event.case_no === value.case_no, {
  message: '最近動態的案件不一致。',
});
export const LineOrderGroupWorkspacePageSchema = z.strictObject({
  items: z.array(LineOrderGroupWorkspaceRecordSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  total_pages: z.number().int().nonnegative(),
});
export const LineOrderGroupWorkspaceEventPageSchema = z.strictObject({
  items: z.array(LineOrderGroupWorkspaceEventSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  total_pages: z.number().int().nonnegative(),
});
export type LineOrderGroupParticipant = z.infer<typeof LineOrderGroupParticipantSchema>;
export type LineOrderGroupWorkspaceEvent = z.infer<typeof LineOrderGroupWorkspaceEventSchema>;
export type LineOrderGroupWorkspaceRecord = z.infer<typeof LineOrderGroupWorkspaceRecordSchema>;
export type LineOrderGroupWorkspacePage = z.infer<typeof LineOrderGroupWorkspacePageSchema>;
export type LineOrderGroupWorkspaceEventPage = z.infer<typeof LineOrderGroupWorkspaceEventPageSchema>;
