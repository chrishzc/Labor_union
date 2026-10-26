import { z } from 'zod';
import { transport } from '../shared/transport';
import { sessionClient } from '../auth/session_client';
import { ApiDecodeError, ApiHttpError } from '../shared/typed_errors';

const resultSchema = z.object({ actual_start_date:z.string(),actual_end_date:z.string(),order_version:z.number(),
  first_payment_due_date:z.string(),group_record_queued:z.boolean(),assignments:z.array(z.object({staff_id:z.number(),staff_name:z.string(),service_dates:z.array(z.string())})) });
export const serviceStartViewSchema = z.object({ request_id:z.number().int(),case_no:z.string(),staff_id:z.number().int(),staff_name:z.string(),
  segment_id:z.number().nullable(),order_version:z.number(),version:z.number(),status:z.enum(['awaiting_peers','substitute_required','applied']),
  requested_start_date:z.string().nullable(),selected_staff_id:z.number().nullable(),selected_staff_name:z.string().nullable(),
  willingness:z.enum(['pending','willing','unwilling']).nullable(),invitation_status:z.string().nullable(),joined:z.boolean(),result:resultSchema.nullable(),
  proposed_start_date:z.string().nullable(),proposed_end_date:z.string().nullable(),
  workflow_kind:z.enum(['service_start','leave','handover']).default('service_start'),
  leave_dates:z.array(z.object({original_date:z.string(),new_date:z.string().nullable()})).default([]),
  conflict_message:z.string().nullable().default(null),handover_dates:z.array(z.string()).default([]) });
export type ServiceStartView = z.infer<typeof serviceStartViewSchema>;
const pageSchema=z.object({items:z.array(serviceStartViewSchema),total:z.number().int(),page:z.number().int(),page_size:z.number().int()});
const optionsSchema=z.object({items:z.array(z.object({staff_id:z.number().int(),name:z.string()}))});
const handoverContextSchema=z.object({case_no:z.string(),assignment_id:z.number().int(),staff_id:z.number().int(),staff_name:z.string(),
  order_version:z.number().int(),scheduling_version:z.number().int(),service_dates:z.array(z.string()),request:serviceStartViewSchema.nullable()});
export type HandoverContext=z.infer<typeof handoverContextSchema>;
export interface HandoverInquiry {case_no:string;assignment_id:number;staff_id:number;expected_order_version:number;expected_scheduling_version:number;idempotency_key:string}
export interface StartCommand {expected_version:number;idempotency_key:string;staff_id?:number;start_date?:string;end_date?:string;dates?:{original_date:string;new_date:string}[];date_changes?:{original_date:string;new_date:string}[]}

async function call<T>(path:string,schema:z.ZodType<T,z.ZodTypeDef,unknown>,body?:StartCommand|HandoverInquiry):Promise<T> {
  const token=sessionClient.getToken();
  if(!token) throw new ApiHttpError(401,'UNAUTHENTICATED','請先登入。');
  const raw=body ? await transport.post<unknown>(path,body,{token}) : await transport.get<unknown>(path,{token});
  const envelope=z.object({success:z.boolean(),data:schema.nullable(),message:z.string()}).safeParse(raw);
  if(!envelope.success) throw new ApiDecodeError('服務安排資料格式錯誤。');
  if(!envelope.data.success || envelope.data.data===null) throw new ApiDecodeError(envelope.data.message);
  return envelope.data.data as T;
}
const base='/api/v1/scheduling/service-start';
export const serviceStartClient={
  handoverContext:(caseNo:string,assignmentId?:number)=>call(`${base}/handover/context?case_no=${encodeURIComponent(caseNo)}${assignmentId?`&assignment_id=${assignmentId}`:''}`,handoverContextSchema),
  inquireHandover:(body:HandoverInquiry)=>call(`${base}/handover/inquire`,serviceStartViewSchema,body),
  todos:(page=1,caseNo?:string)=>call(`${base}/todos?page=${page}&page_size=25${caseNo?`&case_no=${encodeURIComponent(caseNo)}`:''}`,pageSchema),
  options:(keyword='')=>call(`${base}/staff-options?keyword=${encodeURIComponent(keyword)}`,optionsSchema),
  detail:(id:number)=>call(`${base}/${id}`,serviceStartViewSchema),
  command:(id:number,action:'inquire'|'invite'|'dates'|'defer',body:StartCommand)=>call(`${base}/${id}/${action}`,serviceStartViewSchema,body),
};
