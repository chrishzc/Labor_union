/**
 * File: data_browser_query_schemas.ts
 * Description: 六來源 masked Data Browser GET 的 strict Zod 契約。
 */
import { z } from 'zod';

export const DataBrowserSourceIdSchema = z.enum([
  'orders',
  'clients',
  'staff',
  'beclass_intake',
  'hcm_review',
  'bank_facts',
]);
export type DataBrowserSourceId = z.infer<typeof DataBrowserSourceIdSchema>;

export const DataBrowserPresentationSchema = z.enum([
  'text',
  'date',
  'datetime',
  'integer',
  'decimal',
  'status',
  'masked',
]);

export const DataBrowserMaskedCellSchema = z
  .object({
    field_id: z.string().min(1).max(100),
    label: z.string().min(1).max(100),
    value: z.union([z.string(), z.number(), z.boolean(), z.null()]),
    presentation: DataBrowserPresentationSchema,
  })
  .strict();
export type DataBrowserMaskedCell = z.infer<typeof DataBrowserMaskedCellSchema>;

export const DataBrowserMaskedRowSchema = z
  .object({
    source_id: DataBrowserSourceIdSchema,
    row_identity: z.string().min(1).max(191),
    display_title: z.string().min(1).max(300),
    summary_cells: z.array(DataBrowserMaskedCellSchema),
    detail_cells: z.array(DataBrowserMaskedCellSchema),
    recorded_at: z.string().nullable(),
    source_actor_label: z.string().nullable(),
    version_identity: z.string().regex(/^[0-9a-f]{64}$/),
  })
  .strict();
export type DataBrowserMaskedRow = z.infer<typeof DataBrowserMaskedRowSchema>;

export const DataBrowserMaskedPageSchema = z
  .object({
    source_id: DataBrowserSourceIdSchema,
    items: z.array(DataBrowserMaskedRowSchema),
    next_cursor: z.string().min(1).nullable(),
  })
  .strict();
export type DataBrowserMaskedPage = z.infer<typeof DataBrowserMaskedPageSchema>;

export const DataBrowserMaskedPageEnvelopeSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: DataBrowserMaskedPageSchema,
    error: z.string().nullable().optional(),
  })
  .strict();
