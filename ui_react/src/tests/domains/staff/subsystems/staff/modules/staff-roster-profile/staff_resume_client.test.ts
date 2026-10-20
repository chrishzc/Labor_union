import { afterEach, describe, expect, it, vi } from 'vitest';
import { staffResumeClient } from '../../../../../../../api/staff_profile/staff_resume_client';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import { transport } from '../../../../../../../api/shared/transport';

const settings = { photo_max_bytes: 10485760, resume_max_bytes: 50000000, timeout_seconds: 900 };
const envelope = (data: unknown) => ({ success: true, message: 'ok', error: null, data });

afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe('resume file transfers', () => {
  it('keeps the configured timeout active until the PDF body finishes', async () => {
    vi.useFakeTimers();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-session');
    let aborted = false;
    vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit) => {
      if (url.endsWith('/transfer-settings')) return new Response(JSON.stringify(envelope({ ...settings, timeout_seconds: 1 })), { headers: { 'Content-Type': 'application/json' } });
      return { ok: true, status: 200, headers: new Headers({ 'Content-Type': 'application/pdf' }),
        blob: () => new Promise<Blob>((_resolve, reject) => options.signal?.addEventListener('abort', () => {
          aborted = true; reject(new DOMException('aborted', 'AbortError'));
        })),
      };
    }));
    const pending = expect(staffResumeClient.preview('cf_' + '1'.repeat(32))).rejects.toThrow('檔案尚未讀取完成');
    await vi.advanceTimersByTimeAsync(1001);
    await pending;
    expect(aborted).toBe(true);
  });

  it('waits for a slow PDF body when the file timer is disabled', async () => {
    vi.useFakeTimers();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-session');
    let finish: (blob: Blob) => void = () => undefined;
    let signal: AbortSignal | null | undefined;
    vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit) => {
      if (url.endsWith('/transfer-settings')) return new Response(JSON.stringify(envelope({ ...settings, timeout_seconds: 0 })), { headers: { 'Content-Type': 'application/json' } });
      signal = options.signal;
      return { ok: true, status: 200, headers: new Headers({ 'Content-Type': 'application/pdf' }),
        blob: () => new Promise<Blob>(resolve => { finish = resolve; }),
      };
    }));
    const pending = staffResumeClient.preview('cf_' + '1'.repeat(32));
    await vi.advanceTimersByTimeAsync(600000);
    expect(signal?.aborted).toBe(false);
    const blob = new Blob(['%PDF-file'], { type: 'application/pdf' });
    finish(blob);
    expect(await pending).toBe(blob);
  });

  it('uses the server capacity before staging and never sends an oversized PDF', async () => {
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-session');
    vi.spyOn(transport, 'get').mockResolvedValue(envelope({ ...settings, resume_max_bytes: 4 }));
    const post = vi.spyOn(transport, 'post');
    await expect(staffResumeClient.upload(11, new File(['%PDF-1.7'], 'resume.pdf', { type: 'application/pdf' })))
      .rejects.toThrow('本次未上傳');
    expect(post).not.toHaveBeenCalled();
  });

  it('reads PDF bytes with the configured timeout and authenticated no-store transport', async () => {
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-session');
    const blob = new Blob(['%PDF-1.7'], { type: 'application/pdf' });
    const get = vi.spyOn(transport, 'get').mockResolvedValueOnce(envelope(settings)).mockResolvedValueOnce(blob);
    expect(await staffResumeClient.preview('cf_' + '1'.repeat(32))).toBe(blob);
    expect(get).toHaveBeenLastCalledWith(expect.stringContaining('/download'), expect.objectContaining({
      token: 'synthetic-session', timeoutMs: 900000, responseType: 'blob', cache: 'no-store',
    }));
  });

  it('allows a configured disabled timeout and explains missing saved files', async () => {
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('synthetic-session');
    const get = vi.spyOn(transport, 'get').mockResolvedValueOnce(envelope({ ...settings, timeout_seconds: 0 }))
      .mockRejectedValueOnce(new ApiHttpError(404, 'controlled_file_not_found', 'missing', false, null));
    await expect(staffResumeClient.preview('cf_' + '1'.repeat(32))).rejects.toThrow('找不到這份履歷');
    expect(get).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({ timeoutMs: 0 }));
  });
});
