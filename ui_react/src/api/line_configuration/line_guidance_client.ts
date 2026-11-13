import { sessionClient } from '../auth/session_client';
import { applicationFetch } from '../shared/application_fetch';

interface NavigationCatalogEntry {
  alias: string;
  route_key: string;
  tier: string;
  public_route?: string | null;
  postback_identity?: string | null;
  source_identity: string;
  revision: number;
}

export interface NavigationCatalog {
  revision: number;
  entries: NavigationCatalogEntry[];
}

export interface RouterPreview {
  kind: string;
  source_event_id: string;
  source_identity: string;
  source_revision: number;
  semantic_bucket: string;
  confidence: number;
  score_band: string | null;
  reason_code: string | null;
  route_key: string | null;
  options: string[];
  answer_text: string | null;
  ticket_id: number | null;
  apply_ready: boolean;
}

function sessionHeaders(): Record<string, string> {
  const token = sessionClient.getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function loadLineGuidanceCatalog(): Promise<NavigationCatalog> {
  const response = await applicationFetch('/api/v1/line/ai-events/catalog', {
    headers: sessionHeaders(),
    credentials: 'include',
  });
  if (!response.ok) throw new Error('catalog_readback_failed');
  const payload = await response.json() as { data?: NavigationCatalog };
  if (!payload.data) throw new Error('catalog_readback_failed');
  return payload.data;
}

export async function previewLineGuidance(text: string): Promise<RouterPreview> {
  const response = await applicationFetch('/api/v1/line/ai-events/router/preview', {
    method: 'POST',
    headers: { ...sessionHeaders(), 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      text,
      source_event_id: `studio-router-${Date.now()}`,
      score: 90,
      development_line_user_id: import.meta.env.DEV
        ? import.meta.env.VITE_LINE_DEVELOPMENT_USER_ID ?? '' : '',
      apply_manual_fallback: false,
    }),
  });
  const payload = await response.json() as { data?: RouterPreview; detail?: string };
  if (!response.ok || !payload.data) throw new Error(payload.detail ?? 'router_preview_failed');
  return payload.data;
}
