import { beforeEach, expect, it, vi } from 'vitest';
import { importWarningSkipClient } from '../api/anomalies/import_warning_skip_client';
import { sessionClient } from '../api/auth/session_client';
import { transport } from '../api/shared/transport';

beforeEach(() => { vi.restoreAllMocks(); vi.spyOn(sessionClient, 'getToken').mockReturnValue('test-session'); });

it('rejects skip preview for a different occurrence and receipt with an unexpected resulting version', async () => {
  const task = { occurrence_identity: 'occurrence-1', owning_lane: 'hcm' as const, logical_code: 'HCM-LINK-001',
    field_path: '$client_link', subject: 'SYNTH-1', issue_codes: ['hcm_identity:hcm_unique_candidate'], tracking_status: 'open' as const,
    tracking_version: 2, evidence_reference: null, display_message: '疑似已有客戶', navigation_action: 'hcm_import_center' as const };
  const preview = { occurrence_identity: task.occurrence_identity, expected_version: 2, resulting_status: 'closed' as const, resulting_version: 3 };
  const post = vi.spyOn(transport, 'post').mockResolvedValueOnce({ data: { ...preview, occurrence_identity: 'occurrence-2' } });
  await expect(importWarningSkipClient.preview(task, 'key-1')).rejects.toThrow('預覽不一致');
  post.mockResolvedValueOnce({ data: preview });
  await importWarningSkipClient.preview(task, 'key-1');
  post.mockResolvedValueOnce({ data: { occurrence_identity: task.occurrence_identity, before_status: 'open', after_status: 'closed',
    resulting_version: 4, receipt_identity: 'e'.repeat(64), correlation_id: 'corr-1', replayed: false } });
  await expect(importWarningSkipClient.apply(preview, 'key-1')).rejects.toThrow('收據不一致');
  expect(post).toHaveBeenLastCalledWith('/api/v1/import-warning-tracking/tasks/occurrence-1/apply', expect.objectContaining({
    expected_version: 2, reason_code: 'manual_warning_skip', target_status: 'closed',
  }), expect.objectContaining({ headers: { 'Idempotency-Key': 'key-1', 'X-Correlation-ID': 'key-1' } }));
});
