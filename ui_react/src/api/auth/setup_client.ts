/** Shared first-root transport for every management entry. */
import { z } from 'zod';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';
import { AdminPasswordChallengeResponseSchema } from './two_step_auth_schemas';

export const setupClient = {
  async status() {
    return decodePayload(z.object({ required: z.boolean(), enrollment_required: z.boolean() }),
      await transport.get('/api/v1/admin/setup', { cache: 'no-store' }));
  },
  async create(values: { username: string; display_name: string; password: string }) {
    return decodePayload(z.object({ created: z.literal(true), enrollment: AdminPasswordChallengeResponseSchema
      .refine(value => value.challenge_type === 'mfa_enrollment', '首次設定必須提供驗證器綁定資料') }),
      await transport.post('/api/v1/admin/setup', values));
  },
};
