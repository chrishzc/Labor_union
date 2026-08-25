/**
 * File: line_identity_runtime_config_client.test.ts
 * Description: 驗證 LIFF runtime config 嚴格解碼、公開 origin 正規化與 fail-closed 行為。
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  getLineIdentityRuntimeConfig,
  LineIdentityRuntimeConfigError,
} from '../api/line_identity/line_identity_runtime_config_client';

afterEach(() => vi.unstubAllGlobals());

function response(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('line identity runtime config client', () => {
  it('接受封閉 envelope 並只回傳 origin', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({
      success: true,
      message: 'Success',
      data: {
        liff_id: '1234567890-example',
        public_base_url: 'https://line-test.example.dev/',
      },
      error: null,
    })));

    await expect(getLineIdentityRuntimeConfig()).resolves.toEqual({
      liff_id: '1234567890-example',
      public_base_url: 'https://line-test.example.dev',
    });
  });

  it('拒絕缺欄位或多欄位的 runtime config', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({
      success: true,
      message: 'Success',
      data: { public_base_url: 'https://line-test.example.dev', unexpected: true },
      error: null,
    })));

    await expect(getLineIdentityRuntimeConfig()).rejects.toMatchObject({
      name: 'LineIdentityRuntimeConfigError',
      message: 'LIFF runtime config 回應不符合封閉契約。',
    });
  });

  it('拒絕帶路徑、憑證或非 HTTP 的公開網址', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({
      success: true,
      message: 'Success',
      data: {
        liff_id: '1234567890-example',
        public_base_url: 'https://user:secret@line-test.example.dev/private',
      },
      error: null,
    })));

    await expect(getLineIdentityRuntimeConfig()).rejects.toBeInstanceOf(
      LineIdentityRuntimeConfigError,
    );
  });
});
