/**
 * File: line_safe_config_adapter.ts
 * Description: 將 LINE safe configuration DTO 映射為不含 definition 與 provider 資料的顯示模型。
 */

import { LineSafeConfigSchema, type LineSafeConfigKind } from '../../api/line_safe_config/line_safe_config_schemas';

export interface LineSafeConfigModel {
  kind: LineSafeConfigKind;
  kindLabel: string;
  revision: number;
  state: 'empty' | 'configured';
  stateLabel: string;
}

function kindLabel(kind: LineSafeConfigKind): string {
  switch (kind) {
    case 'message_templates': return '訊息範本';
    case 'message_schedules': return '訊息排程';
    case 'rich_menus': return 'Rich Menu';
    case 'liff': return 'LIFF';
    case 'customer_service': return '客服設定';
    case 'notification_rules': return '通知規則';
  }
}

export function adaptLineSafeConfig(source: unknown): LineSafeConfigModel {
  const value = LineSafeConfigSchema.parse(source);
  return {
    kind: value.kind,
    kindLabel: kindLabel(value.kind),
    revision: value.revision,
    state: value.state,
    stateLabel: value.state === 'configured' ? '已設定' : '尚無設定',
  };
}
