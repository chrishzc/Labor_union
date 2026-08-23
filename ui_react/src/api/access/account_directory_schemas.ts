/**
 * File: account_directory_schemas.ts
 * Description: 帳號清冊唯讀 GET 的嚴格 Zod 契約。
 */
import { z } from 'zod';

export const AccountDirectoryItemSchema = z
  .object({
    id: z.number().int().positive(),
    username: z.string().min(1).max(100),
    display_name: z.string().min(1).max(100),
    enabled: z.boolean(),
    is_root: z.boolean(),
    access_control_version: z.number().int().min(1),
  })
  .strict();

export type AccountDirectoryItem = z.infer<typeof AccountDirectoryItemSchema>;

export const AccountDirectoryResponseSchema = z
  .object({
    success: z.boolean(),
    message: z.string(),
    data: z.array(AccountDirectoryItemSchema),
    error: z.string().nullable().optional(),
  })
  .strict()
  .superRefine((response, context) => {
    const seenIds = new Set<number>();
    response.data.forEach((item, index) => {
      if (seenIds.has(item.id)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['data', index, 'id'],
          message: '帳號清冊不得包含重複 id',
        });
      }
      seenIds.add(item.id);
    });
  });

export type AccountDirectoryResponse = z.infer<typeof AccountDirectoryResponseSchema>;
