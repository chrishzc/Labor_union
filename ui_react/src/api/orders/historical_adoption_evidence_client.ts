/** Authenticated GET client for immutable Historical Orders adoption evidence. */
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import {
  HistoricalOrderAdoptionEvidenceEnvelopeSchema,
  type HistoricalOrderAdoptionEvidence,
} from './historical_adoption_evidence_schemas';

export interface HistoricalAdoptionEvidenceQueryOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
}

export const historicalAdoptionEvidencePath = (caseNo: string): string =>
  `/api/orders/${encodeURIComponent(caseNo)}/historical-adoption-evidence`;

export async function queryHistoricalAdoptionEvidence(
  caseNo: string,
  options?: HistoricalAdoptionEvidenceQueryOptions,
): Promise<HistoricalOrderAdoptionEvidence> {
  const identity = caseNo.trim();
  if (!identity || identity.length > 50 || /\s/.test(identity)) {
    throw new Error('案件編號格式無效，無法讀取 historical adoption evidence。');
  }
  const token = sessionClient.getToken();
  if (!token) throw new Error('請先登入再讀取 historical adoption evidence。');
  const request: RequestOptions = {
    signal: options?.signal,
    timeoutMs: options?.timeoutMs ?? 30_000,
    baseUrl: options?.baseUrl,
    token,
  };
  const raw = await transport.get<unknown>(historicalAdoptionEvidencePath(identity), request);
  const evidence = decodePayload(HistoricalOrderAdoptionEvidenceEnvelopeSchema, raw).data;
  if (evidence.case_no !== identity) {
    throw new Error('historical adoption evidence 不屬於目前案件。');
  }
  return evidence;
}

export const historicalAdoptionEvidenceClient = {
  queryByCase: queryHistoricalAdoptionEvidence,
};
