/**
 * File: legacy_api_client_runtime_boundary.test.ts
 * Description: 驗證 legacy import client 只使用瀏覽器 relative /api 邊界。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'

import { requestApply, requestPreview } from '../api/client'


describe('legacy API client runtime boundary', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('Preview 只呼叫 relative /api 路徑', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, message: 'ok', data: {} }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await requestPreview('hcm', new File(['x'], 'x.xlsx'))

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/imports/hcm/preview', expect.any(Object))
  })

  it('Apply 只呼叫 relative /api 路徑', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, message: 'ok', data: {} }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await requestApply('hcm', 'command-key')

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/imports/hcm/apply', expect.any(Object))
  })
})
