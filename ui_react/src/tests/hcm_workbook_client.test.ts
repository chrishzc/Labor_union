/**
 * File: hcm_workbook_client.test.ts
 * Description: 驗證 HCM 真檔快照、multipart Preview、即時 Session 與嚴格失敗邊界。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  HCM_WORKBOOK_PREVIEW_PATH,
  HCM_WORKBOOK_PREVIEW_TIMEOUT_MS,
  HcmWorkbookSnapshot,
  hcmWorkbookPreviewClient,
  previewHcmWorkbook,
} from '../api/case_import/hcm_workbook_client';
import {
  HcmWorkbookContractError,
  HcmWorkbookFileError,
  HcmWorkbookUnauthenticatedError,
} from '../api/case_import/hcm_workbook_errors';
import {
  HcmWorkbookPreviewEnvelopeSchema,
  HcmWorkbookPreviewSchema,
} from '../api/case_import/hcm_workbook_schemas';
import {
  HCM_WORKBOOK_PREVIEW_ENVELOPE_FIXTURE,
  HCM_WORKBOOK_PREVIEW_FIXTURE,
} from './fixtures/hcm_workbook_contract_fixtures';

function response(payload: object, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function setTestSession(token: string): void {
  sessionClient.setSession(token, {
    id: 41,
    username: 'hcm-preview-test',
    display_name: 'HCM 預覽測試',
    role: 'operator',
    linked_line_user_id: null,
    capabilities: [],
    is_root: false,
    access_control_version: 1,
  });
}

async function hcmFile(
  contents: string,
  name = 'current.xlsx'
): Promise<File> {
  return new File([contents], name, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

describe('HCM workbook preview client', () => {
  beforeEach(() => {
    setTestSession('hcm-preview-token-a');
    vi.restoreAllMocks();
  });

  afterEach(() => {
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('以相同 immutable bytes 送出唯一 workbook multipart Preview，並即時取得 bearer', async () => {
    const file = await hcmFile('hcm-current-bytes');
    const snapshot = await HcmWorkbookSnapshot.fromFile(file);
    const envelope = {
      ...HCM_WORKBOOK_PREVIEW_ENVELOPE_FIXTURE,
      data: {
        ...HCM_WORKBOOK_PREVIEW_FIXTURE,
        source_content_digest: snapshot.sha256,
      },
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(envelope))
      .mockResolvedValueOnce(response(envelope));
    globalThis.fetch = fetchMock;

    const preview = await previewHcmWorkbook(snapshot, {
      headers: {
        Authorization: 'Bearer caller-controlled',
        'Content-Type': 'application/json',
        'Idempotency-Key': 'forbidden-on-preview',
        'X-Preview-Fingerprint': 'forbidden-on-preview',
      },
    });

    expect(preview.source_content_digest).toBe(snapshot.sha256);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(HCM_WORKBOOK_PREVIEW_PATH);
    const init = fetchMock.mock.calls[0][1];
    expect(init?.method).toBe('POST');
    expect(init?.body).toBeInstanceOf(FormData);
    const headers = new Headers(init?.headers);
    expect(headers.get('Authorization')).toBe('Bearer hcm-preview-token-a');
    expect(headers.get('Content-Type')).toBeNull();
    expect(headers.get('Idempotency-Key')).toBeNull();
    expect(headers.get('X-Preview-Fingerprint')).toBeNull();
    expect(init?.signal).toBeInstanceOf(AbortSignal);
    const formData = init?.body as FormData;
    expect(Array.from(formData.keys())).toEqual(['workbook']);
    const uploaded = formData.get('workbook');
    expect(uploaded).toBeInstanceOf(File);
    if (!(uploaded instanceof File)) {
      throw new Error('預期 workbook multipart File');
    }
    expect(await uploaded.text()).toBe('hcm-current-bytes');
    expect(uploaded.name).toBe('current.xlsx');
  });

  it('每個 request 即時讀取 memory token，且固定使用 30 秒 timeout', async () => {
    const snapshot = await HcmWorkbookSnapshot.fromFile(await hcmFile('A'));
    const envelope = {
      ...HCM_WORKBOOK_PREVIEW_ENVELOPE_FIXTURE,
      data: { ...HCM_WORKBOOK_PREVIEW_FIXTURE, source_content_digest: snapshot.sha256 },
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(envelope))
      .mockResolvedValueOnce(response(envelope));
    globalThis.fetch = fetchMock;

    await previewHcmWorkbook(snapshot);
    setTestSession('hcm-preview-token-b');
    await previewHcmWorkbook(snapshot);

    const firstHeaders = new Headers(fetchMock.mock.calls[0][1]?.headers);
    const secondHeaders = new Headers(fetchMock.mock.calls[1][1]?.headers);
    expect(firstHeaders.get('Authorization')).toBe('Bearer hcm-preview-token-a');
    expect(secondHeaders.get('Authorization')).toBe('Bearer hcm-preview-token-b');
    expect(HCM_WORKBOOK_PREVIEW_TIMEOUT_MS).toBe(30_000);
  });

  it('缺少 Session 時在送出網路請求前 fail closed', async () => {
    sessionClient.clearSession();
    globalThis.fetch = vi.fn();
    const snapshot = await HcmWorkbookSnapshot.fromFile(await hcmFile('A'));

    await expect(previewHcmWorkbook(snapshot)).rejects.toBeInstanceOf(
      HcmWorkbookUnauthenticatedError
    );
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('外部 signal 已取消時不發送 Preview，並回傳可辨識的取消錯誤', async () => {
    const snapshot = await HcmWorkbookSnapshot.fromFile(await hcmFile('A'));
    const controller = new AbortController();
    controller.abort();
    globalThis.fetch = vi.fn();

    await expect(
      previewHcmWorkbook(snapshot, { signal: controller.signal })
    ).rejects.toMatchObject({ code: 'hcm_preview_aborted' });
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('拒絕副檔名、空檔、超額與 content 讀取漂移，不發送 Preview', async () => {
    await expect(
      HcmWorkbookSnapshot.fromFile(await hcmFile('data', 'current.xls'))
    ).rejects.toBeInstanceOf(HcmWorkbookFileError);
    await expect(
      HcmWorkbookSnapshot.fromFile(await hcmFile('', 'current.xlsx'))
    ).rejects.toBeInstanceOf(HcmWorkbookFileError);
    const oversized = {
      name: 'current.xlsx',
      size: 20 * 1024 * 1024 + 1,
      type: '',
      arrayBuffer: async () => new ArrayBuffer(0),
    } as File;
    await expect(HcmWorkbookSnapshot.fromFile(oversized)).rejects.toBeInstanceOf(
      HcmWorkbookFileError
    );
    const drifting = {
      name: 'current.xlsx',
      size: 2,
      type: '',
      arrayBuffer: async () => new ArrayBuffer(1),
    } as File;
    await expect(HcmWorkbookSnapshot.fromFile(drifting)).rejects.toBeInstanceOf(
      HcmWorkbookFileError
    );
  });

  it('來源 digest 不一致時拒絕 Preview，不暴露為可用 aggregate', async () => {
    const snapshot = await HcmWorkbookSnapshot.fromFile(await hcmFile('digest-a'));
    globalThis.fetch = vi.fn().mockResolvedValue(
      response(HCM_WORKBOOK_PREVIEW_ENVELOPE_FIXTURE)
    );

    await expect(previewHcmWorkbook(snapshot)).rejects.toBeInstanceOf(
      HcmWorkbookContractError
    );
  });

  it('嚴格拒絕 required、primitive、extra、null、hex 與 count drift', () => {
    const invalid = [
      { ...HCM_WORKBOOK_PREVIEW_FIXTURE, ready_count: undefined },
      { ...HCM_WORKBOOK_PREVIEW_FIXTURE, source_row_count: '4' },
      { ...HCM_WORKBOOK_PREVIEW_FIXTURE, unexpected: true },
      { ...HCM_WORKBOOK_PREVIEW_FIXTURE, review_required_count: null },
      { ...HCM_WORKBOOK_PREVIEW_FIXTURE, preview_fingerprint: 'not-hex' },
      { ...HCM_WORKBOOK_PREVIEW_FIXTURE, ready_count: -1 },
      { ...HCM_WORKBOOK_PREVIEW_FIXTURE, ready_count: 1.5 },
    ];
    for (const candidate of invalid) {
      expect(HcmWorkbookPreviewSchema.safeParse(candidate).success).toBe(false);
    }
  });

  it('嚴格拒絕成功信封的 missing、extra、null 與 false success', () => {
    const invalid = [
      { ...HCM_WORKBOOK_PREVIEW_ENVELOPE_FIXTURE, message: undefined },
      { ...HCM_WORKBOOK_PREVIEW_ENVELOPE_FIXTURE, success: false },
      { ...HCM_WORKBOOK_PREVIEW_ENVELOPE_FIXTURE, data: null },
      { ...HCM_WORKBOOK_PREVIEW_ENVELOPE_FIXTURE, unexpected: true },
      {
        ...HCM_WORKBOOK_PREVIEW_ENVELOPE_FIXTURE,
        data: { ...HCM_WORKBOOK_PREVIEW_FIXTURE, unexpected: true },
      },
      { ...HCM_WORKBOOK_PREVIEW_ENVELOPE_FIXTURE, error: 'not-null' },
    ];
    for (const candidate of invalid) {
      expect(
        HcmWorkbookPreviewEnvelopeSchema.safeParse(candidate).success
      ).toBe(false);
    }
  });

  it('沒有 Apply client 或其他 import endpoint，unexpected fetch 不會被吞掉', async () => {
    expect('apply' in hcmWorkbookPreviewClient).toBe(false);
    const snapshot = await HcmWorkbookSnapshot.fromFile(await hcmFile('A'));
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('unexpected fetch'));

    await expect(previewHcmWorkbook(snapshot)).rejects.toThrow(
      'HCM 檔案預覽連線失敗，尚未產生可用預覽。'
    );
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });
});
