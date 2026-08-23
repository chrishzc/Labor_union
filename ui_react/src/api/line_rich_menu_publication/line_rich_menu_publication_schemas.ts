/**
 * File: line_rich_menu_publication_schemas.ts
 * Description: 定義 Rich Menu 發布 Preview、queue 與 retry 的嚴格請求與回應契約。
 */
import { z } from 'zod';
import { LineRichMenuPublicationStatusSchema } from '../line_configuration/line_configuration_query_schemas';

const OperationIdentitySchema = z.string().trim().min(1).max(191);
const ReasonSchema = z.string().trim().min(1).max(500);

export const LineRichMenuPublishPreviewSchema = z
  .object({
    preview_id: z.number().int().positive(),
    config_revision: z.string().regex(/^(0|[1-9][0-9]*)$/).max(20),
    config_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
  })
  .strict();
export type LineRichMenuPublishPreview = z.infer<
  typeof LineRichMenuPublishPreviewSchema
>;

export const LineRichMenuPublishRequestSchema = z
  .object({
    preview_id: z.number().int().positive(),
    reason: ReasonSchema,
    idempotency_key: OperationIdentitySchema,
    correlation_id: OperationIdentitySchema,
  })
  .strict();
export type LineRichMenuPublishRequest = z.infer<
  typeof LineRichMenuPublishRequestSchema
>;

export const LineRichMenuRetryRequestSchema = z
  .object({
    reason: ReasonSchema,
    idempotency_key: OperationIdentitySchema,
    correlation_id: OperationIdentitySchema,
  })
  .strict();
export type LineRichMenuRetryRequest = z.infer<
  typeof LineRichMenuRetryRequestSchema
>;

export const LineRichMenuPublicationMutationSchema = z
  .object({
    id: z.number().int().positive(),
    menu_definition_id: z.string().min(1).max(191),
    configuration_revision: z.number().int().nonnegative(),
    status: LineRichMenuPublicationStatusSchema,
  })
  .strict();
export type LineRichMenuPublicationMutation = z.infer<
  typeof LineRichMenuPublicationMutationSchema
>;

export const LineRichMenuPublishPreviewResponseSchema = z
  .object({
    success: z.literal(true),
    message: z.literal('已確認目前版本的預覽，可再次確認後套用'),
    data: LineRichMenuPublishPreviewSchema,
    error: z.null(),
  })
  .strict();

export const LineRichMenuPublicationQueueResponseSchema = z
  .object({
    success: z.literal(true),
    message: z.literal('Rich Menu 發布工作已建立'),
    data: LineRichMenuPublicationMutationSchema,
    error: z.null(),
  })
  .strict();

export const LineRichMenuPublicationRetryResponseSchema = z
  .object({
    success: z.literal(true),
    message: z.literal('發布工作已重新排入'),
    data: LineRichMenuPublicationMutationSchema,
    error: z.null(),
  })
  .strict();
