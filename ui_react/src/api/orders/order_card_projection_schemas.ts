/**
 * File: order_card_projection_schemas.ts
 * Description: 嚴格解碼案件範圍 Orders card composite projection。
 */
import { z } from 'zod';

const DateOnlySchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const AvailabilitySchema = z.enum(['available', 'unavailable', 'blocked']);

export const OrdersCardProjectionFieldSchema = <T extends z.ZodTypeAny>(valueSchema: T) => z.strictObject({
  value: valueSchema.nullable(),
  owner: z.string().min(1),
  source_identity: z.string().min(1),
  source_version: z.string().min(1).nullable(),
  availability: AvailabilitySchema,
  availability_reason: z.string().min(1).nullable(),
}).superRefine((field, context) => {
  if (field.availability === 'available' && field.value === null) {
    context.addIssue({ code: 'custom', path: ['value'], message: 'available projection 必須帶 value。' });
  }
  if (field.availability !== 'available' && field.value !== null) {
    context.addIssue({ code: 'custom', path: ['value'], message: 'unavailable/blocked projection 不得帶 value。' });
  }
});

export const OrdersCardAssignmentSegmentSchema = z.strictObject({
  assignment_id: OrdersCardProjectionFieldSchema(z.number().int().positive()),
  staff_id: OrdersCardProjectionFieldSchema(z.number().int().positive()),
  staff_name: OrdersCardProjectionFieldSchema(z.string()),
  sequence: OrdersCardProjectionFieldSchema(z.number().int().positive()),
  assigned_start_date: OrdersCardProjectionFieldSchema(DateOnlySchema),
  assigned_end_date: OrdersCardProjectionFieldSchema(DateOnlySchema),
  status: OrdersCardProjectionFieldSchema(z.string()),
});

export const OrdersCardProjectionSchema = z.strictObject({
  case_no: z.string().min(1),
  contact_phone: OrdersCardProjectionFieldSchema(z.string()),
  contact_address: OrdersCardProjectionFieldSchema(z.string()),
  requires_cooking: OrdersCardProjectionFieldSchema(z.boolean()),
  floor_fee_ntd: OrdersCardProjectionFieldSchema(z.number().int().nonnegative()),
  deposit_amount_ntd: OrdersCardProjectionFieldSchema(z.number().int().nonnegative()),
  deposit_settlement_state: OrdersCardProjectionFieldSchema(z.enum(['unsettled', 'settled'])),
  deposit_settled_on: OrdersCardProjectionFieldSchema(DateOnlySchema),
  actual_start_date: OrdersCardProjectionFieldSchema(DateOnlySchema),
  actual_end_date: OrdersCardProjectionFieldSchema(DateOnlySchema),
  assignment_segments: OrdersCardProjectionFieldSchema(z.array(OrdersCardAssignmentSegmentSchema)),
});

export type OrdersCardProjection = z.infer<typeof OrdersCardProjectionSchema>;
export type OrdersCardAssignmentSegment = z.infer<typeof OrdersCardAssignmentSegmentSchema>;
export type OrdersCardProjectionField<T> = {
  value: T | null;
  owner: string;
  source_identity: string;
  source_version: string | null;
  availability: z.infer<typeof AvailabilitySchema>;
  availability_reason: string | null;
};
