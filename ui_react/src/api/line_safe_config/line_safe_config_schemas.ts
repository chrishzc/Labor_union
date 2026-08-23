/**
 * File: line_safe_config_schemas.ts
 * Description: 定義六種 LINE safe configuration GET 的封閉去敏 Zod 契約。
 */

import { z } from 'zod';

export const LineSafeConfigKindSchema = z.enum([
  'message_templates',
  'message_schedules',
  'rich_menus',
  'liff',
  'customer_service',
  'notification_rules',
]);

export const LineSafeConfigStateSchema = z.enum(['empty', 'configured']);

export const LineSafeConfigSchema = z.strictObject({
  kind: LineSafeConfigKindSchema,
  revision: z.number().int().nonnegative(),
  state: LineSafeConfigStateSchema,
});

export const LineSafeConfigResponseSchema = z.strictObject({
  success: z.literal(true),
  message: z.literal('Success'),
  data: LineSafeConfigSchema,
  error: z.null(),
});

export type LineSafeConfigKind = z.infer<typeof LineSafeConfigKindSchema>;
export type LineSafeConfig = z.infer<typeof LineSafeConfigSchema>;
