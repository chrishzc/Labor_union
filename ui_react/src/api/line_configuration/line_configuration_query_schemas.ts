/**
 * File: line_configuration_query_schemas.ts
 * Description: 定義通知規則與 Rich Menu 四個唯讀端點的嚴格 Zod 公開契約。
 */
import { z } from 'zod';

const IdentifierSchema = z.string().regex(/^[a-z][a-z0-9_]{0,63}$/);
const NullableTextSchema = z.string().nullable();

export const LineNotificationEventCodeSchema = z.enum([
  'order_lifecycle_transition',
  'service_time_checkpoint',
  'beclass_completion_changed',
  'deposit_confirmed',
]);
export type LineNotificationEventCode = z.infer<
  typeof LineNotificationEventCodeSchema
>;

export const LineNotificationRecipientSelectorSchema = z.enum([
  'client',
  'assigned_caregiver',
  'case_group',
]);
export type LineNotificationRecipientSelector = z.infer<
  typeof LineNotificationRecipientSelectorSchema
>;

export const LineNotificationPredicateSchema = z.enum([
  'requires_cooking_true',
  'baby_log_missing',
  'beclass_missing',
]);
export type LineNotificationPredicate = z.infer<
  typeof LineNotificationPredicateSchema
>;

export const LineNotificationScheduleSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('immediate') }).strict(),
  z.object({ kind: z.literal('service_end') }).strict(),
  z
    .object({
      kind: z.literal('relative_service_time'),
      offset_seconds: z.number().int().nonnegative(),
    })
    .strict(),
]);
export type LineNotificationSchedule = z.infer<
  typeof LineNotificationScheduleSchema
>;

export const LineNotificationFrequencySchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('once') }).strict(),
  z
    .object({
      kind: z.literal('recurring_bounded'),
      maximum_occurrences: z.number().int().positive(),
      interval_days: z.number().int().positive(),
    })
    .strict(),
]);
export type LineNotificationFrequency = z.infer<
  typeof LineNotificationFrequencySchema
>;

export const LineNotificationRuleSchema = z
  .object({
    id: IdentifierSchema,
    event_code: LineNotificationEventCodeSchema,
    recipient_selector: LineNotificationRecipientSelectorSchema,
    template_id: IdentifierSchema,
    enabled: z.boolean().optional(),
    schedule: LineNotificationScheduleSchema,
    frequency: LineNotificationFrequencySchema.optional(),
    predicates: z.array(LineNotificationPredicateSchema).optional(),
  })
  .strict();
export type LineNotificationRule = z.infer<typeof LineNotificationRuleSchema>;

const EmptyNotificationRulesDefinitionSchema = z.object({}).strict();
const NotificationRulesDefinitionSchema = z
  .object({ rules: z.array(LineNotificationRuleSchema) })
  .strict()
  .superRefine((definition, context) => {
    const ids = new Set<string>();
    for (const rule of definition.rules) {
      if (ids.has(rule.id)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['rules'],
          message: '通知規則 id 不可重複',
        });
      }
      ids.add(rule.id);
    }
  });
export const LineNotificationRulesDefinitionSchema = z.union([
  EmptyNotificationRulesDefinitionSchema,
  NotificationRulesDefinitionSchema,
]);
export type LineNotificationRulesDefinition = z.infer<
  typeof LineNotificationRulesDefinitionSchema
>;

export const LineNotificationRulesCatalogSchema = z
  .object({
    revision: z.number().int().nonnegative(),
    definition: LineNotificationRulesDefinitionSchema,
  })
  .strict();
export type LineNotificationRulesCatalog = z.infer<
  typeof LineNotificationRulesCatalogSchema
>;

const MenuBoundsSchema = z
  .object({
    x: z.number().int().nonnegative(),
    y: z.number().int().nonnegative(),
    width: z.number().int().positive(),
    height: z.number().int().positive(),
  })
  .strict();

