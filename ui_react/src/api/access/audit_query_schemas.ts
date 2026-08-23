/**
 * File: audit_query_schemas.ts
 * Description: 管理員遮罩稽核清單 GET 的嚴格 Zod 契約。
 */
import { z } from 'zod';

const IsoDateTimeSchema = z.string().refine(
  (value) => !Number.isNaN(Date.parse(value)),
  'occurred_at 必須為 ISO 日期時間',
);

export const AdminAuditMaskedItemSchema = z
  .object({
    audit_id: z.number().int().positive(),
    occurred_at: IsoDateTimeSchema,
    actor_label_masked: z.string().max(100).nullable(),
    action_family: z.enum([
      'authentication',
      'account_security',
      'session',
      'mfa',
      'system',
      'other',
    ]),
    target_label_masked: z.string().max(191).nullable(),
    ip_address_masked: z.string().max(64).nullable(),
    outcome: z.enum(['success', 'denied', 'failed', 'unknown']),
    reason_code: z.string().regex(/^[A-Za-z0-9_.-]+$/).max(100).nullable(),
  })
  .strict();

export type AdminAuditMaskedItem = z.infer<typeof AdminAuditMaskedItemSchema>;

export const AdminAuditDetailFieldSchema = z
  .object({
    key: z.enum(['reason', 'mfa_method', 'account', 'enabled', 'source', 'subject']),
    value_masked: z.string().min(1).max(191),
  })
  .strict();

export const AdminAuditMaskedDetailSchema = AdminAuditMaskedItemSchema.extend({
  details: z.array(AdminAuditDetailFieldSchema),
}).strict();

export type AdminAuditMaskedDetail = z.infer<typeof AdminAuditMaskedDetailSchema>;

export const AdminAuditMaskedPageSchema = z
  .object({
    items: z.array(AdminAuditMaskedItemSchema),
    page: z.number().int().min(1),
    page_size: z.number().int().min(1).max(100),
    total: z.number().int().nonnegative(),
    total_pages: z.number().int().min(1),
  })
  .strict()
  .superRefine((page, context) => {
    const seenIds = new Set<number>();
    page.items.forEach((item, index) => {
      if (seenIds.has(item.audit_id)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['items', index, 'audit_id'],
          message: '稽核分頁不得包含重複 audit_id',
        });
      }
      seenIds.add(item.audit_id);
    });

    const expectedTotalPages = Math.max(1, Math.ceil(page.total / page.page_size));
    if (page.total_pages !== expectedTotalPages) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['total_pages'],
        message: 'total_pages 與 total/page_size 不一致',
      });
    }
    if (page.items.length > page.page_size || page.items.length > page.total) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['items'],
        message: 'items 數量超出分頁 metadata',
      });
    }
  });

export type AdminAuditMaskedPage = z.infer<typeof AdminAuditMaskedPageSchema>;

export const AdminAuditMaskedPageResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: AdminAuditMaskedPageSchema,
    error: z.string().nullable().optional(),
  })
  .strict();

export const AdminAuditMaskedDetailResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: AdminAuditMaskedDetailSchema,
    error: z.string().nullable().optional(),
  })
  .strict();

export interface AuditQueryParams {
  page?: number;
  pageSize?: number;
  actionPrefix?: string;
  actorQuery?: string;
}
