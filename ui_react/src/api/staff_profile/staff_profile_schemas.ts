/** Strict schema for the authenticated Staff personal profile endpoint. */
import { z } from 'zod';

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const ISO_DATE_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/;

export const StaffProfileSchema = z.strictObject({
  staff_id: z.number().int().positive(),
  registered_at: z.string().regex(ISO_DATE_TIME).nullable(),
  identity_card: z.string().max(20).nullable(),
  phone: z.string().max(20).nullable(),
  telephone: z.string().max(20).nullable(),
  telephone_extension: z.string().max(10).nullable(),
  email: z.string().max(100).nullable(),
  birthday: z.string().regex(ISO_DATE).nullable(),
  city: z.string().max(50).nullable(),
  zip_code: z.string().max(10).nullable(),
  address: z.string().max(255).nullable(),
  education: z.string().max(255).nullable(),
  emergency_contact_name: z.string().max(100).nullable(),
  emergency_contact_phone: z.string().max(30).nullable(),
  admin_notes: z.string().max(2000).nullable(),
});

export const StaffProfileResponseSchema = z.strictObject({
  success: z.boolean(),
  message: z.string(),
  data: StaffProfileSchema,
  error: z.string().nullable().optional(),
});

export type StaffProfile = z.infer<typeof StaffProfileSchema>;
