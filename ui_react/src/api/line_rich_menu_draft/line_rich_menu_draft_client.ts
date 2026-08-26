/**
 * File: line_rich_menu_draft_client.ts
 * Description: 呼叫 Rich Menu 專用草稿 Query、Preview 與 Apply，不接 generic configuration 或 provider。
 */
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiHttpError } from '../shared/typed_errors';
import {
  LineConfigurationQueryError,
  LineConfigurationQueryUnauthenticatedError,
  mapLineConfigurationQueryError,
} from '../line_configuration/line_configuration_query_errors';
import {
  RichMenuDraftApplyResultSchema,
  RichMenuDraftPreviewSchema,
  RichMenuDraftSchema,
  createRichMenuDraftEnvelopeSchema,
  type RichMenuDraft,
  type RichMenuDraftApplyRequest,
  type RichMenuDraftApplyResult,
  type RichMenuDraftPreview,
  type RichMenuDraftPreviewRequest,
} from './line_rich_menu_draft_schemas';

export interface RichMenuDraftRequestOptions {
  signal?: AbortSignal;
  baseUrl?: string;
}

export interface LineRichMenuDraftClient {
  query(options?: RichMenuDraftRequestOptions): Promise<RichMenuDraft>;
  preview(request: RichMenuDraftPreviewRequest, options?: RichMenuDraftRequestOptions): Promise<RichMenuDraftPreview>;
  apply(request: RichMenuDraftApplyRequest, options?: RichMenuDraftRequestOptions): Promise<RichMenuDraftApplyResult>;
}

function options(input?: RichMenuDraftRequestOptions): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new LineConfigurationQueryUnauthenticatedError();
  return { token, signal: input?.signal, baseUrl: input?.baseUrl, timeoutMs: 10_000 };
}

async function mapped<T>(operation: () => Promise<T>): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    if (error instanceof ApiHttpError) {
      const message = {
        line_rich_menu_draft_invalid: '按鈕動作內容不符合規則；請確認 LIFF 入口、HTTPS 網址格式，以及訊息、資料或選單代號長度。',
        line_rich_menu_draft_revision_stale: 'Rich Menu 草稿已被更新，請重新整理後再試。',
        line_configuration_revision_conflict: 'Rich Menu 草稿版本已變更，請重新整理後再試。',
        line_rich_menu_draft_preview_fingerprint_mismatch: '預覽內容已過期或變更，請重新預覽並確認。',
        line_rich_menu_media_asset_missing: '選取的背景圖已不存在，請重新選擇。',
        line_rich_menu_media_asset_owner_conflict: '選取的背景圖不屬於目前選單，請重新選擇。',
        line_rich_menu_media_asset_deleted: '選取的背景圖已刪除，請重新選擇。',
        line_rich_menu_media_asset_digest_conflict: '選取的背景圖內容已變更，請重新選擇。',
        line_rich_menu_media_asset_version_conflict: '選取的背景圖版本已變更，請重新選擇。',
        line_rich_menu_media_asset_size_conflict: '選取的背景圖尺寸不符合目前選單，請重新選擇。',
      }[error.code];
      if (message) {
        throw new LineConfigurationQueryError(
          'line_configuration_query_request_invalid',
          message,
          { status: error.status, retryable: error.retryable },
        );
      }
    }
    throw mapLineConfigurationQueryError(error);
  }
}

class DefaultLineRichMenuDraftClient implements LineRichMenuDraftClient {
  query(input?: RichMenuDraftRequestOptions): Promise<RichMenuDraft> {
    return mapped(async () => {
      const raw = await transport.get<object>('/api/v1/line/rich-menus/draft', options(input));
      return decodePayload(createRichMenuDraftEnvelopeSchema(RichMenuDraftSchema), raw).data;
    });
  }

  preview(request: RichMenuDraftPreviewRequest, input?: RichMenuDraftRequestOptions): Promise<RichMenuDraftPreview> {
    return mapped(async () => {
      const raw = await transport.post<object>('/api/v1/line/rich-menus/draft/preview', request, options(input));
      return decodePayload(createRichMenuDraftEnvelopeSchema(RichMenuDraftPreviewSchema), raw).data;
    });
  }

  apply(request: RichMenuDraftApplyRequest, input?: RichMenuDraftRequestOptions): Promise<RichMenuDraftApplyResult> {
    return mapped(async () => {
      const raw = await transport.put<object>('/api/v1/line/rich-menus/draft', request, options(input));
      return decodePayload(createRichMenuDraftEnvelopeSchema(RichMenuDraftApplyResultSchema), raw).data;
    });
  }
}

export const lineRichMenuDraftClient: LineRichMenuDraftClient = new DefaultLineRichMenuDraftClient();
