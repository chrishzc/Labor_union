/**
 * File: weekly_report_batch_client.ts
 * Description: 營運週報批次結算與指標管理 API 用戶端 (方案 C)，包含 Bearer Token 與 Session 憑證傳遞。
 */
import { sessionClient } from '../auth/session_client';

export interface WeeklyBatchItem {
  id: number;
  year: number;
  week_code: string;
  cutoff_at: string;
  promotion_count: number;
  inquiry_count: number;
  notes: string | null;
  case_count: number;
  created_at: string;
  updated_at: string;
}

export interface UnclosedCaseItem {
  case_no: string;
  applicant_name: string;
  created_at: string | null;
  order_status: string | null;
  service_days: number | null;
  service_hours_per_day: number | null;
}

export interface CloseWeeklyBatchPayload {
  year: number;
  week_code: string;
  promotion_count: number;
  inquiry_count: number;
  case_nos?: string[];
  notes?: string;
}

export interface UpdateWeeklyBatchPayload {
  promotion_count: number;
  inquiry_count: number;
  week_code?: string;
  notes?: string;
}

const API_BASE = '/api/v1/operations-reports/weekly';

function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
  };
  const token = sessionClient.getToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

async function handleResponse<T>(res: Response, fallbackError: string): Promise<T> {
  if (!res.ok) {
    const errorBody = await res.text().catch(() => '');
    let msg = `${fallbackError} (${res.status})`;
    try {
      const parsed = JSON.parse(errorBody);
      if (parsed.detail?.error?.message) {
        msg = parsed.detail.error.message;
      } else if (parsed.message) {
        msg = parsed.message;
      }
    } catch {
      // ignore json parse failure
    }
    throw new Error(msg);
  }
  const json = await res.json();
  return json.data;
}

export async function fetchWeeklyBatches(year: number): Promise<WeeklyBatchItem[]> {
  const res = await fetch(`${API_BASE}/batches?year=${year}`, {
    method: 'GET',
    headers: getAuthHeaders(),
    credentials: 'include',
  });
  const data = await handleResponse<WeeklyBatchItem[]>(res, '無法取得週報批次清單');
  return data || [];
}

export async function fetchUnclosedCases(year?: number): Promise<UnclosedCaseItem[]> {
  const url = year ? `${API_BASE}/unclosed-cases?year=${year}` : `${API_BASE}/unclosed-cases`;
  const res = await fetch(url, {
    method: 'GET',
    headers: getAuthHeaders(),
    credentials: 'include',
  });
  const data = await handleResponse<UnclosedCaseItem[]>(res, '無法取得待結算案件清單');
  return data || [];
}

export async function closeWeeklyBatch(payload: CloseWeeklyBatchPayload): Promise<WeeklyBatchItem> {
  const headers = getAuthHeaders();
  headers['Content-Type'] = 'application/json';
  const res = await fetch(`${API_BASE}/batches`, {
    method: 'POST',
    headers,
    credentials: 'include',
    body: JSON.stringify(payload),
  });
  return handleResponse<WeeklyBatchItem>(res, '週報結算失敗');
}

export async function updateWeeklyBatch(
  batchId: number,
  payload: UpdateWeeklyBatchPayload
): Promise<WeeklyBatchItem> {
  const headers = getAuthHeaders();
  headers['Content-Type'] = 'application/json';
  const res = await fetch(`${API_BASE}/batches/${batchId}`, {
    method: 'PATCH',
    headers,
    credentials: 'include',
    body: JSON.stringify(payload),
  });
  return handleResponse<WeeklyBatchItem>(res, '更新週報指標失敗');
}
