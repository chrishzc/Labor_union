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

export interface ContractDocumentDownloadArtifact {
  blob: Blob;
  filename: string;
  mimeType: string;
}

function filenameFromHeader(value: string | null, fallback: string): string {
  const match = value?.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1]?.trim();
  return filename && filename.length <= 255 ? filename : fallback;
}

async function downloadError(response: Response): Promise<ApiHttpError> {
  const raw = await response.json().catch(() => undefined);
  return new ApiHttpError(
    response.status,
    `HTTP_${response.status}`,
    `契約文件下載失敗（HTTP ${response.status}）。`,
    response.status >= 500,
    raw,
  );
}

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

  async downloadDocument(
    caseNo: string,
    documentVersionId: number,
    signal?: AbortSignal,
  ): Promise<ContractDocumentDownloadArtifact> {
    const canonicalCaseNo = caseNo.trim();
    if (!canonicalCaseNo) throw new Error('案件編號不得為空。');
    if (!Number.isInteger(documentVersionId) || documentVersionId <= 0) {
      throw new Error('契約文件版本識別無效。');
    }
    const token = sessionClient.getToken();
    if (!token) throw new ApiHttpError(401, 'UNAUTHENTICATED', '請先登入。');
    const response = await fetch(
      `/api/v1/orders/${encodeURIComponent(canonicalCaseNo)}/contract-signing/documents/${documentVersionId}/download`,
      { method: 'GET', headers: { Authorization: `Bearer ${token}` }, signal },
    );
    if (!response.ok) throw await downloadError(response);
    const mimeType = response.headers.get('content-type')?.split(';')[0]?.trim().toLowerCase() ?? '';
    if (!mimeType || mimeType === 'application/json') {
      throw new ApiHttpError(422, 'CONTRACT_DOCUMENT_DOWNLOAD_MEDIA_TYPE', '契約文件下載回應缺少可用檔案類型。');
    }
    const blob = await response.blob();
    if (blob.size === 0) {
      throw new ApiHttpError(422, 'CONTRACT_DOCUMENT_DOWNLOAD_EMPTY', '契約文件下載內容為空。');
    }
    return {
      blob,
      mimeType,
      filename: filenameFromHeader(response.headers.get('content-disposition'), `contract-${canonicalCaseNo}-${documentVersionId}`),
    };
  },
};
