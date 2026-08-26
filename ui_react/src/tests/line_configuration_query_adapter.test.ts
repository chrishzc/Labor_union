/**
 * File: line_configuration_query_adapter.test.ts
 * Description: 驗證 LINE 設定 Adapter 只輸出顯示白名單，絕不洩漏 action 或影像敏感欄位。
 */
import { describe, expect, it } from 'vitest';
import {
  LineNotificationRulesCatalogSchema,
  LineRichMenuConfigurationSchema,
} from '../api/line_configuration/line_configuration_query_schemas';
import {
  adaptLineNotificationRulesCatalog,
  adaptLineRichMenuConfiguration,
  adaptLineRichMenuPublicationPage,
} from '../adapters/line_configuration/line_configuration_query_adapter';
import {
  LINE_NOTIFICATION_RULES_CATALOG_FIXTURE,
  LINE_RICH_MENU_CONFIGURATION_FIXTURE,
  LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE,
} from './fixtures/line_configuration_query_fixtures';

describe('LINE configuration query adapter', () => {
  it('notification catalog 正確區分真 empty 與有規則，並只映射規格允許欄位', () => {
    const model = adaptLineNotificationRulesCatalog(LINE_NOTIFICATION_RULES_CATALOG_FIXTURE);
    expect(model).toMatchObject({ revision: 7, isEmpty: false });
    expect(model.rules[0]).toEqual({
      id: 'deposit_notice',
      eventCode: 'deposit_confirmed',
      eventLabel: '訂金確認',
      recipientSelector: 'client',
      recipientLabel: '客戶',
      templateId: 'deposit_message',
      enabled: true,
      scheduleLabel: '立即通知',
      frequencyLabel: '一次',
      predicateLabels: ['需要下廚'],
    });
    expect(adaptLineNotificationRulesCatalog({ revision: 8, definition: {} })).toMatchObject({ isEmpty: true, rules: [] });
  });

  it('Rich Menu adapter 不輸出 URI、postback data、alias 或 image path', () => {
    const model = adaptLineRichMenuConfiguration(LINE_RICH_MENU_CONFIGURATION_FIXTURE);
    expect(model.menus[0]).toEqual({
      id: 'customer_menu', name: '客戶選單', audienceRole: 'customer', audienceRoleLabel: '客戶',
      enabled: true, selected: true, setAsDefault: true, chatBarText: '服務選單',
      width: 2500, height: 843,
      buttons: [{ id: 'case_progress', label: '案件進度', bounds: { x: 0, y: 0, width: 2500, height: 843 } }],
    });
    const rendered = JSON.stringify(model);
    expect(rendered).not.toContain('postback');
    expect(rendered).not.toContain('image_path');
    expect(rendered).not.toContain('rich_menu_alias_id');
  });

  it('僅 materialize Domain 明定的 optional defaults，revision 0 空設定維持真 empty', () => {
    const rules = LineNotificationRulesCatalogSchema.parse({
      revision: 9,
      definition: {
        rules: [{
          id: 'service_end_notice', event_code: 'service_time_checkpoint', recipient_selector: 'case_group',
          template_id: 'service_message', schedule: { kind: 'service_end' },
        }],
      },
    });
    expect(adaptLineNotificationRulesCatalog(rules).rules[0]).toMatchObject({
      enabled: false, frequencyLabel: '一次', predicateLabels: [],
    });
    const configured = LineRichMenuConfigurationSchema.parse({
      kind: 'rich_menus', revision: 9,
      definition: {
        menus: [{
          id: 'staff_menu', name: '月嫂選單', audience_role: 'staff', set_as_default: false,
          chat_bar_text: '月嫂服務',
          buttons: [{
            id: 'schedule', label: '排班', bounds: { x: 0, y: 0, width: 2500, height: 843 },
            action: { type: 'postback', data: 'schedule' },
          }],
        }, {
          id: 'customer_default', name: '客戶選單', audience_role: 'customer', set_as_default: true,
          chat_bar_text: '客戶服務',
          buttons: [{
            id: 'progress', label: '進度', bounds: { x: 0, y: 0, width: 2500, height: 843 },
            action: { type: 'postback', data: 'progress' },
          }],
        }],
      },
    });
    expect(adaptLineRichMenuConfiguration(configured).menus[0]).toMatchObject({
      enabled: true, selected: true, setAsDefault: false, width: 2500, height: 843,
    });
    expect(adaptLineRichMenuConfiguration(LineRichMenuConfigurationSchema.parse({
      kind: 'rich_menus', revision: 0, definition: {},
    }))).toEqual({ revision: 0, version: 1, menus: [], isEmpty: true });
  });

  it('publication status 僅以 server enum 映射，不推導 provider 成功', () => {
    expect(adaptLineRichMenuPublicationPage({
      ...LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE,
      items: [...LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE.items],
    })).toEqual({
      items: [{ id: 19, menuDefinitionId: 'customer_menu', configurationRevision: 8, status: 'published', statusLabel: '已發布' }],
      page: 1, pageSize: 20, total: 1, totalPages: 1, loadedCount: 1, loadedScope: true,
    });
  });
});
