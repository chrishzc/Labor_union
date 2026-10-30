import { z } from 'zod';
import { request } from './shared/transport';
import { sessionClient } from './auth/session_client';

const statusSchema = z.object({
  configured: z.boolean(), enabled: z.boolean(), time: z.string(), version: z.number().int(),
  last_backup: z.string().nullable(),
  last_result: z.object({ status: z.enum(['passed', 'failed']), time: z.string(), message: z.string().nullable().optional() }).nullable(),
});
const responseSchema = z.object({ success: z.literal(true), data: statusSchema });
export type DatabaseBackupStatus = z.infer<typeof statusSchema>;

export const databaseBackupClient = {
  async read(): Promise<DatabaseBackupStatus> {
    return responseSchema.parse(await request('/api/v1/system/database-backup', { token: sessionClient.getToken() })).data;
  },
  async save(time: string, expectedVersion: number): Promise<DatabaseBackupStatus> {
    return responseSchema.parse(await request('/api/v1/system/database-backup/schedule', {
      method: 'PUT', token: sessionClient.getToken(), timeoutMs: 45000,
      body: { time, expected_version: expectedVersion },
    })).data;
  },
};