export const RichMenuActionSchema = z
  .object({
      type: z.enum(['message', 'uri', 'postback', 'richmenuswitch']),
      text: NullableTextSchema.optional(),
      uri: NullableTextSchema.optional(),
      uri_source: z.enum(['literal', 'liff']).optional(),
      data: NullableTextSchema.optional(),
      rich_menu_alias_id: z
        .string()
        .regex(/^[a-z0-9_-]{1,32}$/)
        .nullable()
        .optional(),
    })
    .strict()
    .superRefine((action, context) => {
      const uriSource = action.uri_source ?? 'literal';
      if (action.type === 'message' && !action.text) {
        context.addIssue({ code: z.ZodIssueCode.custom, path: ['text'], message: 'message action 必須有 text' });
      }
      if (action.type === 'uri' && uriSource === 'literal' && !action.uri) {
        context.addIssue({ code: z.ZodIssueCode.custom, path: ['uri'], message: 'literal uri action 必須有 uri' });
      }
      if (action.type === 'postback' && !action.data) {
        context.addIssue({ code: z.ZodIssueCode.custom, path: ['data'], message: 'postback action 必須有 data' });
      }
      if (action.type === 'richmenuswitch' && !action.rich_menu_alias_id) {
        context.addIssue({ code: z.ZodIssueCode.custom, path: ['rich_menu_alias_id'], message: 'richmenuswitch action 必須有 alias' });
      }
      const has = (value: string | null | undefined) => value !== null && value !== undefined;
      if (action.type !== 'message' && has(action.text)) {
        context.addIssue({ code: z.ZodIssueCode.custom, path: ['text'], message: '此 action kind 不可包含 text' });
      }
      if (action.type !== 'uri' && (has(action.uri) || action.uri_source === 'liff')) {
        context.addIssue({ code: z.ZodIssueCode.custom, path: ['uri'], message: '此 action kind 不可包含 URI' });
      }
      if (!['postback', 'richmenuswitch'].includes(action.type) && has(action.data)) {
        context.addIssue({ code: z.ZodIssueCode.custom, path: ['data'], message: '此 action kind 不可包含 data' });
      }
      if (action.type !== 'richmenuswitch' && has(action.rich_menu_alias_id)) {
        context.addIssue({ code: z.ZodIssueCode.custom, path: ['rich_menu_alias_id'], message: '此 action kind 不可包含 alias' });
      }
    });
export type RichMenuAction = z.infer<typeof RichMenuActionSchema>;

const RichMenuButtonSchema = z
  .object({
    id: IdentifierSchema,
    label: z.string().min(1).max(30),
    text_color: z.string().min(1).optional(),
    background_color: z.string().min(1).optional(),
    border_radius: z.number().int().min(0).max(160).optional(),
    bounds: MenuBoundsSchema,
    action: RichMenuActionSchema,
  })
  .strict();

const RichMenuSizeSchema = z
  .object({
    width: z.literal(2500),
    height: z.union([z.literal(843), z.literal(1686)]),
  })
  .strict();

const RichMenuAppearanceSchema = z
  .object({
    background_color: z.string().min(1).optional(),
    image_mode: z.enum(['generated', 'uploaded']).optional(),
    image_path: NullableTextSchema.optional(),
    image_asset_id: z.number().int().positive().nullable().optional(),
    image_asset_sha256: z.string().regex(/^[0-9a-f]{64}$/).nullable().optional(),
    image_asset_version: z.string().regex(/^[0-9a-f]{64}$/).nullable().optional(),
  })
  .strict()
  .superRefine((appearance, context) => {
    const assetReference = [
      appearance.image_asset_id,
      appearance.image_asset_sha256,
      appearance.image_asset_version,
    ];
    if (appearance.image_mode === 'uploaded') {
      if (appearance.image_path) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['image_path'],
          message: 'uploaded Rich Menu 不接受原始影像路徑',
        });
      }
      if (assetReference.some((value) => value == null)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['image_mode'],
          message: 'uploaded Rich Menu 必須有完整受控影像資產參照',
        });
      }
    } else if (assetReference.some((value) => value != null)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['image_mode'],
        message: 'generated Rich Menu 不接受影像資產參照',
      });
    }
  });

export const RichMenuAudienceRoleSchema = z.enum([
  'customer',
  'staff',
  'union_staff',
  'union_staff_page',
]);
export type RichMenuAudienceRole = z.infer<typeof RichMenuAudienceRoleSchema>;

