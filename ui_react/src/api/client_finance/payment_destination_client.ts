import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';

const DestinationSchema = z.strictObject({ configured: z.boolean(), account_display: z.string().min(1).max(255).nullable(), revision: z.number().int().nonnegative() });
const PreviewSchema = z.strictObject({ current: DestinationSchema, candidate_account_display: z.string().min(1).max(255), expected_revision: z.number().int().nonnegative(), preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/) });
const ReceiptSchema = z.strictObject({ account_display: z.string().min(1).max(255), resulting_revision: z.number().int().positive(), preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/) });
const response = <T extends z.ZodTypeAny>(schema: T) => z.strictObject({ success: z.literal(true), message: z.string(), data: schema, error: z.string().nullable().optional() });

export type PaymentDestination = z.infer<typeof DestinationSchema>;
export type PaymentDestinationPreview = z.infer<typeof PreviewSchema>;

function options(headers: Record<string, string> = {}) {
  const token = sessionClient.getToken();
  if (!token) throw new Error('請先登入。');
  return { token, headers };
}
function decode<T extends z.ZodTypeAny>(schema: T, raw: unknown): z.output<T> {
  return decodePayload(response(schema), raw).data;
}

export const paymentDestinationClient = {
  async query(): Promise<PaymentDestination> {
    return decode(DestinationSchema, await transport.get('/api/v1/client-finance/payment-destination', options()));
  },
  async preview(accountDisplay: string, expectedRevision: number): Promise<PaymentDestinationPreview> {
    return decode(PreviewSchema, await transport.post('/api/v1/client-finance/payment-destination/preview', { account_display: accountDisplay, expected_revision: expectedRevision }, options()));
  },
  async apply(preview: PaymentDestinationPreview, reason: string) {
    return decode(ReceiptSchema, await transport.post('/api/v1/client-finance/payment-destination/apply', {
      account_display: preview.candidate_account_display,
      expected_revision: preview.expected_revision,
      preview_fingerprint: preview.preview_fingerprint,
      reason,
    }, options({ 'Idempotency-Key': `payment-destination-${crypto.randomUUID()}`, 'X-Correlation-ID': `payment-destination-${crypto.randomUUID()}` })));
  },
};

