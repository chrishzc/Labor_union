import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { decodePayload } from '../shared/runtime_decoder';

export type TemplateKey = 'contract_client_copy' | 'contract_staff_service';
const field = z.strictObject({ key: z.string(), label: z.string(), requiredness: z.enum(['required', 'conditional', 'optional']), applicability: z.string().nullable(), example: z.string() });
const version = z.strictObject({ version_id: z.string(), template_key: z.string(), number: z.number().int(), filename: z.string(), worksheet_name: z.string(), template_sha256: z.string(), mapping_sha256: z.string(), created_by: z.string(), created_at: z.string().nullable() });
const catalog = z.strictObject({ template_key: z.string(), catalog_version: z.number().int().nonnegative(), active_version_id: z.string(), versions: z.array(version), fields: z.array(field) });
const cellStyle = z.strictObject({ font: z.string(), size: z.number(), bold: z.boolean(), italic: z.boolean(), color: z.string(), fill: z.string(), align: z.string(), vertical: z.string(), wrap: z.boolean(), borders: z.record(z.string(), z.string()) });
const cell = z.strictObject({ ref: z.string(), row: z.number().int(), col: z.number().int(), value: z.string(), style: cellStyle });
const image = z.strictObject({ row: z.number().int(), col: z.number().int(), left: z.number(), top: z.number(), width: z.number().positive(), height: z.number().positive(), data_url: z.string().regex(/^data:image\/(png|jpeg);base64,[A-Za-z0-9+/=]+$/) });
const preview = z.strictObject({ filename: z.string(), worksheet_name: z.string(), worksheet_names: z.array(z.string()), sheet: z.strictObject({
  name: z.string(), rows: z.number().int().positive(), columns: z.number().int().positive(), column_widths: z.record(z.string(), z.number()), row_heights: z.record(z.string(), z.number()),
  merges: z.array(z.strictObject({ start_row: z.number().int(), end_row: z.number().int(), start_col: z.number().int(), end_col: z.number().int() })),
  cells: z.array(cell), formula_cells: z.array(z.string()), images: z.array(image),
}), missing_fields: z.array(z.string()), assignments: z.record(z.string(), z.string()), sample_values: z.record(z.string(), z.string()) });
const mutation = z.strictObject({ catalog, version_id: z.string(), replayed: z.boolean() });
export type TemplateCatalog = z.infer<typeof catalog>;
export type TemplatePreview = z.infer<typeof preview>;
export type TemplateField = z.infer<typeof field>;
export type TemplateMutation = z.infer<typeof mutation>;
export type TemplateCell = z.infer<typeof cell>;
export interface TemplateSource { file: File | null; sourceVersionId: string | null; worksheetName: string | null; assignments: Record<string, string> }
export interface TemplateSave extends TemplateSource { expectedVersion: number; commandId: string }
const endpoint = (key: TemplateKey) => `/api/v1/contract-templates/${key}`;
const options = (signal?: AbortSignal) => ({ token: sessionClient.getToken(), signal, cache: 'no-store' as RequestCache });
const form = (source: TemplateSource) => {
  const body = new FormData();
  if (source.file) body.set('document', source.file);
  else if (source.sourceVersionId) body.set('source_version_id', source.sourceVersionId);
  if (source.worksheetName) body.set('worksheet_name', source.worksheetName);
  body.set('assignments', JSON.stringify(source.assignments));
  return body;
};
export const contractTemplatesClient = {
  async query(key: TemplateKey, signal?: AbortSignal): Promise<TemplateCatalog> {
    return decodePayload(z.object({ data: catalog }), await transport.get(endpoint(key), options(signal))).data;
  },
  async read(key: TemplateKey, id: string, signal?: AbortSignal): Promise<TemplatePreview> {
    return decodePayload(z.object({ data: preview }), await transport.get(`${endpoint(key)}/versions/${encodeURIComponent(id)}`, options(signal))).data;
  },
  async inspect(key: TemplateKey, source: TemplateSource, sample = false): Promise<TemplatePreview> {
    const body = form(source); body.set('sample', String(sample));
    return decodePayload(z.object({ data: preview }), await transport.post(`${endpoint(key)}/inspect`, body, { ...options(), timeoutMs: 60000 })).data;
  },
  async save(key: TemplateKey, source: TemplateSave): Promise<TemplateMutation> {
    const body = form(source); body.set('expected_version', String(source.expectedVersion));
    return decodePayload(z.object({ data: mutation }), await transport.post(`${endpoint(key)}/versions`, body, { ...options(), timeoutMs: 60000, headers: { 'Idempotency-Key': source.commandId, 'X-Correlation-ID': source.commandId } })).data;
  },
  async activate(key: TemplateKey, versionId: string, expectedVersion: number, commandId: string): Promise<TemplateMutation> {
    return decodePayload(z.object({ data: mutation }), await transport.post(`${endpoint(key)}/activate`, { version_id: versionId, expected_version: expectedVersion }, { ...options(), headers: { 'Idempotency-Key': commandId, 'X-Correlation-ID': commandId } })).data;
  },
  async receipt(key: TemplateKey, commandId: string): Promise<TemplateMutation | null> {
    return decodePayload(z.object({ data: mutation.nullable() }), await transport.get(`${endpoint(key)}/commands/${encodeURIComponent(commandId)}`, options())).data;
  },
  async download(key: TemplateKey, versionId: string): Promise<Blob> {
    return transport.get<Blob>(`${endpoint(key)}/versions/${encodeURIComponent(versionId)}/download`, { ...options(), responseType: 'blob' });
  },
};
