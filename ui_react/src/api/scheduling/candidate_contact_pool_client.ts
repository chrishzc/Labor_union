/**
 * File: candidate_contact_pool_client.ts
 * Description: 以 closed Zod 解碼候選聯繫池 GET，驗證案件 identity 並保留傳輸錯誤語意。
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

export type CandidateContactPool = z.infer<typeof CandidateContactPoolSchema>;

export interface CandidateContactPoolQueryOptions {
  signal?: AbortSignal;
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
};
