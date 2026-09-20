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
const CurrentReviewsSchema = z.object({ items: z.array(z.object({ source_id: z.number().int(), review_identity: z.string(), case_no: z.string(), fields: z.array(z.string()), can_correct: z.boolean(), unavailable_reason: z.string().nullable().optional() }).strict()), next_cursor: z.number().int().nullable() }).strict();
export type HcmReviewState = z.infer<typeof ReviewStateSchema>;
export type HcmCurrentReviews = z.infer<typeof CurrentReviewsSchema>;

export const hcmResubmissionClient = {
  async query(reviewIdentity: string): Promise<HcmReviewState> {
    const raw = await transport.get(`/api/v1/case-import/hcm/reviews/${encodeURIComponent(reviewIdentity)}`, { token: token() });
    return decodePayload(z.object({ data: ReviewStateSchema }), raw).data;
  },
  async current(beforeId?: number): Promise<HcmCurrentReviews> {
    const raw = await transport.get('/api/v1/case-import/hcm/reviews', { token: token(), params: { limit: 20, before_id: beforeId } });
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
