import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { transport } from '../shared/transport';
import { decodePayload } from '../shared/runtime_decoder';

const scalar = z.union([z.string(), z.number(), z.boolean(), z.null()]);
const schema = z.strictObject({
  case_no: z.string(), scope: z.string(), assignment_id: z.number().int().positive().nullable(),
  template_key: z.string(), template_version: z.string().regex(/^[0-9a-f]{64}$/),
  owner_fingerprints: z.record(z.string(), z.string()),
  field_values: z.record(z.string(), z.union([scalar, z.array(scalar)])),
  field_states: z.record(z.string(), z.enum(['present', 'missing', 'optional_empty', 'not_applicable', 'unresolved'])),
  field_labels: z.record(z.string(), z.string()).default({}),
  field_keys: z.record(z.string(), z.string()).default({}),
  warnings: z.array(z.string()),
  blockers: z.array(z.string()), preview_fingerprint: z.string().regex(/^[0-9a-f]{64}$/), ready_to_print: z.boolean(),
});
export type ContractFullPreview = z.infer<typeof schema>;

/** POST Preview is zero-write under the existing Contract Signing contract. */
export async function previewContractFields(caseNo: string, scope: 'client' | 'staff', segmentId: number | null, signal: AbortSignal): Promise<ContractFullPreview> {
  if (scope === 'staff' && (segmentId === null || !Number.isSafeInteger(segmentId) || segmentId <= 0)) throw new Error('請先選擇月嫂契約。');
  const target = scope === 'client' ? 'client' : `staff-segments/${segmentId}`;
  const response = decodePayload(z.strictObject({ success: z.literal(true), message: z.string(), data: schema, error: z.null() }),
    await transport.post(`/api/v1/orders/${encodeURIComponent(caseNo)}/contract-signing/${target}/preview`, {}, { token: sessionClient.getToken(), signal }));
  const expectedTemplate = scope === 'client' ? 'contract_client_copy' : 'contract_staff_service';
  if (response.data.case_no !== caseNo || response.data.scope !== scope || response.data.template_key !== expectedTemplate) throw new Error('契約預覽對象不一致。');
  return response.data;
}

/** Open during the click gesture, then print the authenticated, full template. */
export async function openContractPrintView(caseNo: string, scope: 'client' | 'staff', segmentId: number | null, signal: AbortSignal): Promise<void> {
  if (scope === 'staff' && (segmentId === null || !Number.isSafeInteger(segmentId) || segmentId <= 0)) throw new Error('請先選擇月嫂契約。');
  const view = window.open('', '_blank');
  if (!view) throw new Error('瀏覽器已封鎖列印視窗，請允許此網站開啟彈出式視窗後再試。');
  view.opener = null;
  const close = () => view.close();
  signal.addEventListener('abort', close, { once: true });
  try {
    view.document.title = '正在準備契約列印';
    view.document.body.textContent = '正在讀取完整契約…';
    const target = scope === 'client' ? 'client' : `staff-segments/${segmentId}`;
    const blob = await transport.get<Blob>(`/api/v1/orders/${encodeURIComponent(caseNo)}/contract-signing/${target}/print`, {
      token: sessionClient.getToken(), signal, cache: 'no-store', responseType: 'blob',
    });
    if (signal.aborted || view.closed) return;
    if (blob.type.split(';')[0].trim().toLowerCase() !== 'text/html') throw new Error('契約列印內容格式無效。');
    const html = await blob.text();
    if (signal.aborted || view.closed) return;
    // The popup inherits the admin CSP, which disallows inline styles. Apply
    // the authenticated renderer's styles through CSSOM without relaxing CSP.
    const printContent = document.createElement('template');
    // These are the renderer's only styled tags; facts are HTML-escaped. Rename
    // their attributes before parsing so even inert parsing cannot trip CSP.
    printContent.innerHTML = html.replace(/<(?:col|tr|td|img)\b[^>]*>/g, tag => tag.replace(' style=', ' data-contract-css='));
    const styles = Array.from(printContent.content.querySelectorAll('style'), element => {
      element.remove();
      return element.textContent ?? '';
    });
    printContent.content.querySelectorAll('[data-contract-css]').forEach((element, index) => {
      styles.push(`[data-contract-style="${index}"]{${element.getAttribute('data-contract-css')}}`);
      element.removeAttribute('data-contract-css');
      element.setAttribute('data-contract-style', String(index));
    });
    view.document.open();
    view.document.write(`<!doctype html><html lang="zh-Hant">${printContent.innerHTML}</html>`);
    view.document.close();
    const stylesheet = new (view as Window & typeof globalThis).CSSStyleSheet();
    stylesheet.replaceSync(styles.join('\n'));
    view.document.adoptedStyleSheets = [stylesheet];
    view.document.getElementById('print-contract')?.addEventListener('click', () => view.print());
    await view.document.fonts.ready;
    if (signal.aborted || view.closed) return;
    view.focus();
    view.print();
  } catch (error) {
    close();
    throw error;
  } finally {
    signal.removeEventListener('abort', close);
  }
}
