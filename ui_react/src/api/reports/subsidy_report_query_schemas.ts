/**
 * File: subsidy_report_query_schemas.ts
 * Description: 定義季度與年度補助報表server-redacted strict Zod views。
 */
import { z } from 'zod';
const DateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
export const SubsidyReportRowSchema = z.strictObject({ serial_number: z.number().int().positive(), case_no: z.string().min(1), eligibility: z.string(), service_start: DateSchema, service_end: DateSchema, subsidy_hours: z.number().positive(), subsidy_days: z.number().positive(), service_days: z.number().int().positive(), subsidy_amount_ntd: z.number().int().nonnegative(), unit_price_ntd: z.number().int().nonnegative(), employer_name_masked: z.string(), staff_name_masked: z.string(), identity_card_masked: z.string(), address_masked: z.enum(['—', '地址已遮罩']) });
export const SubsidyReportPartitionSchema = z.strictObject({ citizen_kind: z.enum(['general', 'subsidized']), row_count: z.number().int().nonnegative(), total_amount_ntd: z.number().int().nonnegative(), rows: z.array(SubsidyReportRowSchema) });
export const SubsidyReportPreviewSchema = z.strictObject({ period_kind: z.enum(['quarterly', 'annual']), application_year: z.number().int().min(1912), quarter: z.number().int().min(1).max(4).nullable(), generated_at: z.string().datetime({ offset: true }), source_revision: z.string(), total_row_count: z.number().int().nonnegative(), total_amount_ntd: z.number().int().nonnegative(), partitions: z.array(SubsidyReportPartitionSchema) });
export const SubsidyReportResponseSchema = z.strictObject({ success: z.boolean(), message: z.string(), data: SubsidyReportPreviewSchema, error: z.string().nullable().optional() });
export type SubsidyReportPreview = z.infer<typeof SubsidyReportPreviewSchema>;
