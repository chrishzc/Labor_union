/**
 * File: hcm_import_result_client.ts
 * Description: 以fresh memory bearer查詢 HCM recent results，並嚴格驗證legacy與row outcome契約。
 */
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';
import { HcmImportResultError, mapHcmImportResultError } from './hcm_import_result_errors';
import { HcmImportResultEnvelopeSchema, type HcmImportResultPage } from './hcm_import_result_schemas';

export interface HcmImportResultQueryOptions {
  signal?: AbortSignal;
  baseUrl?: string;
}

export async function queryHcmImportResults(
  params: { limit?: number; beforeReceiptId?: number } = {},
  options: HcmImportResultQueryOptions = {}
): Promise<HcmImportResultPage> {
  const token = sessionClient.getToken();
  if (!token) throw new HcmImportResultError('hcm_result_unauthenticated', '管理員 Session 已失效。');
  try {
    const raw = await transport.get('/api/v1/case-import/hcm/workbooks/results', {
      token,
      signal: options.signal,
      baseUrl: options.baseUrl,
      params: {
        limit: params.limit ?? 20,
        before_receipt_id: params.beforeReceiptId,
      },
    });
    const envelope = decodePayload(HcmImportResultEnvelopeSchema, raw);
    if (!envelope.success) throw new HcmImportResultError('hcm_result_business_error', envelope.message);
    return envelope.data;
  } catch (error) {
    throw mapHcmImportResultError(error);
  }
}

export const hcmImportResultClient = { query: queryHcmImportResults };

