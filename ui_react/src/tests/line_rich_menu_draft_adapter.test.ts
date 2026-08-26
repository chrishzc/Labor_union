/**
 * File: line_rich_menu_draft_adapter.test.ts
 * Description: 驗證 Rich Menu 草稿 adapter 保留四種 typed action 與空草稿投影。
 */
import { describe, expect, it } from 'vitest';
import { adaptLineRichMenuDraft } from '../adapters/line_rich_menu_draft/line_rich_menu_draft_adapter';
import type { RichMenuDraft } from '../api/line_rich_menu_draft/line_rich_menu_draft_schemas';

const DRAFT: RichMenuDraft = {
  kind: 'rich_menus',
  revision: 6,
  publication_locks: [{
    menu_definition_id: 'customer_menu', configuration_revision: 6,
    state: 'editable', readonly_reason: null,
  }],
  definition: {
    version: 4,
    menus: [{
      id: 'customer_menu',
      name: '客戶服務選單',
      audience_role: 'customer',
      enabled: true,
      selected: true,
      set_as_default: true,
      chat_bar_text: '服務選單',
      buttons: [
        {
          id: 'message_button',
          label: '聯絡客服',
          bounds: { x: 0, y: 0, width: 625, height: 843 },
          action: { type: 'message', text: '我要聯絡客服' },
        },
        {
          id: 'uri_button',
          label: '官方網站',
          bounds: { x: 625, y: 0, width: 625, height: 843 },
          action: { type: 'uri', uri: 'https://example.test/help', uri_source: 'literal' },
        },
        {
          id: 'postback_button',
          label: '案件進度',
          bounds: { x: 1250, y: 0, width: 625, height: 843 },
          action: { type: 'postback', data: 'case_progress' },
        },
        {
          id: 'switch_button',
          label: '切換選單',
          bounds: { x: 1875, y: 0, width: 625, height: 843 },
          action: { type: 'richmenuswitch', data: 'switch', rich_menu_alias_id: 'customer-menu' },
        },
      ],
    }],
  },
};

describe('Rich Menu draft adapter', () => {
  it('保留 message、uri、postback、richmenuswitch 的 typed action 映射', () => {
    const model = adaptLineRichMenuDraft(DRAFT);
    expect(model).toMatchObject({ revision: 6, version: 4, isEmpty: false });
    expect(model.menus[0].buttons.map((button) => button.action)).toEqual([
      { kind: 'message', text: '我要聯絡客服' },
      { kind: 'uri', uri: 'https://example.test/help', uriSource: 'literal' },
      { kind: 'postback', data: 'case_progress' },
      { kind: 'richmenuswitch', data: 'switch', richMenuAliasId: 'customer-menu' },
    ]);
  });

  it('revision 0 的空草稿維持空投影，不合成 menu 或 action', () => {
    expect(adaptLineRichMenuDraft({
      kind: 'rich_menus',
      revision: 0,
      definition: { version: 1, menus: [] },
      publication_locks: [],
    })).toEqual({ revision: 0, version: 1, menus: [], isEmpty: true });
  });
});
