/**
 * File: line_rich_menu_publication_adapter.ts
 * Description: 將 Rich Menu Preview 與 queue 結果映射為去敏且只含 durable 狀態的顯示模型。
 */
import type {
  LineRichMenuPublicationMutation,
  LineRichMenuPublishPreview,
} from '../../api/line_rich_menu_publication/line_rich_menu_publication_schemas';

export interface LineRichMenuPublishPreviewModel {
  previewId: number;
  configurationRevision: string;
  fingerprintSummary: string;
}

export interface LineRichMenuPublicationReceiptModel {
  publicationId: number;
  menuDefinitionId: string;
  configurationRevision: number;
  status: LineRichMenuPublicationMutation['status'];
  statusLabel: string;
  durableNotice: string;
}

function statusLabel(status: LineRichMenuPublicationMutation['status']): string {
  switch (status) {
    case 'draft': return '草稿';
    case 'queued': return '已排入';
    case 'publishing': return '發布中';
    case 'published': return '已發布';
    case 'publish_retryable_failed': return '發布可重試失敗';
    case 'failed': return '失敗';
    case 'rollback_queued': return '已排入回復';
    case 'delete_queued': return '已排入刪除';
    case 'rollback_retryable_failed': return '回復可重試失敗';
    case 'delete_retryable_failed': return '刪除可重試失敗';
    case 'rolled_back': return '已回復';
    case 'deleted': return '已刪除';
  }
}

export function adaptLineRichMenuPublishPreview(
  preview: LineRichMenuPublishPreview
): LineRichMenuPublishPreviewModel {
  return {
    previewId: preview.preview_id,
    configurationRevision: preview.config_revision,
    fingerprintSummary: `${preview.config_fingerprint.slice(0, 8)}…${preview.config_fingerprint.slice(-4)}`,
  };
}

export function adaptLineRichMenuPublicationReceipt(
  mutation: LineRichMenuPublicationMutation
): LineRichMenuPublicationReceiptModel {
  return {
    publicationId: mutation.id,
    menuDefinitionId: mutation.menu_definition_id,
    configurationRevision: mutation.configuration_revision,
    status: mutation.status,
    statusLabel: statusLabel(mutation.status),
    durableNotice: '後端 durable 發布工作已建立；本頁未直接呼叫 LINE provider。',
  };
}
