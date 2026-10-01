/** Audited, per-occurrence dismissal through the existing import tracking owner. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';
import type { ImportWarningTaskView } from './anomaly_query_schemas';

const PreviewSchema = z.strictObject({ occurrence_identity: z.string(), expected_version: z.number().int().positive(),
  resulting_status: z.literal('closed'), resulting_version: z.number().int().positive() });
const ReceiptSchema = z.strictObject({ occurrence_identity: z.string(), before_status: z.string(), after_status: z.literal('closed'),
  resulting_version: z.number().int().positive(), receipt_identity: z.string(), correlation_id: z.string(), replayed: z.boolean() });
export type ImportWarningSkipPreview = z.infer<typeof PreviewSchema>;

function options(idempotencyKey: string) {
  const token = sessionClient.getToken();
  if (!token) throw new Error('請先登入後再處理異常。');
  return { token, headers: { 'Idempotency-Key': idempotencyKey, 'X-Correlation-ID': idempotencyKey } };
}
const body = (expectedVersion: number) => ({ expected_version: expectedVersion, target_status: 'closed',
  reason_code: 'manual_warning_skip', note: '人工確認略過此匯入警示', evidence_reference: null });

export const importWarningSkipClient = {
  async preview(task: ImportWarningTaskView, idempotencyKey: string): Promise<ImportWarningSkipPreview> {
    const raw = await transport.post(`/api/v1/import-warning-tracking/tasks/${encodeURIComponent(task.occurrence_identity)}/preview`,
      body(task.tracking_version), options(idempotencyKey));
    const preview = decodePayload(z.object({ data: PreviewSchema }), raw).data;
    if (preview.occurrence_identity !== task.occurrence_identity || preview.expected_version !== task.tracking_version) throw new Error('警示略過預覽不一致。');
    return preview;
  },
  async apply(preview: ImportWarningSkipPreview, idempotencyKey: string) {
    const raw = await transport.post(`/api/v1/import-warning-tracking/tasks/${encodeURIComponent(preview.occurrence_identity)}/apply`,
      body(preview.expected_version), options(idempotencyKey));
    const receipt = decodePayload(z.object({ data: ReceiptSchema }), raw).data;
    if (receipt.occurrence_identity !== preview.occurrence_identity || receipt.resulting_version !== preview.resulting_version) throw new Error('警示略過收據不一致。');
    return receipt;
  },
};
