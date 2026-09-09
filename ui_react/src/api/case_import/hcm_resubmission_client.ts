/** Connects an active HCM warning to the controlled full-workbook correction flow. */
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

export const hcmResubmissionClient = {
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
        'Idempotency-Key': `ui-hcm-resubmission-${preview.review_identity}-${nonce}`,
        'X-Correlation-ID': `ui-hcm-resubmission-${nonce}`,
      },
    });
    return decodePayload(HcmResubmissionReceiptEnvelopeSchema, raw).data;
  },
};
