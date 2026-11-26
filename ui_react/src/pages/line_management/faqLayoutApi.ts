import { applicationFetch } from '../../api/shared/application_fetch';
import { sessionClient } from '../../api/auth/session_client';

export interface FaqCard {
  category_id: string;
  name: string;
  title: string;
  description: string;
  footer_label: string;
  questions: { qa_id: string; label: string }[];
}

export interface FaqLayout { categories: FaqCard[] }
export interface FaqLayoutState {
  draft_revision: number;
  published_revision: number | null;
  draft_layout: FaqLayout;
  published_layout: FaqLayout | null;
}

export interface FaqPreview {
  view: Pick<FaqCard, 'category_id' | 'title' | 'description' | 'footer_label'> & {
    buttons: { qa_id: string; label: string; question: string; answer: string }[];
  };
  issues: { code: string; field: string; qa_id?: string }[];
}

export interface PublishedFaq {
  qa_id: string;
  version: number;
  question: string;
  answer: string;
  category: string;
  category_id?: string | null;
}

export interface FaqReceipt {
  operation_id: string;
  draft_revision: number;
  published_revision?: number;
  category_id?: string;
}

export class FaqRequestError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly field?: string;

  constructor(status: number, code?: string, field?: string) {
    const messages: Record<string, string> = {
      faq_category_not_published: '尚未發布',
      faq_layout_revision_conflict: '版面已被其他人修改。請核對新版後再編輯。',
      faq_layout_idempotency_conflict: '這個操作鍵已用於其他內容。',
      faq_layout_invalid: '請檢查輸入欄位。卡片發布前須有至少一個有效題目。',
    };
    super((code && messages[code]) || (
      status === 401 ? '登入已失效，請重新登入。'
        : status === 403 ? '目前帳號沒有這項操作權限。'
          : status >= 500 ? '資料來源暫時無法使用，請稍後再試。'
            : `讀取或操作失敗（${status}）。`
    ));
    this.status = status;
    this.code = code;
    this.field = field;
  }
}

export const faqLayoutPath = '/api/v1/line/faq-layout';

export async function faqRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = sessionClient.getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body) headers.set('Content-Type', 'application/json');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await applicationFetch(path, { ...options, headers, signal: controller.signal, credentials: 'include' });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = payload?.detail?.error ?? payload?.detail ?? payload?.error;
      throw new FaqRequestError(response.status, typeof detail === 'string' ? detail : detail?.code, detail?.field_errors?.[0]?.field ?? detail?.field);
    }
    return payload.data as T;
  } finally {
    clearTimeout(timeout);
  }
}

export const getFaqLayout = () => faqRequest<FaqLayoutState>(faqLayoutPath);

export async function getPublishedFaq(): Promise<PublishedFaq[]> {
  const rows: PublishedFaq[] = [];
  let cursor: string | null = null;
  do {
    const query = new URLSearchParams({ limit: '100' });
    if (cursor) query.set('cursor', cursor);
    const page = await faqRequest<{ items: PublishedFaq[]; next_cursor: string | null }>(`/api/v1/line/faq-layout/published-questions?${query}`);
    rows.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor);
  return rows;
}
