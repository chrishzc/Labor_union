/**
 * File: line_rich_menu_media_schemas.ts
 * Description: 嚴格解碼 Rich Menu 受控背景圖 metadata 清單，並驗證分頁與可選狀態。
 */
import { z } from 'zod';

const DateTimeSchema = z.string().min(1).refine(
  (value) => Number.isFinite(Date.parse(value)),
  '日期時間格式不正確',
);

export const RichMenuMediaAssetSchema = z.object({
  asset_id: z.number().int().positive(),
  menu_definition_id: z.string().min(1).max(100),
  original_filename: z.string().min(1).max(255).nullable(),
  mime_type: z.string().min(1).max(100),
  file_size: z.number().int().positive(),
  sha256: z.string().regex(/^[0-9a-f]{64}$/),
  width: z.number().int().positive(),
  height: z.number().int().positive(),
  created_at: DateTimeSchema,
  deleted_at: DateTimeSchema.nullable(),
  selectable: z.boolean(),
  business_reason: z.string().min(1).max(500).nullable(),
  asset_version: z.string().regex(/^[0-9a-f]{64}$/),
}).strict().superRefine((asset, context) => {
  const active = asset.deleted_at === null;
  if (active !== asset.selectable || active === (asset.business_reason !== null)) {
    context.addIssue({ code: 'custom', message: 'Rich Menu 圖片可選狀態不一致' });
  }
});
export type RichMenuMediaAsset = z.infer<typeof RichMenuMediaAssetSchema>;

export const RichMenuMediaAssetPageSchema = z.object({
  items: z.array(RichMenuMediaAssetSchema),
  page: z.number().int().positive(),
  page_size: z.number().int().min(1).max(100),
  total: z.number().int().nonnegative(),
  total_pages: z.number().int().positive(),
}).strict().superRefine((page, context) => {
  if (
    page.items.length > page.page_size
    || page.items.length > page.total
    || page.total_pages !== Math.max(1, Math.ceil(page.total / page.page_size))
  ) {
    context.addIssue({ code: 'custom', message: 'Rich Menu 圖片分頁彙總不一致' });
  }
});
export type RichMenuMediaAssetPage = z.infer<typeof RichMenuMediaAssetPageSchema>;

export const RichMenuMediaAssetPageEnvelopeSchema = z.object({
  success: z.literal(true),
  message: z.literal('Success'),
  data: RichMenuMediaAssetPageSchema,
  error: z.null(),
}).strict();
