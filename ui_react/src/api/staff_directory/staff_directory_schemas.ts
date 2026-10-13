/**
 * File: staff_directory_schemas.ts
 * Description: 定義 bounded Staff 摘要頁與成功信封的嚴格 Zod 執行期契約。
 */
import { z } from 'zod';
import { StaffProfileSchema } from '../staff_profile/staff_profile_schemas';
import { StaffServiceProfileSchema, StaffServiceProfileItemSchema } from '../staff/qualification_master_schemas';

export const StaffRosterServiceProfileSchema = StaffServiceProfileSchema.extend({
  cooking_skills: z.array(StaffServiceProfileItemSchema),
});
export type StaffRosterServiceProfile = z.infer<typeof StaffRosterServiceProfileSchema>;

export const StaffDirectorySummarySchema = z
  .object({
    id: z.number().int().positive(),
    union_no: z.string().max(50).nullable().optional(),
    name: z.string().nullable(),
    phone: z.string().nullable(),
    education: z.string().nullable(),
    profile: StaffProfileSchema.optional(),
    service_profile: StaffRosterServiceProfileSchema.optional(),
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

export const StaffRosterResponseSchema = StaffDirectoryResponseSchema.extend({
  data: StaffDirectoryPageSchema.extend({
    items: z.array(StaffDirectorySummarySchema.extend({ profile: StaffProfileSchema, service_profile: StaffRosterServiceProfileSchema })).max(200),
  }),
});
export type StaffDirectoryPage = z.infer<typeof StaffDirectoryPageSchema>;
export type StaffDirectoryResponse = z.infer<typeof StaffDirectoryResponseSchema>;
