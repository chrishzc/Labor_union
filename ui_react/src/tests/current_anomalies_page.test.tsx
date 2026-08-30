import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CurrentAnomaliesPage } from '../pages/CurrentAnomaliesPage';
import { currentAnomalyQueryClient } from '../api/anomalies/current_anomaly_query_client';
import { anomalyDetailClient } from '../api/anomalies/anomaly_detail_client';

const issueKey = `ci_${'b'.repeat(64)}`;

describe('CurrentAnomaliesPage', () => {
  beforeEach(() => {
    vi.spyOn(currentAnomalyQueryClient, 'queryCurrentAnomalies').mockResolvedValue({
      items: [{
        issue_key: issueKey,
        definition_code: 'SCHEDULE-006',
        owner_domain: 'scheduling',
        severity: 'blocking',
        blocking: true,
        episode_started_at: '2026-08-30T01:00:00Z',
        last_verified_at: '2026-08-30T01:01:00Z',
      }],
      next_cursor: null,
    });
    vi.spyOn(anomalyDetailClient, 'queryAnomalyRecovery').mockResolvedValue({
      issue_key: issueKey,
      definition_code: 'SCHEDULE-006',
      owner_domain: 'scheduling',
      owner_root_type: 'case',
      subject: { redaction_version: 'anomaly-safe.v1', definition_code: 'SCHEDULE-006', fields: [] },
      owner_snapshot_token: 'owner-v1',
      owner_version: 3,
      severity: 'blocking',
      blocking: true,
      details_version: 1,
      details: { redaction_version: 'anomaly-safe.v1', definition_code: 'SCHEDULE-006', fields: [] },
      episode_started_at: '2026-08-30T01:00:00Z',
      last_verified_at: '2026-08-30T01:01:00Z',
      available_actions: [],
    });
  });

  it('renders only current state and performs current detail readback', async () => {
    render(<CurrentAnomaliesPage />);

    const issue = await screen.findByRole('button', { name: /SCHEDULE-006/ });
    expect(screen.queryByText(/claimed|resolved|timeline|occurrence/i)).not.toBeInTheDocument();
    fireEvent.click(issue);

    await waitFor(() => expect(anomalyDetailClient.queryAnomalyRecovery).toHaveBeenCalledWith({ issueKey }));
    expect(await screen.findByText(/系統不會以通用 resolve 代替/)).toBeInTheDocument();
  });
});
