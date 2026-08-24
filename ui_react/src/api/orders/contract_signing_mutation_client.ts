/**
 * File: contract_signing_mutation_client.ts
 * Description: 以既有 Contract Signing typed API 建立寄送與簽回文件命令，不直接呼叫 LINE provider。
 */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';

const ReceiptSchema = z.strictObject({
  document_version_id: z.number().int().positive(),
  signing_event_id: z.number().int().positive(),
  line_delivery_task_id: z.number().int().positive().nullable(),
  commitment_id: z.number().int().positive().nullable(),
  contract_identity: z.string().min(1).nullable(),
});

const EnvelopeSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: ReceiptSchema,
  error: z.string().nullable(),
});

export type ContractSigningReceipt = z.infer<typeof ReceiptSchema>;

export interface ContractCommandOptions {
  idempotencyKey: string;
  correlationId: string;
  signal?: AbortSignal;
}

function canonicalCaseNo(caseNo: string): string {
  const canonical = caseNo.trim();
  if (!canonical) throw new Error('案件編號不得為空。');
  return canonical;
}

function commandOptions(options: ContractCommandOptions): RequestOptions {
  return {
    signal: options.signal,
    token: sessionClient.getToken(),
    headers: {
      'Idempotency-Key': options.idempotencyKey,
      'X-Correlation-ID': options.correlationId,
    },
  };
}

async function command(path: string, body: unknown, options: ContractCommandOptions): Promise<ContractSigningReceipt> {
  const envelope = decodePayload(EnvelopeSchema, await transport.post(path, body, commandOptions(options)));
  if (!envelope.success) {
    throw new ApiHttpError(400, 'CONTRACT_SIGNING_COMMAND_FAILED', envelope.error ?? envelope.message, false, envelope);
  }
  return envelope.data;
}

function signedDocumentBody(document: File, expectedDocumentVersionId: number): FormData {
  if (!(expectedDocumentVersionId > 0)) throw new Error('簽回文件版本無效。');
  if (document.size <= 0) throw new Error('簽回檔案不得為空。');
  const body = new FormData();
  body.append('document', document, document.name);
  body.append('expected_document_version_id', String(expectedDocumentVersionId));
  return body;
}

export const contractSigningMutationClient = {
  sendStaff(caseNo: string, segmentId: number, downloadUrl: string, options: ContractCommandOptions): Promise<ContractSigningReceipt> {
    if (!(segmentId > 0)) throw new Error('月嫂服務分段無效。');
    return command(
      `/api/v1/orders/${encodeURIComponent(canonicalCaseNo(caseNo))}/contract-signing/staff-segments/${segmentId}/send`,
      { download_url: downloadUrl },
      options,
    );
  },
  uploadStaffSignedReturn(caseNo: string, segmentId: number, document: File, expectedDocumentVersionId: number, options: ContractCommandOptions): Promise<ContractSigningReceipt> {
    if (!(segmentId > 0)) throw new Error('月嫂服務分段無效。');
    return command(
      `/api/v1/orders/${encodeURIComponent(canonicalCaseNo(caseNo))}/contract-signing/staff-segments/${segmentId}/signed-return`,
      signedDocumentBody(document, expectedDocumentVersionId),
      options,
    );
  },
  sendClient(caseNo: string, downloadUrl: string, options: ContractCommandOptions): Promise<ContractSigningReceipt> {
    return command(
      `/api/v1/orders/${encodeURIComponent(canonicalCaseNo(caseNo))}/contract-signing/client/send`,
      { download_url: downloadUrl },
      options,
    );
  },
  uploadClientSignedReturn(caseNo: string, document: File, expectedDocumentVersionId: number, options: ContractCommandOptions): Promise<ContractSigningReceipt> {
    return command(
      `/api/v1/orders/${encodeURIComponent(canonicalCaseNo(caseNo))}/contract-signing/client/signed-return`,
      signedDocumentBody(document, expectedDocumentVersionId),
      options,
    );
  },
};
