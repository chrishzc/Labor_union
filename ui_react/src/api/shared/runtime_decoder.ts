/**
 * @file runtime_decoder.ts
 * @description Zod 執行期解碼器，驗證後端 BaseResponse 信封並解構型別化領域資料。
 */
import { z } from 'zod';
import { ApiDecodeError, ApiHttpError, type DecodeIssue } from './typed_errors';

export function createBaseResponseSchema<T extends z.ZodTypeAny>(dataSchema: T) {
  return z.object({
    success: z.boolean().default(true),
    message: z.string().optional().default('Success'),
    data: dataSchema.nullable().optional(),
    error: z.string().nullable().optional(),
  });
}

export function decodePayload<T extends z.ZodTypeAny>(
  schema: T,
  raw: unknown
): z.output<T> {
  const result = schema.safeParse(raw);
  if (!result.success) {
    const issues: DecodeIssue[] = result.error.issues.map((issue) => ({
      path: issue.path.join('.') || '(root)',
      message: issue.message,
      code: issue.code,
    }));
    const formatted = issues.map((i) => `[${i.path}] ${i.message}`).join(', ');
    throw new ApiDecodeError(`資料結構驗證失敗: ${formatted}`, issues, raw);
  }
  return result.data;
}

export function decodeEnvelope<T extends z.ZodTypeAny>(
  dataSchema: T,
  raw: unknown
): z.output<T> {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw new ApiDecodeError('回應內容格式無效，預期為 JSON 物件', [], raw);
  }

  const envelopeSchema = createBaseResponseSchema(dataSchema);
  const envelopeResult = envelopeSchema.safeParse(raw);

  if (!envelopeResult.success) {
    const issues: DecodeIssue[] = envelopeResult.error.issues.map((issue) => ({
      path: issue.path.join('.') || '(root)',
      message: issue.message,
      code: issue.code,
    }));
    const formatted = issues.map((i) => `[${i.path}] ${i.message}`).join(', ');
    throw new ApiDecodeError(`回應信封結構驗證失敗: ${formatted}`, issues, raw);
  }

  const envelope = envelopeResult.data;

  if (!envelope.success) {
    const errorMessage = envelope.error || envelope.message || '後端業務執行失敗';
    throw new ApiHttpError(400, 'BUSINESS_ERROR', errorMessage, false, raw);
  }

  if (envelope.data === null || envelope.data === undefined) {
    throw new ApiDecodeError('回應成功但缺少資料本體 (data 為 null 或 undefined)', [], raw);
  }

  return envelope.data;
}
