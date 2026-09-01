/**
 * File: substitution_payables_lineage_client.ts
 * Description: 讀取代班→Payroll→Staff Payables 的 server-owned 版本化血緣。
 */
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import { StaffPayablesQueryError, mapStaffPayablesQueryError } from '../staff_payables/staff_payables_query_errors';
import { z } from 'zod';

const DateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const EvidenceSchema = z.strictObject({
  obligation_identity: z.string().min(1),
  assignment_id: z.number().int().positive(),
  staff_id: z.number().int().positive(),
  amount_due_ntd: z.number().int().positive(),
  due_date: DateSchema.nullable(),
  obligation_status: z.enum(['open', 'settled', 'cancelled']),
  obligation_payroll_version: z.number().int().nonnegative(),
  obligation_event_id: z.number().int().positive(),
  projection_status: z.enum(['payable', 'completed', 'anomaly']).nullable(),
  projection_amount_ntd: z.number().int().positive().nullable(),
  projection_net_paid_ntd: z.number().int().nonnegative().nullable(),
  projection_balance_ntd: z.number().int().nullable(),
  projection_version: z.number().int().nonnegative().nullable(),
  projection_event_id: z.number().int().positive().nullable(),
  blockers: z.array(z.string()),
});

const ItemSchema = z.strictObject({
  item_index: z.number().int().nonnegative(),
  outcome_event_id: z.number().int().positive(),
  original_assignment_id: z.number().int().positive(),
  original_schedule_id: z.number().int().positive(),
  original_staff_id: z.number().int().positive(),
  original_work_date: DateSchema,
  resolution_type: z.enum(['defer_following_assignments', 'substitute']),
  resulting_assignment_id: z.number().int().positive(),
  resulting_staff_id: z.number().int().positive(),
  resulting_service_date: DateSchema,
  payroll_event_id: z.number().int().positive().nullable(),
  payroll_event_expected_version: z.number().int().nonnegative().nullable(),
  payroll_event_resulting_version: z.number().int().nonnegative().nullable(),
  payroll_fingerprint: z.string().regex(/^[0-9a-f]{64}$/).nullable(),
  payables_evidence: EvidenceSchema.nullable(),
  lineage_subject: z.string().min(1),
  blockers: z.array(z.string()),
});

export const SubstitutionPayablesLineageSchema = z.strictObject({
  case_no: z.string().min(1).max(50),
  batch_key: z.string().min(1),
  scheduling_receipt_id: z.number().int().positive(),
  scheduling_version: z.number().int().nonnegative(),
  scheduling_generation: z.number().int().nonnegative(),
  expected_payroll_version: z.number().int().nonnegative(),
  resulting_payroll_version: z.number().int().nonnegative(),
  items: z.array(ItemSchema),
  authoritative_complete: z.boolean(),
  blockers: z.array(z.string()),
});

const ResponseSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: SubstitutionPayablesLineageSchema.nullable(),
  error: z.string().nullable().optional(),
});

export type SubstitutionPayablesLineage = z.infer<typeof SubstitutionPayablesLineageSchema>;

export interface SubstitutionPayablesLineageClient {
  query(caseNo: string, batchKey: string): Promise<SubstitutionPayablesLineage>;
}

function validateIdentity(value: string, label: string): string {
  if (typeof value !== 'string' || value.trim() !== value || value.length < 1 || value.length > 191) {
    throw new StaffPayablesQueryError('SUBSTITUTION_LINEAGE_VALIDATION', `${label} 格式無效。`);
  }
  return value;
}

class DefaultSubstitutionPayablesLineageClient implements SubstitutionPayablesLineageClient {
  async query(caseNo: string, batchKey: string): Promise<SubstitutionPayablesLineage> {
    const token = sessionClient.getToken();
    if (!token) throw new StaffPayablesQueryError('STAFF_PAYABLES_UNAUTHENTICATED', '請先登入。', false, 401);
    const validatedCaseNo = validateIdentity(caseNo, 'caseNo');
    const validatedBatchKey = validateIdentity(batchKey, 'batchKey');
    try {
      const raw = await transport.get<unknown>(
        `/api/v1/orders/${encodeURIComponent(validatedCaseNo)}/leave-substitution/${encodeURIComponent(validatedBatchKey)}/payables-lineage`,
        { token, headers: { 'X-Correlation-ID': 'substitution-payables-lineage' } },
      );
      const decoded = ResponseSchema.safeParse(raw);
      if (!decoded.success) {
        throw new ApiDecodeError('代班薪資血緣回應結構異常。', decoded.error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message, code: issue.code })), raw);
      }
      if (!decoded.data.success || decoded.data.data === null) {
        throw new StaffPayablesQueryError('SUBSTITUTION_LINEAGE_FAILURE', decoded.data.error ?? decoded.data.message);
      }
      return decoded.data.data;
    } catch (error) {
      throw mapStaffPayablesQueryError(error);
    }
  }
}

export const substitutionPayablesLineageClient: SubstitutionPayablesLineageClient = new DefaultSubstitutionPayablesLineageClient();
