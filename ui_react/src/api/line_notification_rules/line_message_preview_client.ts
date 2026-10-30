/** Closed, authenticated read-only message previews; no delivery methods. */
import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { decodePayload } from '../shared/runtime_decoder';

export interface PreviewNode {
  kind: 'text' | 'box' | 'button' | 'separator' | 'image';
  text: string; bold: boolean; size: string; layout: 'horizontal' | 'vertical';
  primary: boolean; action_description: string; children: PreviewNode[];
  image_data?: string;
}
const NodeSchema: z.ZodType<PreviewNode> = z.lazy(() => z.strictObject({
  kind: z.enum(['text', 'box', 'button', 'separator', 'image']), text: z.string(), bold: z.boolean(),
  size: z.string(), layout: z.enum(['horizontal', 'vertical']), primary: z.boolean(),
  action_description: z.string(), children: z.array(NodeSchema),
  image_data: z.string().regex(/^(?:data:image\/png;base64,[A-Za-z0-9+/=]+)?$/).default(''),
}));
const DescriptorSchema = z.strictObject({ id: z.string(), template_id: z.string().nullable(), name: z.string(),
  format: z.enum(['text', 'flex']), requires_case: z.boolean(), requires_staff: z.boolean(), builtin: z.boolean(), allows_draft: z.boolean().default(false) });
const OptionSchema = z.strictObject({ id: z.string(), label: z.string() });
const PageSchema = z.strictObject({ items: z.array(OptionSchema), next_cursor: z.string().nullable() });
const ResultSchema = z.strictObject({ status: z.enum(['ready', 'needs_subject', 'unavailable']), note: z.string(),
  format: z.enum(['text', 'flex']), text: z.string(), bubbles: z.array(NodeSchema), facts: z.array(OptionSchema) });
const envelope = <T extends z.ZodTypeAny>(schema: T) => z.object({ success: z.literal(true), data: schema });
export type PreviewDescriptor = z.infer<typeof DescriptorSchema>;
export type PreviewOption = z.infer<typeof OptionSchema>;
export type PreviewOptionPage = z.infer<typeof PageSchema>;
export type MessagePreviewResult = z.infer<typeof ResultSchema>;
export interface MessagePreviewRequest { id: string; content?: string; data_source?: 'sample' | 'record'; case_no?: string; staff_id?: number }
export interface PreviewQueryOptions { signal?: AbortSignal }
export interface LineMessagePreviewClient {
  catalog(options?: PreviewQueryOptions): Promise<PreviewDescriptor[]>;
  subjects(kind: 'case' | 'staff', search: string, after: string | null, options?: PreviewQueryOptions): Promise<PreviewOptionPage>;
  render(payload: MessagePreviewRequest, options?: PreviewQueryOptions): Promise<MessagePreviewResult>;
}
const root = '/api/v1/line/message-previews';
const auth = (options?: PreviewQueryOptions) => ({ token: sessionClient.getToken() ?? undefined, signal: options?.signal, cache: 'no-store' as const });
export const lineMessagePreviewClient: LineMessagePreviewClient = {
  async catalog(options) { return decodePayload(envelope(z.array(DescriptorSchema)), await transport.get<object>(root + '/catalog', auth(options))).data; },
  async subjects(kind, search, after, options) { return decodePayload(envelope(PageSchema), await transport.get<object>(root + '/subjects', { ...auth(options), params: { kind, search, after } })).data; },
  async render(payload, options) { return decodePayload(envelope(ResultSchema), await transport.post<object>(root + '/preview', payload, auth(options))).data; },
};
