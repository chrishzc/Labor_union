import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';

const option = z.strictObject({ value: z.string(), label: z.string() });
const field = z.strictObject({ id: z.string(), label: z.string(),
  type: z.enum(['text', 'textarea', 'phone', 'email', 'date', 'number', 'single_choice', 'multiple_choice', 'boolean']),
  required: z.boolean(), enabled: z.boolean(), order: z.number().int(), placeholder: z.string(),
  help_text: z.string(), system_field: z.boolean(), options: z.array(option) });
const action = z.strictObject({ id: z.string(), label: z.string(), description: z.string(), icon: z.string(),
  path: z.string(), enabled: z.boolean(), order: z.number().int() });
const page = z.strictObject({ page_type: z.enum(['navigation', 'bind', 'registration']), enabled: z.boolean(),
  title: z.string(), subtitle: z.string(), submit_button: z.string(), success_title: z.string(),
  success_description: z.string(), loading_text: z.string(), content: z.record(z.string(), z.string()),
  actions: z.array(action), fields: z.array(field) });
const view = z.strictObject({ revision: z.string(), page: page.nullable() });
export type NonCitizenLiffPage = z.infer<typeof page>;
export type NonCitizenLiffView = z.infer<typeof view>;
const path = '/api/config/liff/non-citizen';
const options = (revision?: string) => {
  const token = sessionClient.getToken();
  if (!token) throw new Error('請先登入管理後台。');
  return { token, ...(revision ? { headers: { 'If-Match': `"${revision}"` } } : {}) };
};
export const nonCitizenLiffClient = {
  async query(): Promise<NonCitizenLiffView> {
    return decodePayload(view, await transport.get(path, options()));
  },
  async initialize(revision: string): Promise<NonCitizenLiffView> {
    return decodePayload(view, await transport.post(path, {}, options(revision)));
  },
  async save(revision: string, value: NonCitizenLiffPage): Promise<NonCitizenLiffView> {
    return decodePayload(view, await transport.put(path, value, options(revision)));
  },
};