const RichMenuDefinitionSchema = z
  .object({
    id: IdentifierSchema,
    name: z.string().min(1).max(300),
    audience_role: RichMenuAudienceRoleSchema,
    rich_menu_alias_id: z
      .string()
      .regex(/^[a-z0-9_-]{1,32}$/)
      .nullable()
      .optional(),
    enabled: z.boolean().optional(),
    selected: z.boolean().optional(),
    set_as_default: z.boolean().optional(),
    chat_bar_text: z.string().min(1).max(14),
    size: RichMenuSizeSchema.optional(),
    appearance: RichMenuAppearanceSchema.optional(),
    buttons: z.array(RichMenuButtonSchema).min(1).max(20),
  })
  .strict()
  .superRefine((menu, context) => {
    if (menu.set_as_default === true && menu.audience_role !== 'customer') {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['set_as_default'],
        message: '只有 customer 選單可設為預設',
      });
    }
    const buttonIds = new Set<string>();
    for (const button of menu.buttons) {
      if (buttonIds.has(button.id)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['buttons'],
          message: 'Rich Menu button id 不可重複',
        });
      }
      buttonIds.add(button.id);
      const size = menu.size ?? { width: 2500, height: 843 };
      if (
        button.bounds.x + button.bounds.width > size.width ||
        button.bounds.y + button.bounds.height > size.height
      ) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['buttons'],
          message: 'Rich Menu button 不可超出選單範圍',
        });
      }
    }
  });

export const LineRichMenusDefinitionSchema = z
  .object({
    version: z.number().int().positive().optional(),
    menus: z.array(RichMenuDefinitionSchema),
  })
  .strict()
  .superRefine((definition, context) => {
    const ids = new Set<string>();
    const enabledRoles = new Set<string>();
    let defaults = 0;
    for (const menu of definition.menus) {
      if (ids.has(menu.id)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['menus'],
          message: 'Rich Menu id 不可重複',
        });
      }
      ids.add(menu.id);
      if ((menu.enabled ?? true) && menu.audience_role !== 'union_staff_page') {
        if (enabledRoles.has(menu.audience_role)) {
          context.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['menus'],
            message: '每個主要受眾只能有一個 enabled Rich Menu',
          });
        }
        enabledRoles.add(menu.audience_role);
      }
      if ((menu.enabled ?? true) && (menu.set_as_default ?? false)) defaults += 1;
    }
    if (defaults !== 1) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['menus'],
        message: '必須恰有一個 enabled 預設 Rich Menu',
      });
    }
  });
export type LineRichMenusDefinition = z.infer<
  typeof LineRichMenusDefinitionSchema
>;

const EmptyRichMenuDefinitionSchema = z.object({}).strict();

export const LineRichMenuConfigurationSchema = z
  .object({
    kind: z.literal('rich_menus'),
    revision: z.number().int().nonnegative(),
    definition: z.union([
      EmptyRichMenuDefinitionSchema,
      LineRichMenusDefinitionSchema,
    ]),
  })
  .strict()
  .superRefine((configuration, context) => {
    if (!('menus' in configuration.definition) && configuration.revision !== 0) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['definition'],
        message: '只有 revision 0 可使用空 Rich Menu definition',
      });
    }
  });
export type LineRichMenuConfiguration = z.infer<
  typeof LineRichMenuConfigurationSchema
>;

export const LineRichMenuPublicationStatusSchema = z.enum([
  'draft',
  'queued',
  'publishing',
  'published',
  'publish_retryable_failed',
  'failed',
  'rollback_queued',
  'delete_queued',
  'rollback_retryable_failed',
  'delete_retryable_failed',
  'rolled_back',
  'deleted',
]);
export type LineRichMenuPublicationStatus = z.infer<
  typeof LineRichMenuPublicationStatusSchema
>;

export const LineRichMenuPublicationSchema = z
  .object({
    id: z.number().int().positive(),
    menu_definition_id: z.string().min(1).max(191),
    configuration_revision: z.number().int().nonnegative(),
    status: LineRichMenuPublicationStatusSchema,
  })
  .strict();
export type LineRichMenuPublication = z.infer<
  typeof LineRichMenuPublicationSchema
>;

export const LineRichMenuPublicationPageSchema = z
  .object({
    items: z.array(LineRichMenuPublicationSchema),
    page: z.number().int().positive(),
    page_size: z.number().int().min(1).max(100),
    total: z.number().int().nonnegative(),
    total_pages: z.number().int().positive(),
  })
  .strict();
export type LineRichMenuPublicationPage = z.infer<
  typeof LineRichMenuPublicationPageSchema
>;

export function createLineConfigurationQueryEnvelopeSchema<T extends z.ZodTypeAny>(
  dataSchema: T
) {
  return z
    .object({
      success: z.literal(true),
      message: z.string(),
      data: dataSchema,
      error: z.null(),
    })
    .strict();
}
