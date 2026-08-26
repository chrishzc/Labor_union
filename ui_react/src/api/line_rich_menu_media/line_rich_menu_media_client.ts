/**
 * File: line_rich_menu_media_client.ts
 * Description: 查詢指定 Rich Menu 草稿可選的受控背景圖 metadata，不取得儲存位置或檔案內容。
 */
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';
import {
  LineConfigurationQueryUnauthenticatedError,
  mapLineConfigurationQueryError,
} from '../line_configuration/line_configuration_query_errors';
import {
  RichMenuMediaAssetPageEnvelopeSchema,
  type RichMenuMediaAssetPage,
} from './line_rich_menu_media_schemas';

export interface RichMenuMediaRequestOptions {
  signal?: AbortSignal;
  baseUrl?: string;
}

export interface LineRichMenuMediaClient {
  list(
    menuDefinitionId: string,
    options?: RichMenuMediaRequestOptions,
  ): Promise<RichMenuMediaAssetPage>;
}

class DefaultLineRichMenuMediaClient implements LineRichMenuMediaClient {
  async list(
    menuDefinitionId: string,
    input?: RichMenuMediaRequestOptions,
  ): Promise<RichMenuMediaAssetPage> {
    const canonicalId = menuDefinitionId.trim();
    if (!canonicalId || canonicalId !== menuDefinitionId) {
      throw new Error('Rich Menu 選單識別不正確。');
    }
    const token = sessionClient.getToken();
    if (!token) throw new LineConfigurationQueryUnauthenticatedError();
    try {
      const raw = await transport.get<object>('/api/v1/line/media-assets/rich-menu', {
        token,
        signal: input?.signal,
        baseUrl: input?.baseUrl,
        timeoutMs: 10_000,
        params: {
          menu_definition_id: canonicalId,
          page: 1,
          page_size: 100,
        },
      });
      const page = decodePayload(RichMenuMediaAssetPageEnvelopeSchema, raw).data;
      if (page.page !== 1 || page.page_size !== 100) {
        throw new Error('Rich Menu 背景圖分頁與查詢不一致。');
      }
      if (page.items.some((item) => item.menu_definition_id !== canonicalId)) {
        throw new Error('Rich Menu 背景圖與目前選單不一致。');
      }
      return page;
    } catch (error) {
      throw mapLineConfigurationQueryError(error);
    }
  }
}

export const lineRichMenuMediaClient: LineRichMenuMediaClient =
  new DefaultLineRichMenuMediaClient();
