/**
 * File: qualification_master_schemas.ts
 * Description: 定義 Staff qualification master 的 strict GET 回應契約。
 */
import { z } from 'zod';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export const StaffQualificationDateSchema = z.string().regex(ISO_DATE);
export const StaffQualificationAvailabilitySchema = z.enum([
  'available',
  'unavailable',
  'unknown',
  'partial',
]);
export const StaffQualificationSectionKindSchema = z.enum([
  'skills',
  'cooking',
  'certifications',
  'medical',
  'validity',
  'unavailability',
]);

export const StaffQualificationFactSchema = z
  .strictObject({
    code: z.string().min(1).max(191),
    value: z.string().nullable().or(z.boolean()),
    detail: z.string().max(200).nullable(),
    source_identity: z.string().min(1).max(191),
    source_version: z.string().max(191).nullable(),
    valid_from: StaffQualificationDateSchema.nullable(),
    valid_until: StaffQualificationDateSchema.nullable(),
    availability: StaffQualificationAvailabilitySchema,
    availability_reason: z.string().min(1).max(191),
  });

export const StaffQualificationSectionSchema = z
  .strictObject({
    kind: StaffQualificationSectionKindSchema,
    owner: z.string().min(1).max(191),
    availability: StaffQualificationAvailabilitySchema,
    availability_reason: z.string().min(1).max(191),
    source_identity: z.string().max(191).nullable(),
    source_version: z.string().max(191).nullable(),
    items: z.array(StaffQualificationFactSchema),
  });

export const StaffQualificationMasterSchema = z
  .strictObject({
    staff_id: z.number().int().positive(),
    staff_name: z.string().min(1).max(100),
    as_of: StaffQualificationDateSchema,
    overall_availability: StaffQualificationAvailabilitySchema,
    availability_reason: z.string().min(1).max(191),
    sections: z.array(StaffQualificationSectionSchema),
  });

export const StaffQualificationMasterResponseSchema = z
  .strictObject({
    success: z.boolean(),
    message: z.string(),
    data: StaffQualificationMasterSchema.nullable(),
    error: z.string().nullable().optional(),
  });

export type StaffQualificationAvailability = z.infer<typeof StaffQualificationAvailabilitySchema>;
export type StaffQualificationSectionKind = z.infer<typeof StaffQualificationSectionKindSchema>;
export type StaffQualificationFact = z.infer<typeof StaffQualificationFactSchema>;
export type StaffQualificationSection = z.infer<typeof StaffQualificationSectionSchema>;
export type StaffQualificationMaster = z.infer<typeof StaffQualificationMasterSchema>;
