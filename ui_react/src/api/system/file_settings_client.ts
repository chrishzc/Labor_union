import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodeEnvelope } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';

const FileSettingsSchema = z.strictObject({
  version: z.number().int().nonnegative(),
  photo_max_bytes: z.number().int().positive(), resume_max_bytes: z.number().int().positive(),
  timeout_seconds: z.number().int().nonnegative(), container_root: z.string().nullable(),
});
export type FileSettings = z.infer<typeof FileSettingsSchema>;
export type FileSettingsInput = Pick<FileSettings, 'photo_max_bytes' | 'resume_max_bytes' | 'timeout_seconds'>;
const options = () => {
  const token = sessionClient.getToken();
  if (!token) throw new Error('請先登入管理介面。');
  return { token, cache: 'no-store' as const };
};
export const fileSettingsClient = {
  async read(): Promise<FileSettings> {
    return decodeEnvelope(FileSettingsSchema, await transport.get('/api/v1/storage/settings', options()));
  },
  async save(input: FileSettingsInput, expectedVersion: number): Promise<FileSettings> {
    return decodeEnvelope(FileSettingsSchema, await transport.request('/api/v1/storage/settings', {
      ...options(), method: 'PUT', body: { ...input, expected_version: expectedVersion },
    }));
  },
};
