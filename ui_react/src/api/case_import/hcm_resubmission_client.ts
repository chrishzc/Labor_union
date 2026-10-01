/** Connects an active HCM warning to the controlled full-workbook correction flow. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';
import { HcmWorkbookSnapshot } from './hcm_workbook_client';
import {
  HcmResubmissionPreviewEnvelopeSchema,
  HcmResubmissionReceiptEnvelopeSchema,
  type HcmResubmissionPreview,
  type HcmResubmissionReceipt,
} from './hcm_workbook_schemas';

function token(): string {
  const value = sessionClient.getToken();
  if (!value) throw new Error('請先登入後再處理 HCM 異常。');
  return value;
}

const ReviewStateSchema = z.object({ review_identity: z.string(), case_no: z.string(), source_field: z.string(), review_version: z.number().int(), resolved: z.boolean() }).strict();
const SkipPreviewSchema = z.object({ review_identity: z.string(), case_no: z.string(), source_field: z.string().min(1).max(191), review_version: z.number().int().nonnegative(), preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/) }).strict();
export type HcmReviewSkipPreview = z.infer<typeof SkipPreviewSchema>;
const CurrentReviewsSchema = z.object({ items: z.array(z.object({ source_id: z.number().int(), review_identity: z.string(), case_no: z.string(), fields: z.array(z.string()), can_correct: z.boolean(), unavailable_reason: z.string().nullable().optional() }).strict()), next_cursor: z.number().int().nullable() }).strict();
export type HcmReviewState = z.infer<typeof ReviewStateSchema>;
export type HcmCurrentReviews = z.infer<typeof CurrentReviewsSchema>;
export type HcmCurrentReview = HcmCurrentReviews['items'][number];

/** Read the current owner predicate, including cases beyond the first page. */
export async function loadCurrentHcmReviewsForCases(
  caseNos: readonly string[],
  options?: { signal?: AbortSignal },
): Promise<readonly HcmCurrentReview[]> {
  const pending = new Set(caseNos);
  const matches: HcmCurrentReview[] = [];
  let cursor: number | undefined;
  while (pending.size > 0) {
    options?.signal?.throwIfAborted();
    const page = await hcmResubmissionClient.current(cursor, options);
    for (const item of page.items) {
      if (pending.delete(item.case_no)) matches.push(item);
    }
    if (page.next_cursor === null || pending.size === 0) return matches;
    if (page.items.length === 0 || page.next_cursor !== page.items.at(-1)?.source_id
      || (cursor !== undefined && page.next_cursor >= cursor)) {
      throw new Error('進件欄位問題分頁無法繼續，請重新讀取。');
    }
    cursor = page.next_cursor;
  }
  return matches;
}

export const hcmResubmissionClient = {
  async previewFieldSkip(reviewIdentity: string, sourceField: string): Promise<HcmReviewSkipPreview> {
    const raw = await transport.post(`/api/v1/case-import/hcm/reviews/${encodeURIComponent(reviewIdentity)}/skip-field/preview`,
      { source_field: sourceField }, { token: token() });
    const preview = decodePayload(z.object({ data: SkipPreviewSchema }), raw).data;
    if (preview.review_identity !== reviewIdentity || preview.source_field !== sourceField) throw new Error('警示略過預覽與欄位不一致。');
    return preview;
  },
  async applyFieldSkip(preview: HcmReviewSkipPreview, idempotencyKey: string): Promise<HcmResubmissionReceipt> {
    const raw = await transport.post(`/api/v1/case-import/hcm/reviews/${encodeURIComponent(preview.review_identity)}/skip-field/apply`, {
      source_field: preview.source_field, expected_review_version: preview.review_version, preview_fingerprint: preview.preview_fingerprint,
    }, { token: token(), headers: { 'Idempotency-Key': idempotencyKey, 'X-Correlation-ID': idempotencyKey } });
    const receipt = decodePayload(HcmResubmissionReceiptEnvelopeSchema, raw).data;
    if (receipt.review_identity !== preview.review_identity || receipt.case_no !== preview.case_no
      || !receipt.target_fields.includes(`review.skip_field:${preview.source_field}`)) throw new Error('警示略過收據與欄位不一致。');
    return receipt;
  },
  async previewSkip(reviewIdentity: string): Promise<HcmReviewSkipPreview> {
    const raw = await transport.post(`/api/v1/case-import/hcm/reviews/${encodeURIComponent(reviewIdentity)}/skip-missing-reject-reason/preview`, {}, { token: token() });
    return decodePayload(z.object({ data: SkipPreviewSchema }), raw).data;
  },
  async applySkip(preview: HcmReviewSkipPreview, idempotencyKey: string): Promise<HcmResubmissionReceipt> {
    const raw = await transport.post(`/api/v1/case-import/hcm/reviews/${encodeURIComponent(preview.review_identity)}/skip-missing-reject-reason/apply`, {
      expected_review_version: preview.review_version, preview_fingerprint: preview.preview_fingerprint,
    }, { token: token(), headers: { 'Idempotency-Key': idempotencyKey, 'X-Correlation-ID': idempotencyKey } });
    return decodePayload(HcmResubmissionReceiptEnvelopeSchema, raw).data;
  },
  async query(reviewIdentity: string): Promise<HcmReviewState> {
    const raw = await transport.get(`/api/v1/case-import/hcm/reviews/${encodeURIComponent(reviewIdentity)}`, { token: token() });
    return decodePayload(z.object({ data: ReviewStateSchema }), raw).data;
  },
  async current(beforeId?: number, options?: { signal?: AbortSignal }): Promise<HcmCurrentReviews> {
    const raw = await transport.get('/api/v1/case-import/hcm/reviews', { token: token(), params: { limit: 20, before_id: beforeId }, signal: options?.signal });
    return decodePayload(z.object({ data: CurrentReviewsSchema }), raw).data;
  },
  async preview(snapshot: HcmWorkbookSnapshot, reviewIdentity: string): Promise<HcmResubmissionPreview> {
    const body = snapshot.toFormData();
    body.append('review_identity', reviewIdentity);
    const raw = await transport.post('/api/v1/case-import/hcm/resubmissions/preview', body, { token: token(), timeoutMs: 30_000 });
    return decodePayload(HcmResubmissionPreviewEnvelopeSchema, raw).data;
  },

  async apply(snapshot: HcmWorkbookSnapshot, preview: HcmResubmissionPreview, reason: string): Promise<HcmResubmissionReceipt> {
    const body = snapshot.toFormData();
    body.append('review_identity', preview.review_identity);
    body.append('expected_review_version', String(preview.review_version));
    body.append('expected_root_fingerprint', preview.root_fingerprint);
    body.append('reason', reason);
    const nonce = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}`;
    const raw = await transport.post('/api/v1/case-import/hcm/resubmissions/apply', body, {
      token: token(), timeoutMs: 30_000,
      headers: {
        'X-Preview-Fingerprint': preview.preview_fingerprint,
        'Idempotency-Key': `ui-hcm-resubmission-${preview.preview_fingerprint}`,
        'X-Correlation-ID': `ui-hcm-resubmission-${nonce}`,
      },
    });
    return decodePayload(HcmResubmissionReceiptEnvelopeSchema, raw).data;
  },
};
