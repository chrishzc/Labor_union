import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { operationalRetentionClient } from '../../../../../api/system/operational_retention_client';
import { StorageManagementPage } from '../../../../../pages/StorageManagementPage';


const dashboard = {
  policy_revision: 'operational-retention.v1',
  retention_days: 30 as const,
  sources: [
    {
      source_id: 'knowledge-observations', label: 'AI 客服技術觀測與舊索引',
      storage_kind: 'database' as const, classification: 'eligible' as const,
      current_logical_bytes: 10_000, eligible_count: 3, expired_count: 1,
      oldest_eligible_at_utc: '2026-08-01T00:00:00Z', estimated_reclaimable_bytes: 500,
      high_water_bytes: 20_000, low_water_bytes: 15_000, capacity_status: 'normal' as const,
      blocked_reason: null, last_run_at_utc: null, last_outcome: null,
    },
    {
      source_id: 'managed-logs', label: '受管應用程式 Log',
      storage_kind: 'files' as const, classification: 'blocked-unclassified' as const,
      current_logical_bytes: 0, eligible_count: 0, expired_count: 0,
      oldest_eligible_at_utc: null, estimated_reclaimable_bytes: 0,
      high_water_bytes: null, low_water_bytes: null, capacity_status: 'unconfigured' as const,
      blocked_reason: '尚未設定受管 Log 根目錄', last_run_at_utc: null, last_outcome: null,
    },
  ],
};

describe('儲存空間管理', () => {
  afterEach(() => vi.restoreAllMocks());

  it('顯示 denylist 說明，且必須 Preview 與確認後才 Apply', async () => {
    vi.spyOn(operationalRetentionClient, 'dashboard').mockResolvedValue(dashboard);
    vi.spyOn(operationalRetentionClient, 'preview').mockResolvedValue({
      policy_revision: 'operational-retention.v1', source_id: 'knowledge-observations',
      mode: 'expired', reason: '清理到期技術與營運觀測紀錄',
      previewed_at_utc: '2026-09-09T08:00:00Z', cutoff_at_utc: '2026-08-10T08:00:00Z',
      batch_size: 250, candidate_count: 1, estimated_reclaimable_bytes: 500,
      current_logical_bytes: 10_000, target_low_water_bytes: null,
      preview_fingerprint: 'a'.repeat(64),
    });
    const apply = vi.spyOn(operationalRetentionClient, 'apply').mockResolvedValue({
      idempotency_key: 'retention:test', source_id: 'knowledge-observations', mode: 'expired',
      policy_revision: 'operational-retention.v1', preview_fingerprint: 'a'.repeat(64),
      outcome: 'completed', candidate_count: 1, deleted_count: 1, failed_count: 0,
      deleted_logical_bytes: 500, started_at_utc: '2026-09-09T08:00:00Z',
      finished_at_utc: '2026-09-09T08:00:01Z', correlation_id: 'retention:test',
      error_code: null, replayed: false,
    });

    render(<StorageManagementPage />);

    expect(await screen.findByText('AI 客服技術觀測與舊索引')).toBeInTheDocument();
    expect(screen.getByText(/會員、訂單、財務、合約及正式稽核證據不會被刪除/)).toBeInTheDocument();
    const sourceButtons = screen.getAllByRole('button', { name: '建立清理預覽' });
    expect(sourceButtons[0]).toBeEnabled();
    expect(sourceButtons[1]).toBeDisabled();

    fireEvent.click(sourceButtons[0]);
    fireEvent.click(screen.getByRole('button', { name: '零寫入預覽' }));
    expect(await screen.findByText(/候選：1 筆／檔/)).toBeInTheDocument();
    expect(apply).not.toHaveBeenCalled();

    const applyButton = screen.getByRole('button', { name: '確認清理' });
    expect(applyButton).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(applyButton);

    await waitFor(() => expect(apply).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/刪除 1，失敗 0/)).toBeInTheDocument();
  });
});
