import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CurrentAnomaliesPage } from '../pages/CurrentAnomaliesPage';
import { currentAnomalyQueryClient } from '../api/anomalies/current_anomaly_query_client';
import { anomalyDetailClient } from '../api/anomalies/anomaly_detail_client';
import { anomalyQueryClient } from '../api/anomalies/anomaly_query_client';
import { lineNotificationTimelineClient } from '../api/line/notification_timeline_client';
import { lineNotificationManualReplayClient, lineNotificationWarningSkipClient } from '../api/line/notification_manual_replay_client';
import { importWarningSkipClient } from '../api/anomalies/import_warning_skip_client';
import { hcmResubmissionClient } from '../api/case_import/hcm_resubmission_client';

const issueKey = `ci_${'b'.repeat(64)}`;

describe('CurrentAnomaliesPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(hcmResubmissionClient, 'current').mockResolvedValue({ items: [], next_cursor: null });
    vi.spyOn(anomalyQueryClient, 'queryImportWarningTasks').mockResolvedValue([]);
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
    expect(screen.queryByText(/資料版本：3/)).not.toBeInTheDocument();
    expect(screen.queryByText(/owner facts|closed owner action|通用 resolve/)).not.toBeInTheDocument();
  });

  it('shows business evidence and keeps raw fields in collapsed technical details', async () => {
    const original = await anomalyDetailClient.queryCurrentAnomalyRecovery({ issueKey });
    vi.mocked(anomalyDetailClient.queryCurrentAnomalyRecovery).mockResolvedValue({
      ...original,
      details: { ...original.details, fields: [
        { key: 'notification_reason', kind: 'text', value: 'recipient_unavailable' },
        { key: 'root_condition_active', kind: 'boolean', value: true },
        { key: 'unresolved_reason_codes', kind: 'code_list', value: ['exact_replay_successor_missing'] },
      ] },
    });
    render(<CurrentAnomaliesPage />);
    fireEvent.click(await screen.findByRole('button', { name: /LINE-006/ }));
    expect(await screen.findByText('目前無法通知收件者')).toBeVisible();
    expect(screen.getByText('問題是否仍存在')).toBeVisible();
    expect(screen.queryByText('recipient_unavailable')).not.toBeInTheDocument();
    expect(screen.queryByText('root_condition_active')).not.toBeInTheDocument();
    expect(screen.queryByText('exact_replay_successor_missing')).not.toBeInTheDocument();
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

  it('shows active HCM reviews and opens the controlled correction in this page', async () => {
    vi.mocked(hcmResubmissionClient.current).mockResolvedValue({ items: [{
      source_id: 2, review_identity: 'review-2', case_no: '115000002',
      fields: ['行動電話'], can_correct: true,
    }], next_cursor: null });
    vi.mocked(anomalyQueryClient.queryImportWarningTasks).mockResolvedValueOnce([]);
    vi.spyOn(anomalyQueryClient, 'queryImportWarningReferral').mockResolvedValue({
      occurrence_identity: 'warning-phone', expected_version: 1, owning_lane: 'hcm',
      logical_code: 'HCM-FIELD-002', field_path: '行動電話', subject: '115000002',
      display_message: '行動電話格式錯誤', navigation_action: 'hcm_import_center',
      action_kind: 'owner_preview_apply', target_command: 'preview_hcm_resubmission', review_identity: 'review-2',
    });

    render(<CurrentAnomaliesPage />);
    expect(await screen.findByText('案件 115000002')).toBeInTheDocument();
    const link = screen.getByRole('link', { name: '前往客戶名冊補資料' });
    expect(link).toHaveAttribute('href', '#clients?case=115000002&field=phone');
    fireEvent.click(screen.getByRole('button', { name: '使用修正版工作簿處理' }));

    expect(await screen.findByText('修正案件 115000002')).toBeInTheDocument();
    expect(anomalyQueryClient.queryImportWarningReferral).not.toHaveBeenCalled();
  });

  it('shows all unresolved fields, skips only the reason after confirmation and re-reads the server', async () => {
    const item = { source_id: 3, review_identity: 'review-3', case_no: '115000003',
      fields: ['預產期/預計服務開始月份', '不符合原因'], can_correct: false };
    vi.mocked(hcmResubmissionClient.current).mockResolvedValueOnce({ items: [item], next_cursor: null })
      .mockResolvedValue({ items: [{ ...item, fields: ['預產期/預計服務開始月份'] }], next_cursor: null });
    vi.spyOn(hcmResubmissionClient, 'previewFieldSkip').mockResolvedValue({ review_identity: item.review_identity,
      case_no: item.case_no, source_field: '不符合原因', review_version: 0, preview_fingerprint: 'a'.repeat(64) });
    const apply = vi.spyOn(hcmResubmissionClient, 'applyFieldSkip').mockResolvedValue({
      event_identity: 'event-3', review_identity: item.review_identity, case_no: item.case_no,
      target_fields: ['review.skip_field:不符合原因'], resulting_review_version: 1, replayed: false,
    });
    render(<CurrentAnomaliesPage />);
    expect(await screen.findByText('預產期/預計服務開始月份待補齊或修正')).toBeVisible();
    expect(screen.getByRole('link', { name: '前往客戶名冊補資料' })).toHaveAttribute('href', '#clients?case=115000003&field=due_month');
    expect(screen.getByRole('link', { name: '補填不符合原因' })).toHaveAttribute('href', '#clients?case=115000003&field=reject_reason');
    fireEvent.click(within(screen.getByText('不符合原因待補齊或修正').closest('.import-warning-field') as HTMLElement).getByRole('button', { name: '略過並解除這項警示' }));
    await screen.findByRole('button', { name: '確認略過並保存紀錄' });
    expect(apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '確認略過並保存紀錄' }));
    await waitFor(() => expect(screen.queryByText('不符合原因待補齊或修正')).not.toBeInTheDocument());
    expect(screen.getByText('預產期/預計服務開始月份待補齊或修正')).toBeVisible();
    expect(apply).toHaveBeenCalledTimes(1);
    expect(hcmResubmissionClient.current).toHaveBeenCalledTimes(2);
  });

  it('keeps the warning when skip Apply fails and does not fake a successful resolution', async () => {
    vi.mocked(hcmResubmissionClient.current).mockResolvedValue({ items: [{ source_id: 3,
      review_identity: 'review-3', case_no: '115000003', fields: ['不符合原因'], can_correct: false }], next_cursor: null });
    vi.spyOn(hcmResubmissionClient, 'previewFieldSkip').mockResolvedValue({ review_identity: 'review-3',
      case_no: '115000003', source_field: '不符合原因', review_version: 0, preview_fingerprint: 'a'.repeat(64) });
    vi.spyOn(hcmResubmissionClient, 'applyFieldSkip').mockRejectedValue({ status: 409 });
    render(<CurrentAnomaliesPage />);
    const field = await screen.findByText('不符合原因待補齊或修正');
    fireEvent.click(within(field.closest('.import-warning-field') as HTMLElement).getByRole('button', { name: '略過並解除這項警示' }));
    fireEvent.click(await screen.findByRole('button', { name: '確認略過並保存紀錄' }));
    await waitFor(() => expect(screen.getAllByRole('alert')[0]).toHaveTextContent('問題資料已變更'));
    expect(screen.getByText('不符合原因待補齊或修正')).toBeVisible();
    expect(screen.queryByText(/已保存人工略過紀錄/)).not.toBeInTheDocument();
  });

  it('maps unexpected list failures to a closed business error', async () => {
    vi.mocked(currentAnomalyQueryClient.queryCurrentAnomalies).mockRejectedValueOnce(new Error('raw database host detail'));
    render(<CurrentAnomaliesPage />);

    expect(await screen.findByRole('alert')).toHaveTextContent('目前異常資料暫時無法使用，請稍後重試。');
    expect(screen.queryByText(/raw database host detail/)).not.toBeInTheDocument();
  });

  it.each(['預產期/預計服務開始月份', '行動電話', '查詢序號(案件編號)'])('allows audited skip for %s without requiring a data correction', async (field) => {
    const review = { source_id: 4, review_identity: 'review-4', case_no: '115000004', fields: [field], can_correct: false };
    vi.mocked(hcmResubmissionClient.current).mockResolvedValueOnce({ items: [review], next_cursor: null })
      .mockResolvedValue({ items: [], next_cursor: null });
    const preview = { review_identity: review.review_identity, case_no: review.case_no, source_field: field,
      review_version: 0, preview_fingerprint: 'c'.repeat(64) };
    vi.spyOn(hcmResubmissionClient, 'previewFieldSkip').mockResolvedValue(preview);
    const apply = vi.spyOn(hcmResubmissionClient, 'applyFieldSkip').mockResolvedValue({ event_identity: 'event-4',
      review_identity: review.review_identity, case_no: review.case_no, target_fields: ['review.skip_field:' + field],
      resulting_review_version: 1, replayed: false });
    render(<CurrentAnomaliesPage />);
    const warning = await screen.findByText(field + '待補齊或修正');
    fireEvent.click(within(warning.closest('.import-warning-field') as HTMLElement).getByRole('button', { name: '略過並解除這項警示' }));
    expect(await screen.findByText('警示：' + field)).toBeVisible();
    expect(apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '確認略過並保存紀錄' }));
    await waitFor(() => expect(screen.queryByText(field + '待補齊或修正')).not.toBeInTheDocument());
    expect(hcmResubmissionClient.previewFieldSkip).toHaveBeenCalledWith('review-4', field);
    expect(apply).toHaveBeenCalledWith(preview, expect.any(String));
  });

  it('keeps same-case import occurrences separate and dismisses only the confirmed occurrence', async () => {
    const first = { occurrence_identity: 'warning-link', owning_lane: 'hcm' as const, logical_code: 'HCM-LINK-001',
      field_path: '$client_link', subject: '115000150', issue_codes: ['hcm_identity:hcm_unique_candidate'],
      tracking_status: 'open' as const, tracking_version: 1, evidence_reference: null,
      display_message: '疑似已有客戶，待確認連結', navigation_action: 'hcm_import_center' as const };
    const second = { ...first, occurrence_identity: 'warning-system', logical_code: 'HCM-SYSTEM-001',
      display_message: '案件初始設定尚未完成' };
    vi.mocked(anomalyQueryClient.queryImportWarningTasks).mockResolvedValueOnce([first, second]).mockResolvedValue([second]);
    const preview = { occurrence_identity: first.occurrence_identity, expected_version: 1,
      resulting_status: 'closed' as const, resulting_version: 2 };
    vi.spyOn(importWarningSkipClient, 'preview').mockResolvedValue(preview);
    const apply = vi.spyOn(importWarningSkipClient, 'apply').mockResolvedValue({ occurrence_identity: first.occurrence_identity,
      before_status: 'open', after_status: 'closed', resulting_version: 2, receipt_identity: 'e'.repeat(64), correlation_id: 'skip', replayed: false });
    render(<CurrentAnomaliesPage />);
    const warning = await screen.findByText(first.display_message);
    expect(screen.getByText(second.display_message)).toBeVisible();
    const button = within(warning.closest('article') as HTMLElement).getByRole('button', { name: '略過並解除這項警示' });
    fireEvent.click(button);
    fireEvent.click(await screen.findByRole('button', { name: '取消' }));
    expect(apply).not.toHaveBeenCalled();
    fireEvent.click(button);
    fireEvent.click(await screen.findByRole('button', { name: '確認略過並保存紀錄' }));
    await waitFor(() => expect(screen.queryByText(first.display_message)).not.toBeInTheDocument());
    expect(screen.getByText(second.display_message)).toBeVisible();
    expect(apply).toHaveBeenCalledTimes(1);
  });

  it('dismisses a LINE warning through the owner and reloads the current list', async () => {
    const preview = { issue_key: issueKey, case_no: 'CASE-1', notification_reason: 'recipient_unavailable',
      owner_snapshot_token: 'a'.repeat(64), preview_fingerprint: 'c'.repeat(64) };
    vi.spyOn(lineNotificationWarningSkipClient, 'preview').mockResolvedValue(preview);
    const apply = vi.spyOn(lineNotificationWarningSkipClient, 'apply').mockResolvedValue({ issue_key: issueKey, replayed: false });
    render(<CurrentAnomaliesPage />);
    const open = await screen.findByRole('button', { name: /LINE-006/ });
    fireEvent.click(within(open.closest('article') as HTMLElement).getByRole('button', { name: '略過並解除這項警示' }));
    expect(await screen.findByText('警示：LINE 通知失敗')).toBeVisible();
    expect(apply).not.toHaveBeenCalled();
    vi.mocked(currentAnomalyQueryClient.queryCurrentAnomalies).mockResolvedValue({ items: [], next_cursor: null });
    fireEvent.click(screen.getByRole('button', { name: '確認略過並保存紀錄' }));
    expect(await screen.findByText('目前沒有其他異常。')).toBeVisible();
    expect(apply).toHaveBeenCalledWith(preview, expect.any(String));
    expect(lineNotificationManualReplayClient.apply).not.toHaveBeenCalled();
  });

  it('keeps HCM review usable when the independent LINE anomaly query fails', async () => {
    vi.mocked(currentAnomalyQueryClient.queryCurrentAnomalies).mockRejectedValueOnce(new Error('LINE projection unavailable'));
    vi.mocked(anomalyQueryClient.queryImportWarningTasks).mockResolvedValueOnce([{
      occurrence_identity: 'warning-system', owning_lane: 'hcm', logical_code: 'HCM-SYSTEM-001',
      field_path: '$case_setup', subject: '115000150', issue_codes: ['case_import_bootstrap_blocked'],
      tracking_status: 'open', tracking_version: 1, evidence_reference: null,
      display_message: '案件初始設定尚未完成', navigation_action: 'hcm_import_center',
    }]);

    render(<CurrentAnomaliesPage />);

    expect(await screen.findByText('案件 115000150')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '前往負責頁面處理' })).toBeEnabled();
    expect(screen.getByRole('alert')).toHaveTextContent('目前異常資料暫時無法使用');
  });
});
