/**
 * File: candidate_contact_pool_client.ts
 * Description: 查詢與操作候選聯繫池，嚴格驗證案件、候選及操作 identity。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';

const IsoDateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const IsoDateTimeSchema = z.string().regex(
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?$/,
);

const CandidateInformationDeliverySchema = z.strictObject({
  status: z.enum([
    'queued',
    'pending',
    'sent',
    'retryable_failed',
    'failed',
    'cancelled',
  ]),
  sent_at: IsoDateTimeSchema,
});

const CandidateContactSchema = z.strictObject({
  id: z.number().int().positive(),
  staff_id: z.number().int().positive(),
  service_start_date: IsoDateSchema,
  service_end_date: IsoDateSchema,
  status: z.enum(['active', 'selected', 'withdrawn']),
  created_at: IsoDateTimeSchema,
  staff_name: z.string().min(1).max(100),
  willingness: z.enum(['pending', 'willing', 'unwilling']),
  reason: z.string().max(500).nullable(),
  information: z.strictObject({
    '1': CandidateInformationDeliverySchema.nullable(),
    '2': CandidateInformationDeliverySchema.nullable(),
  }),
}).superRefine((candidate, context) => {
  if (candidate.service_start_date > candidate.service_end_date) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['service_end_date'],
      message: '服務結束日不得早於開始日。',
    });
  }
});

export const CandidateContactPoolSchema = z.strictObject({
  pool_id: z.number().int().positive().nullable(),
  case_no: z.string().min(1).max(50),
  candidates: z.array(CandidateContactSchema).max(50),
});

const CandidateContactPoolEnvelopeSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: CandidateContactPoolSchema.nullable(),
  error: z.string().nullable(),
});

const SendCandidateInformationResultSchema = z.strictObject({
  status: z.enum(['queued', 'idempotent_replay']),
  event_id: z.number().int().positive(),
  line_task_id: z.number().int().positive().nullable(),
}).superRefine((result, context) => {
  if (result.status === 'queued' && result.line_task_id === null) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['line_task_id'],
      message: 'queued 結果必須帶 line_task_id。',
    });
  }
});

const SendCandidateInformationEnvelopeSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: SendCandidateInformationResultSchema.nullable(),
  error: z.string().nullable(),
});

const AddCandidatesResultSchema = z.strictObject({
  pool_id: z.number().int().positive(),
  candidate_ids: z.array(z.number().int().positive()).min(1).max(50),
  status: z.literal('recorded'),
});

const CandidateWillingnessResultSchema = z.strictObject({
  status: z.enum(['recorded', 'idempotent_replay']),
  event_id: z.number().int().positive(),
});

const mutationEnvelope = <TSchema extends z.ZodTypeAny>(schema: TSchema) => z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: schema.nullable(),
  error: z.string().nullable(),
});

export type CandidateContactPool = z.infer<typeof CandidateContactPoolSchema>;
export type SendCandidateInformationResult = z.infer<typeof SendCandidateInformationResultSchema>;
export type AddCandidatesResult = z.infer<typeof AddCandidatesResultSchema>;
export type CandidateWillingnessResult = z.infer<typeof CandidateWillingnessResultSchema>;

export interface CandidateContactInput {
  staff_id: number;
  start_date: string;
  end_date: string;
}

export interface CandidateContactPoolQueryOptions {
  signal?: AbortSignal;
}

function mutationIdentity(): { actor: string; token: string } {
  const actor = sessionClient.getUser()?.username.trim() ?? '';
  const token = sessionClient.getToken();
  if (!actor || !token) {
    throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
  }
  return { actor, token };
}

function canonicalCaseNo(caseNo: string): string {
  const canonical = caseNo.trim();
  if (!canonical || canonical.length > 50) {
    throw new Error('案件編號必須是 1 至 50 字元。');
  }
  return canonical;
}

export const candidateContactPoolClient = {
  async query(
    caseNo: string,
    options?: CandidateContactPoolQueryOptions,
  ): Promise<CandidateContactPool> {
    const canonicalCaseNo = caseNo.trim();
    if (!canonicalCaseNo || canonicalCaseNo.length > 50) {
      throw new Error('案件編號必須是 1 至 50 字元。');
    }
    const requestOptions: RequestOptions = {
      signal: options?.signal,
      token: sessionClient.getToken(),
    };
    const envelope = decodePayload(
      CandidateContactPoolEnvelopeSchema,
      await transport.get(
        `/api/v1/orders/${encodeURIComponent(canonicalCaseNo)}/candidate-contact-pool`,
        requestOptions,
      ),
    );
    if (!envelope.success || envelope.data === null) {
      throw new ApiHttpError(
        422,
        'CANDIDATE_CONTACT_POOL_QUERY_FAILED',
        envelope.error ?? envelope.message,
        false,
        envelope,
      );
    }
    if (envelope.data.case_no !== canonicalCaseNo) {
      throw new Error('候選聯繫池案件識別不一致。');
    }
    return envelope.data;
  },

  async addCandidates(
    caseNo: string,
    candidates: CandidateContactInput[],
  ): Promise<AddCandidatesResult> {
    const canonical = canonicalCaseNo(caseNo);
    const { actor, token } = mutationIdentity();
    if (candidates.length < 1 || candidates.length > 50) {
      throw new Error('必須選擇 1 至 50 位候選月嫂。');
    }
    const candidateSchema = z.strictObject({
      staff_id: z.number().int().positive(),
      start_date: IsoDateSchema,
      end_date: IsoDateSchema,
    }).refine((candidate) => candidate.start_date <= candidate.end_date, {
      message: '候選服務結束日不得早於開始日。',
      path: ['end_date'],
    });
    const parsedCandidates = z.array(candidateSchema).min(1).max(50).parse(candidates);
    const envelope = decodePayload(
      mutationEnvelope(AddCandidatesResultSchema),
      await transport.post(
        `/api/v1/orders/${encodeURIComponent(canonical)}/candidate-contact-pool/candidates`,
        {
          candidates: parsedCandidates,
          actor,
          event_key: `orders-candidate-pool-add-${crypto.randomUUID()}`,
        },
        { token },
      ),
    );
    if (!envelope.success || envelope.data === null) {
      throw new ApiHttpError(422, 'CANDIDATE_POOL_ADD_FAILED', envelope.error ?? envelope.message, false, envelope);
    }
    return envelope.data;
  },

  async recordWillingness(
    caseNo: string,
    candidateId: number,
    willingness: 'willing' | 'unwilling',
    reason: string,
  ): Promise<CandidateWillingnessResult> {
    const canonical = canonicalCaseNo(caseNo);
    const { actor, token } = mutationIdentity();
    if (!Number.isInteger(candidateId) || candidateId <= 0) {
      throw new Error('候選聯繫識別必須是正整數。');
    }
    const canonicalReason = reason.trim();
    if (canonicalReason.length > 500 || (willingness === 'unwilling' && !canonicalReason)) {
      throw new Error('無意願時必須填寫 500 字內拒絕理由。');
    }
    const envelope = decodePayload(
      mutationEnvelope(CandidateWillingnessResultSchema),
      await transport.put(
        `/api/v1/orders/${encodeURIComponent(canonical)}/candidate-contact-pool/candidates/${candidateId}/willingness`,
        {
          willingness,
          reason: canonicalReason || '人工補登願意',
          actor,
          event_key: `orders-candidate-willingness-${candidateId}-${crypto.randomUUID()}`,
        },
        { token },
      ),
    );
    if (!envelope.success || envelope.data === null) {
      throw new ApiHttpError(422, 'CANDIDATE_WILLINGNESS_FAILED', envelope.error ?? envelope.message, false, envelope);
    }
    return envelope.data;
  },

  async sendInformation(
    caseNo: string,
    candidateId: number,
    infoType: 1 | 2,
  ): Promise<SendCandidateInformationResult> {
    const canonicalCaseNo = caseNo.trim();
    const actor = sessionClient.getUser()?.username.trim() ?? '';
    const token = sessionClient.getToken();
    if (!canonicalCaseNo || canonicalCaseNo.length > 50) {
      throw new Error('案件編號必須是 1 至 50 字元。');
    }
    if (!Number.isInteger(candidateId) || candidateId <= 0) {
      throw new Error('候選聯繫識別必須是正整數。');
    }
    if (!actor || !token) {
      throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
    }
    const envelope = decodePayload(
      SendCandidateInformationEnvelopeSchema,
      await transport.post(
        `/api/v1/orders/${encodeURIComponent(canonicalCaseNo)}/candidate-contact-pool/candidates/${candidateId}/information`,
        {
          info_type: infoType,
          actor,
          event_key: `orders-candidate-info-${infoType}-${candidateId}-${crypto.randomUUID()}`,
        },
        { token },
      ),
    );
    if (!envelope.success || envelope.data === null) {
      throw new ApiHttpError(
        422,
        'CANDIDATE_INFORMATION_SEND_FAILED',
        envelope.error ?? envelope.message,
        false,
        envelope,
      );
    }
    return envelope.data;
  },
};
