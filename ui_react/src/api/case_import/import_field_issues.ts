import { z } from 'zod';
import { sessionClient } from '../auth/session_client';
import { decodePayload } from '../shared/runtime_decoder';
import { transport } from '../shared/transport';

export const ImportFieldIssueSchema = z.strictObject({
  source: z.enum(['hcm', 'client_beclass']),
  owner: z.enum(['client_profile', 'client_beclass', 'order_terms']),
  field: z.string(), source_field: z.string(), code: z.string(), message: z.string(),
  optional_skip_review_identity: z.string().min(1).nullish(),
});
export type ImportFieldIssue = z.infer<typeof ImportFieldIssueSchema>;
const PageSchema = z.object({ data: z.object({
  items: z.array(z.object({ case_no: z.string(), issues: z.array(ImportFieldIssueSchema) })),
  next_page: z.number().int().nullable(), total: z.number().int().nullable().optional(),
}) });
export type ImportFieldIssueCase = z.infer<typeof PageSchema>['data']['items'][number];

export async function loadCurrentImportFieldIssuesForCases(caseNos: readonly string[], options?: { signal?: AbortSignal }): Promise<readonly ImportFieldIssueCase[]> {
  const pending = new Set(caseNos);
  const matches: ImportFieldIssueCase[] = [];
  const token = sessionClient.getToken();
  if (pending.size && !token) throw new Error('請先登入後再讀取進件欄位問題。');
  let page = 1;
  while (pending.size) {
    options?.signal?.throwIfAborted();
    const raw = await transport.get('/api/v1/case-import/field-issues', { token, params: { page, page_size: 100 }, signal: options?.signal });
    const result = decodePayload(PageSchema, raw).data;
    for (const item of result.items) if (pending.delete(item.case_no)) matches.push(item);
    if (result.next_page === null || !pending.size) break;
    if (result.next_page <= page) throw new Error('進件欄位問題分頁無法繼續，請重新讀取。');
    page = result.next_page;
  }
  return matches;
}

export function importFieldIssueHref(caseNo: string, issue?: ImportFieldIssue): string {
  const field = issue && (issue.owner !== 'order_terms' || issue.field === 'requires_cooking') ? issue.field : 'intake';
  return `#clients?case=${encodeURIComponent(caseNo)}&field=${encodeURIComponent(field)}&from=workbench`;
}
