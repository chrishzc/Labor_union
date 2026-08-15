/**
 * Typed API Client for Lobar Union Backend (FastAPI)
 * Handles REST HTTP communication, Preview (zero-write), and Apply (fresh-validate)
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  commandKey?: string;
}

export interface PreviewResult {
  categoryId: string;
  totalRows: number;
  acceptedRows: number;
  reviewRows: number;
  conflictRows: number;
  previewSummary: string;
}

export interface ApplyResult {
  categoryId: string;
  commandKey: string;
  status: 'applied' | 'replayed' | 'conflict' | 'error';
  message: string;
  appliedCount: number;
}

export async function requestPreview(categoryId: string, file: File): Promise<ApiResponse<PreviewResult>> {
  try {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE_URL}/api/v1/imports/${categoryId}/preview`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorData.detail || `Preview failed with status ${response.status}`,
      };
    }

    const data: PreviewResult = await response.json();
    return { success: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Network error during preview';
    return { success: false, error: message };
  }
}

export async function requestApply(categoryId: string, commandKey: string): Promise<ApiResponse<ApplyResult>> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/imports/${categoryId}/apply`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ command_key: commandKey }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      return {
        success: false,
        error: errorData.detail || `Apply failed with status ${response.status}`,
      };
    }

    const data: ApplyResult = await response.json();
    return { success: true, data };
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Network error during apply';
    return { success: false, error: message };
  }
}
