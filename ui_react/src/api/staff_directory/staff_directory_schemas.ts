/**
 * File: staff_directory_schemas.ts
 * Description: 定義 bounded Staff 摘要頁與成功信封的嚴格 Zod 執行期契約。
 */
import { z } from 'zod';

export const StaffDirectorySummarySchema = z
  .object({
    id: z.number().int().positive(),
    name: z.string().nullable(),
    phone: z.string().nullable(),
    education: z.string().nullable(),
  })
  .strict();

export const StaffDirectoryPageSchema = z
  .object({
    items: z.array(StaffDirectorySummarySchema),
    next_cursor: z.number().int().positive().nullable(),
  })
  .strict();

export const StaffDirectoryResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: StaffDirectoryPageSchema,
    error: z.string().nullable().optional(),
  })
  .strict();

export type StaffDirectorySummary = z.infer<typeof StaffDirectorySummarySchema>;
export type StaffDirectoryPage = z.infer<typeof StaffDirectoryPageSchema>;
export type StaffDirectoryResponse = z.infer<typeof StaffDirectoryResponseSchema>;
