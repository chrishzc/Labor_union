/** Shared first-root transport for every management entry. */
import { z } from 'zod';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';

export const setupClient = {
  async status() {
    return decodePayload(z.object({ required: z.boolean() }),
      await transport.get('/api/v1/admin/setup', { cache: 'no-store' }));
  },
  async create(values: { username: string; display_name: string; password: string }) {
    return decodePayload(z.object({ created: z.literal(true), next: z.literal('/admin/') }),
      await transport.post('/api/v1/admin/setup', values));
  },
};
