/**
 * File: staff_assignment_options_client.ts
 * Description: 取得單一月嫂的正式指派案件選項，strict decode 後供 Calendar 下拉選單使用。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';

const StaffAssignmentOptionSchema = z.strictObject({
  id: z.number().int().positive(),
  case_no: z.string().min(1).max(50),
  staff_id: z.number().int().positive(),
  status: z.string().min(1).max(50),
  assigned_start_date: z.string().date(),
  assigned_end_date: z.string().date(),
  order_status: z.string().min(1).max(100),
  actual_start_date: z.string().date().nullable(),
  actual_end_date: z.string().date().nullable(),
  staff_name: z.string().min(1).max(200),
});

const StaffAssignmentOptionsEnvelopeSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: z.strictObject({ assignments: z.array(StaffAssignmentOptionSchema) }),
  error: z.string().nullable(),
});

export type StaffAssignmentOption = z.infer<typeof StaffAssignmentOptionSchema>;

export interface StaffAssignmentOptionsQueryOptions {
  signal?: AbortSignal;
  token?: string | null;
  baseUrl?: string;
  timeoutMs?: number;
}

export async function getStaffAssignmentOptions(
  staffId: number,
  options?: StaffAssignmentOptionsQueryOptions,
): Promise<readonly StaffAssignmentOption[]> {
  if (!Number.isInteger(staffId) || staffId < 1) throw new Error('月嫂 identity 不正確。');
  const requestOptions: RequestOptions = {
    signal: options?.signal,
    token: options?.token !== undefined ? options.token : sessionClient.getToken(),
    baseUrl: options?.baseUrl,
    timeoutMs: options?.timeoutMs,
  };
  const raw = await transport.get(
    `/api/v1/staff/${encodeURIComponent(String(staffId))}/assignment-schedules`,
    requestOptions,
  );
  const envelope = decodePayload(StaffAssignmentOptionsEnvelopeSchema, raw);
  if (!envelope.success) throw new Error(envelope.error ?? envelope.message);
  return envelope.data.assignments;
}

export const staffAssignmentOptionsClient = { getStaffAssignmentOptions };
