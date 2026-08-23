/**
 * File: contract_signing_client.ts
 * Description: 嚴格解碼案件契約簽署狀態 GET，供 Orders 契約 Drawer 顯示真實簽回進度。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';

const ContractDocumentSchema = z.strictObject({
  document_version_id: z.number().int().positive(),
  scope: z.string().min(1),
  role: z.string().min(1),
  target_key: z.string().min(1),
  version_number: z.number().int().positive(),
  template_key: z.string().nullable(),
  template_sha256: z.string().nullable(),
  mapping_sha256: z.string().nullable(),
  archive_sha256: z.string().min(1),
  mime_type: z.string().min(1),
  file_size: z.number().int().nonnegative(),
});

export const ContractSigningStatusSchema = z.strictObject({
  case_no: z.string().min(1),
  staff_segments: z.array(z.strictObject({
    segment_id: z.number().int().positive(),
    staff_id: z.number().int().positive(),
    sent: z.boolean(),
    signed_received: z.boolean(),
  })),
  commitment_id: z.number().int().positive().nullable(),
  client_document_sent: z.boolean(),
  client_signed_received: z.boolean(),
  contract_identity: z.string().nullable(),
  documents: z.array(ContractDocumentSchema),
});

const EnvelopeSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: ContractSigningStatusSchema,
  error: z.string().nullable(),
});

export type ContractSigningStatus = z.infer<typeof ContractSigningStatusSchema>;

export const contractSigningClient = {
  async query(caseNo: string, options?: { signal?: AbortSignal }): Promise<ContractSigningStatus> {
    const canonicalCaseNo = caseNo.trim();
    if (!canonicalCaseNo) throw new Error('案件編號不得為空。');
    const endpoint = `/api/v1/orders/${encodeURIComponent(canonicalCaseNo)}/contract-signing`;
    const requestOptions: RequestOptions = {
      signal: options?.signal,
      token: sessionClient.getToken(),
    };
    const envelope = decodePayload(
      EnvelopeSchema,
      await transport.get(endpoint, requestOptions),
    );
    if (!envelope.success) {
      throw new ApiHttpError(
        400,
        'CONTRACT_SIGNING_QUERY_FAILED',
        envelope.error ?? envelope.message,
        false,
        envelope,
      );
    }
    if (envelope.data.case_no !== canonicalCaseNo) {
      throw new Error('契約簽署狀態案件識別不一致。');
    }
    return envelope.data;
  },
};
