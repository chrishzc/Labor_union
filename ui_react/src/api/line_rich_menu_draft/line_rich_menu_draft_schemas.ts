/**
 * File: line_rich_menu_draft_schemas.ts
 * Description: 嚴格解碼 Rich Menu 專用草稿 Query、Preview、Apply 與 readback。
 */
import { z } from 'zod';
import {
  LineRichMenusDefinitionSchema,
  type LineRichMenusDefinition,
} from '../line_configuration/line_configuration_query_schemas';

const EmptyDraftDefinitionSchema = z.object({
  version: z.number().int().positive(),
  menus: z.tuple([]),
}).strict();

export const RichMenuDraftDefinitionSchema = z.union([
  LineRichMenusDefinitionSchema,
  EmptyDraftDefinitionSchema,
]);
export type RichMenuDraftDefinition = LineRichMenusDefinition | z.infer<typeof EmptyDraftDefinitionSchema>;

export const RichMenuDraftPublicationLockSchema = z.object({
  menu_definition_id: z.string().min(1).max(191),
  configuration_revision: z.number().int().nonnegative(),
  state: z.enum(['editable', 'processing', 'published']),
  readonly_reason: z.string().min(1).max(300).nullable(),
}).strict().superRefine((value, context) => {
  if (value.state === 'editable' && value.readonly_reason !== null) {
    context.addIssue({ code: 'custom', message: 'Editable Rich Menu cannot have a readonly reason' });
  }
  if (value.state !== 'editable' && value.readonly_reason === null) {
    context.addIssue({ code: 'custom', message: 'Readonly Rich Menu requires a business reason' });
  }
});

export const RichMenuDraftSchema = z.object({
  kind: z.literal('rich_menus'),
  revision: z.number().int().nonnegative(),
  definition: RichMenuDraftDefinitionSchema,
  publication_locks: z.array(RichMenuDraftPublicationLockSchema),
}).strict().superRefine((value, context) => {
  const menuIds = 'menus' in value.definition
    ? value.definition.menus.map((menu) => menu.id)
    : [];
  const lockIds = value.publication_locks.map((lock) => lock.menu_definition_id);
  if (
    lockIds.length !== menuIds.length
    || new Set(lockIds).size !== lockIds.length
    || menuIds.some((menuId) => !lockIds.includes(menuId))
  ) {
    context.addIssue({ code: 'custom', message: 'Rich Menu publication locks do not match the draft menus' });
  }
  if (value.publication_locks.some((lock) => lock.configuration_revision !== value.revision)) {
    context.addIssue({ code: 'custom', message: 'Rich Menu publication lock revision mismatch' });
  }
});
export type RichMenuDraft = z.infer<typeof RichMenuDraftSchema>;

export const RichMenuDraftPreviewSchema = z.object({
  before_revision: z.number().int().nonnegative(),
  resulting_revision: z.number().int().positive(),
  normalized_definition: RichMenuDraftDefinitionSchema,
  preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/),
}).strict();
export type RichMenuDraftPreview = z.infer<typeof RichMenuDraftPreviewSchema>;

export const RichMenuDraftReceiptSchema = z.object({
  outcome: z.enum(['created', 'existing']),
  committed_revision: z.number().int().positive(),
  receipt_reference: z.string().min(1).max(191),
}).strict();

export const RichMenuDraftApplyResultSchema = z.object({
  receipt: RichMenuDraftReceiptSchema,
  readback: RichMenuDraftSchema,
}).strict();
export type RichMenuDraftApplyResult = z.infer<typeof RichMenuDraftApplyResultSchema>;

export interface RichMenuDraftPreviewRequest {
  expected_revision: number;
  definition: RichMenuDraftDefinition;
}

export interface RichMenuDraftApplyRequest extends RichMenuDraftPreviewRequest {
  preview_fingerprint: string;
  reason: string;
  idempotency_key: string;
  correlation_id: string;
}

export function createRichMenuDraftEnvelopeSchema<T extends z.ZodTypeAny>(data: T) {
  return z.object({
    success: z.literal(true),
    message: z.string(),
    data,
    error: z.null(),
  }).strict();
}
