/**
 * @file runtime_decoder.test.ts
 * @description 驗證 Zod 執行期解碼器，包含結構校驗、型別不符攔截與 BaseResponse 信封解構。
 */
import { describe, it, expect } from 'vitest';
import { z } from 'zod';
import {
  decodePayload,
  decodeEnvelope,
  createBaseResponseSchema,
} from '../api/shared/runtime_decoder';
import { ApiDecodeError, ApiHttpError } from '../api/shared/typed_errors';
import { PerformanceSnapshotSchema } from '../api/system/system_status_schema';

describe('Runtime Decoder (Zod Payload & Envelope Validation)', () => {
  const samplePayload = {
    started_at: '2026-08-09T00:00:00Z',
    request_count: 42,
    average_response_time_ms: 12.5,
    p50_response_time_upper_bound_ms: 10,
    p95_response_time_upper_bound_ms: 25,
    maximum_response_time_ms: 120.0,
  };

  it('應成功解碼完全合規的效能快照資料', () => {
    const decoded = decodePayload(PerformanceSnapshotSchema, samplePayload);
    expect(decoded).toEqual(samplePayload);
    expect(decoded.request_count).toBe(42);
    expect(decoded.average_response_time_ms).toBe(12.5);
  });

  it('應允許冷啟動時之 Null 延遲指標', () => {
    const zeroLoadPayload = {
      started_at: '2026-08-09T00:00:00Z',
      request_count: 0,
      average_response_time_ms: null,
      p50_response_time_upper_bound_ms: null,
      p95_response_time_upper_bound_ms: null,
      maximum_response_time_ms: null,
    };

    const decoded = decodePayload(PerformanceSnapshotSchema, zeroLoadPayload);
    expect(decoded.request_count).toBe(0);
    expect(decoded.average_response_time_ms).toBeNull();
    expect(decoded.maximum_response_time_ms).toBeNull();
  });

  it('缺少必要欄位時應拋出 ApiDecodeError 並標記問題路徑', () => {
    const invalidPayload = {
      average_response_time_ms: 10.0,
      // missing started_at and request_count
    };

    expect(() => decodePayload(PerformanceSnapshotSchema, invalidPayload)).toThrow(
      ApiDecodeError
    );

    try {
      decodePayload(PerformanceSnapshotSchema, invalidPayload);
    } catch (err) {
      const decodeErr = err as ApiDecodeError;
      expect(decodeErr.name).toBe('ApiDecodeError');
      expect(decodeErr.issues.length).toBeGreaterThan(0);
      const paths = decodeErr.issues.map((i) => i.path);
      expect(paths).toContain('started_at');
      expect(paths).toContain('request_count');
    }
  });

  it('型別不符時應拋出 ApiDecodeError (例如 request_count 為字串)', () => {
    const invalidTypePayload = {
      ...samplePayload,
      request_count: 'invalid_count',
    };

    expect(() =>
      decodePayload(PerformanceSnapshotSchema, invalidTypePayload)
    ).toThrow(ApiDecodeError);
  });

  it('數值違反約束條件時應拋出 ApiDecodeError (例如 request_count 小於 0)', () => {
    const negativePayload = {
      ...samplePayload,
      request_count: -5,
    };

    expect(() =>
      decodePayload(PerformanceSnapshotSchema, negativePayload)
    ).toThrow(ApiDecodeError);
  });

  it('應成功解開 BaseResponse 信封並取出內層資料本體', () => {
    const rawEnvelope = {
      success: true,
      message: 'Success',
      data: samplePayload,
      error: null,
    };

    const decoded = decodeEnvelope(PerformanceSnapshotSchema, rawEnvelope);
    expect(decoded).toEqual(samplePayload);
  });

  it('當信封標記 success 為 false 時應拋出業務錯誤', () => {
    const errorEnvelope = {
      success: false,
      message: '伺服器目前維護中',
      data: null,
      error: 'Database locked',
    };

    expect(() => decodeEnvelope(PerformanceSnapshotSchema, errorEnvelope)).toThrow(
      ApiHttpError
    );

    try {
      decodeEnvelope(PerformanceSnapshotSchema, errorEnvelope);
    } catch (err) {
      const httpErr = err as ApiHttpError;
      expect(httpErr.status).toBe(400);
      expect(httpErr.message).toBe('Database locked');
    }
  });

  it('當非 JSON 物件時應拋出 ApiDecodeError', () => {
    expect(() => decodeEnvelope(PerformanceSnapshotSchema, '500 Internal Error')).toThrow(
      ApiDecodeError
    );
    expect(() => decodeEnvelope(PerformanceSnapshotSchema, null)).toThrow(
      ApiDecodeError
    );
    expect(() => decodeEnvelope(PerformanceSnapshotSchema, [1, 2, 3])).toThrow(
      ApiDecodeError
    );
  });

  it('當信封標記 success 為 true 但缺少 data 時應拋出 ApiDecodeError', () => {
    const missingDataEnvelope = {
      success: true,
      message: 'Success',
      data: null,
      error: null,
    };

    expect(() =>
      decodeEnvelope(PerformanceSnapshotSchema, missingDataEnvelope)
    ).toThrow(ApiDecodeError);
  });

  it('createBaseResponseSchema 應正確構建自訂綱要之信封', () => {
    const ItemSchema = z.object({ id: z.string(), count: z.number() });
    const CustomEnvelopeSchema = createBaseResponseSchema(ItemSchema);

    const validEnvelope = {
      success: true,
      message: 'OK',
      data: { id: 'item-1', count: 100 },
      error: null,
    };

    const parsed = CustomEnvelopeSchema.parse(validEnvelope);
    expect(parsed.data?.id).toBe('item-1');
  });
});
