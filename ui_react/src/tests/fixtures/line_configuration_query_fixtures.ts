/**
 * File: line_configuration_query_fixtures.ts
 * Description: 提供去敏且完整的 LINE 設定唯讀契約測試資料，不作 production fallback。
 */
export const LINE_NOTIFICATION_RULES_CATALOG_FIXTURE = {
  revision: 7,
  definition: {
    rules: [
      {
        id: 'deposit_notice',
        event_code: 'deposit_confirmed',
        recipient_selector: 'client',
        template_id: 'deposit_message',
        enabled: true,
        schedule: { kind: 'immediate' },
        frequency: { kind: 'once' },
        predicates: ['requires_cooking_true'],
      },
    ],
  },
} as const;

export const LINE_NOTIFICATION_RULES_ENVELOPE_FIXTURE = {
  success: true,
  message: 'Success',
  data: LINE_NOTIFICATION_RULES_CATALOG_FIXTURE,
  error: null,
} as const;

export const LINE_RICH_MENU_CONFIGURATION_FIXTURE = {
  kind: 'rich_menus',
  revision: 8,
  definition: {
    version: 2,
    menus: [
      {
        id: 'customer_menu',
        name: '客戶選單',
        audience_role: 'customer',
        rich_menu_alias_id: null,
        enabled: true,
        selected: true,
        set_as_default: true,
        chat_bar_text: '服務選單',
        size: { width: 2500, height: 843 },
        appearance: {
          background_color: '#FFFFFF',
          image_mode: 'generated',
          image_path: null,
          image_asset_id: null,
        },
        buttons: [
          {
            id: 'case_progress',
            label: '案件進度',
            text_color: '#FFFFFF',
            background_color: '#4A90E2',
            border_radius: 0,
            bounds: { x: 0, y: 0, width: 2500, height: 843 },
            action: {
              type: 'postback',
              text: null,
              uri: null,
              uri_source: 'literal',
              data: 'case_progress',
              rich_menu_alias_id: null,
            },
          },
        ],
      },
    ],
  },
} as const;

export const LINE_RICH_MENU_CONFIGURATION_ENVELOPE_FIXTURE = {
  success: true,
  message: 'Success',
  data: LINE_RICH_MENU_CONFIGURATION_FIXTURE,
  error: null,
} as const;

export const LINE_RICH_MENU_PUBLICATION_FIXTURE = {
  id: 19,
  menu_definition_id: 'customer_menu',
  configuration_revision: 8,
  status: 'published',
} as const;

export const LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE = {
  items: [LINE_RICH_MENU_PUBLICATION_FIXTURE],
  page: 1,
  page_size: 20,
  total: 1,
  total_pages: 1,
} as const;

export const LINE_RICH_MENU_PUBLICATION_PAGE_ENVELOPE_FIXTURE = {
  success: true,
  message: 'Success',
  data: LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE,
  error: null,
} as const;

export const LINE_RICH_MENU_PUBLICATION_ENVELOPE_FIXTURE = {
  success: true,
  message: 'Success',
  data: LINE_RICH_MENU_PUBLICATION_FIXTURE,
  error: null,
} as const;
