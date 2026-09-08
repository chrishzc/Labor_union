import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CurrentAnomaliesPage } from '../pages/CurrentAnomaliesPage';
import { currentAnomalyQueryClient } from '../api/anomalies/current_anomaly_query_client';
import { anomalyDetailClient } from '../api/anomalies/anomaly_detail_client';
import { lineNotificationTimelineClient } from '../api/line/notification_timeline_client';
import { lineNotificationManualReplayClient } from '../api/line/notification_manual_replay_client';

const issueKey = `ci_${'b'.repeat(64)}`;

describe('CurrentAnomaliesPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(currentAnomalyQueryClient, 'queryCurrentAnomalies').mockResolvedValue({
      items: [{
        issue_key: issueKey,
        definition_code: 'LINE-006',
        owner_domain: 'line',
        severity: 'warning',
        blocking: false,
        episode_started_at: '2026-08-30T01:00:00Z',
        last_verified_at: '2026-08-30T01:01:00Z',
      }],
      next_cursor: null,
    });
    vi.spyOn(anomalyDetailClient, 'queryCurrentAnomalyRecovery').mockResolvedValue({
      issue_key: issueKey,
      definition_code: 'LINE-006',
      owner_domain: 'line',
      owner_root_type: 'notification_failure',
      subject: { redaction_version: 'anomaly-safe.v1', definition_code: 'LINE-006', fields: [] },
      owner_snapshot_token: 'owner-v1',
      owner_version: 3,
      severity: 'warning',
      blocking: false,
      details_version: 1,
      details: { redaction_version: 'anomaly-safe.v1', definition_code: 'LINE-006', fields: [] },
      episode_started_at: '2026-08-30T01:00:00Z',
      last_verified_at: '2026-08-30T01:01:00Z',
      available_actions: [{
        action_key: 'manual_replay_failed_notification',
        label: '重新發送失敗的LINE通知',
        owning_domain: 'line_notification',
        form_schema_key: 'line_notification.manual_replay.v1',
        source_binding_keys: ['case_no', 'notification_reason', 'source_version'],
        source_bindings: [
          { kind: 'identity', key: 'case_no', value: 'CASE-1' },
          { kind: 'identity', key: 'notification_reason', value: 'recipient_unavailable' },
          { kind: 'version', key: 'source_version', value: 132 },
        ],
        required_operator_inputs: ['reason', 'source_event_id'],
        preview_operation: 'PreviewLineNotificationManualReplay',
        apply_operation: 'ApplyLineNotificationManualReplay',
        required_capability: 'line.config.manage',
        completion_predicate: 'line_notification_failed_sources_have_terminal_replay_successors',
        action_contract_version: 1,
        requires_preview: true,
      }],
    });
    vi.spyOn(lineNotificationTimelineClient, 'query').mockResolvedValue({
      case_no: 'CASE-1',
      records: [{
        source_event_id: 132,
        event_code: 'runtime.alert.review_required',
        reason_code: 'recipient_unavailable',
      }],
    });
    vi.spyOn(lineNotificationManualReplayClient, 'preview').mockResolvedValue({
      source_event_id: 132,
      event_code: 'runtime.alert.review_required',
      historical_silent: false,
      matching_rule_count: 1,
      will_create_new_immutable_source: true,
    });
    vi.spyOn(lineNotificationManualReplayClient, 'apply').mockResolvedValue({
      source_event_id: 132,
      replayed_source_event_id: 201,
    });
  });

  it('renders only current state and performs current detail readback', async () => {
    render(<CurrentAnomaliesPage />);

    const issue = await screen.findByRole('button', { name: /LINE-006/ });
    expect(screen.queryByText(/claimed|resolved|timeline|occurrence/i)).not.toBeInTheDocument();
    fireEvent.click(issue);

    await waitFor(() => expect(anomalyDetailClient.queryCurrentAnomalyRecovery).toHaveBeenCalledWith({ issueKey }));
    expect(await screen.findByText('重新發送失敗的LINE通知')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '檢查重新發送' })).toBeEnabled();
    expect(screen.getAllByText('LINE 管理').length).toBeGreaterThan(0);
    expect(screen.getByText(/資料版本：3/)).not.toBeVisible();
    expect(screen.queryByText(/owner facts|closed owner action|通用 resolve/)).not.toBeInTheDocument();
  });

  it('binds the current issue to the LINE owner Preview and confirmed Apply APIs', async () => {
    render(<CurrentAnomaliesPage />);
    fireEvent.click(await screen.findByRole('button', { name: /LINE-006/ }));
    fireEvent.click(await screen.findByRole('button', { name: '檢查重新發送' }));

    await waitFor(() => expect(lineNotificationTimelineClient.query).toHaveBeenCalledWith('CASE-1'));
    await waitFor(() => expect(lineNotificationManualReplayClient.preview).toHaveBeenCalledWith(132));
    expect(await screen.findByText(/來源事件：132/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('重新發送原因'), {
      target: { value: '已確認收件者設定並重新發送' },
    });
    fireEvent.click(screen.getByRole('checkbox', { name: /我已確認目前收件者與通知規則/ }));
    fireEvent.click(screen.getByRole('button', { name: '確認建立重新發送工作' }));

    await waitFor(() => expect(lineNotificationManualReplayClient.apply).toHaveBeenCalledWith(
      132,
      expect.objectContaining({ reason: '已確認收件者設定並重新發送' }),
    ));
    expect(await screen.findByRole('status')).toHaveTextContent('已建立重新發送來源 201');
  });

  it('maps unexpected list failures to a closed business error', async () => {
    vi.mocked(currentAnomalyQueryClient.queryCurrentAnomalies).mockRejectedValueOnce(new Error('raw database host detail'));
    render(<CurrentAnomaliesPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent('目前異常資料暫時無法使用，請稍後重試。');
    expect(screen.queryByText(/raw database host detail/)).not.toBeInTheDocument();
  });
});
