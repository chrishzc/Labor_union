/**
 * File: data_browser_query_schemas.ts
 * Description: 六來源 canonical Data Browser GET 的 strict Zod 契約。
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
]);

export const DataBrowserCellSchema = z
  .object({
    field_id: z.string().min(1).max(100),
    label: z.string().min(1).max(100),
    value: z.union([z.string(), z.number(), z.boolean(), z.null()]),
    presentation: DataBrowserPresentationSchema,
  })
  .strict();
export type DataBrowserCell = z.infer<typeof DataBrowserCellSchema>;

export const DataBrowserRowSchema = z
  .object({
    source_id: DataBrowserSourceIdSchema,
    row_identity: z.string().min(1).max(191),
    display_title: z.string().min(1).max(300),
    summary_cells: z.array(DataBrowserCellSchema),
    detail_cells: z.array(DataBrowserCellSchema),
    recorded_at: z.string().nullable(),
    source_actor_label: z.string().nullable(),
    version_identity: z.string().regex(/^[0-9a-f]{64}$/),
  })
  .strict();
export type DataBrowserRow = z.infer<typeof DataBrowserRowSchema>;

export const DataBrowserPageSchema = z
  .object({
    source_id: DataBrowserSourceIdSchema,
    items: z.array(DataBrowserRowSchema),
    next_cursor: z.string().min(1).nullable(),
  })
  .strict();
export type DataBrowserPage = z.infer<typeof DataBrowserPageSchema>;

export const DataBrowserPageEnvelopeSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: DataBrowserPageSchema,
    error: z.string().nullable().optional(),
  })
  .strict();
