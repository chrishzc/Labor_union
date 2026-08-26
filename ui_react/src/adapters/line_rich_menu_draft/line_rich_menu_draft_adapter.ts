/**
 * File: line_rich_menu_draft_adapter.ts
 * Description: 將 Rich Menu 專用草稿 DTO 映射為保留 typed action 的管理端模型。
 */
import type { RichMenuAction } from '../../api/line_configuration/line_configuration_query_schemas';
import type { RichMenuDraft } from '../../api/line_rich_menu_draft/line_rich_menu_draft_schemas';
import {
  adaptLineRichMenuConfiguration,
  type LineRichMenuConfigurationModel,
  type RichMenuActionModel,
} from '../line_configuration/line_configuration_query_adapter';

function adaptAction(action: RichMenuAction): RichMenuActionModel {
  switch (action.type) {
    case 'message':
      return { kind: 'message', text: action.text ?? '' };
    case 'uri':
      return {
        kind: 'uri',
        uri: action.uri ?? '',
        uriSource: action.uri_source ?? 'literal',
      };
    case 'postback':
      return { kind: 'postback', data: action.data ?? '' };
    case 'richmenuswitch':
      return {
        kind: 'richmenuswitch',
        data: action.data ?? '',
        richMenuAliasId: action.rich_menu_alias_id ?? '',
      };
  }
}

export function adaptLineRichMenuDraft(draft: RichMenuDraft): LineRichMenuConfigurationModel {
  const model = adaptLineRichMenuConfiguration(draft);
  if (!('menus' in draft.definition) || draft.definition.menus.length === 0) {
    return { ...model, isEmpty: true };
  }

  const actions = new Map<string, RichMenuAction>();
  for (const menu of draft.definition.menus) {
    for (const button of menu.buttons) actions.set(`${menu.id}\u0000${button.id}`, button.action);
  }

  return {
    ...model,
    menus: model.menus.map((menu) => ({
      ...menu,
      buttons: menu.buttons.map((button) => ({
        ...button,
        action: actions.has(`${menu.id}\u0000${button.id}`)
          ? adaptAction(actions.get(`${menu.id}\u0000${button.id}`)!)
          : undefined,
      })),
    })),
  };
}
