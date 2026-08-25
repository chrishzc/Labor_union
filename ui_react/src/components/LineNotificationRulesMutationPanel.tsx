/**
 * File: LineNotificationRulesMutationPanel.tsx
 * Description: 提供通知規則欄位編輯、零寫入 Preview、人工確認 Save 與安全 Delete 操作。
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  adaptLineNotificationRuleDeleteReceipt,
  adaptLineNotificationRulesDraft,
  adaptLineNotificationRulesPreview,
  adaptLineNotificationRulesSaveReceipt,
  type LineNotificationRulesMutationReceiptModel,
  type LineNotificationRulesPreviewModel,
} from '../adapters/line_notification_rules/line_notification_rules_mutation_adapter';
import type {
  LineNotificationEventCode,
  LineNotificationPredicate,
  LineNotificationRecipientSelector,
  LineNotificationRule,
  LineNotificationRulesCatalog,
} from '../api/line_configuration/line_configuration_query_schemas';
import {
  lineNotificationRulesMutationClient,
  type LineNotificationRulesMutationClient,
} from '../api/line_notification_rules/line_notification_rules_mutation_client';
import { LineNotificationRulesMutationError } from '../api/line_notification_rules/line_notification_rules_mutation_errors';
import type { LineNotificationRulesMutationDefinition } from '../api/line_notification_rules/line_notification_rules_mutation_schemas';

export interface LineNotificationRulesMutationPanelProps {
  catalog: LineNotificationRulesCatalog;
  selectedRuleId?: string | null;
  client?: LineNotificationRulesMutationClient;
  onCommitted?: (receipt: LineNotificationRulesMutationReceiptModel) => void;
}

type OperationState = 'idle' | 'loading' | 'success' | 'error';
type PreviewIntent =
  | { kind: 'save'; preview: LineNotificationRulesPreviewModel }
  | { kind: 'delete'; ruleId: string; preview: LineNotificationRulesPreviewModel };

const EVENT_OPTIONS: ReadonlyArray<{ value: LineNotificationEventCode; label: string }> = [
  { value: 'order_lifecycle_transition', label: '訂單生命週期變更' },
  { value: 'service_time_checkpoint', label: '服務時間節點' },
  { value: 'beclass_completion_changed', label: 'BeClass 完成狀態變更' },
  { value: 'deposit_confirmed', label: '訂金確認' },
];
const RECIPIENT_OPTIONS: ReadonlyArray<{
  value: LineNotificationRecipientSelector;
  label: string;
}> = [
  { value: 'client', label: '客戶' },
  { value: 'assigned_caregiver', label: '已指派月嫂' },
  { value: 'case_group', label: '案件群組' },
];
const PREDICATE_OPTIONS: ReadonlyArray<{
  value: LineNotificationPredicate;
  label: string;
}> = [
  { value: 'requires_cooking_true', label: '需要下廚' },
  { value: 'baby_log_missing', label: '嬰兒日誌缺失' },
  { value: 'beclass_missing', label: 'BeClass 資料缺失' },
];

function operationIdentity(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function displayError(error: unknown): string {
  if (error instanceof LineNotificationRulesMutationError) {
    return `${error.code}：${error.message}`;
  }
  return error instanceof Error
    ? error.message
    : 'LINE 通知規則操作失敗，請重新整理後再試。';
}

function nextRuleId(definition: LineNotificationRulesMutationDefinition): string {
  const used = new Set(definition.rules.map((rule) => rule.id));
  let sequence = 1;
  while (used.has(`new_rule_${sequence}`)) sequence += 1;
  return `new_rule_${sequence}`;
}

function newRule(id: string): LineNotificationRule {
  return {
    id,
    event_code: 'order_lifecycle_transition',
    recipient_selector: 'client',
    template_id: 'message_template',
    enabled: false,
    schedule: { kind: 'immediate' },
    frequency: { kind: 'once' },
    predicates: [],
  };
}

export const LineNotificationRulesMutationPanel: React.FC<
  LineNotificationRulesMutationPanelProps
> = ({
  catalog,
  selectedRuleId = null,
  client = lineNotificationRulesMutationClient,
  onCommitted,
}) => {
  const initial = useMemo(() => adaptLineNotificationRulesDraft(catalog), [catalog]);
  const [revision, setRevision] = useState(initial.revision);
  const [baseline, setBaseline] = useState(initial.definition);
  const [draft, setDraft] = useState(initial.definition);
  const [activeRuleId, setActiveRuleId] = useState<string | null>(
    selectedRuleId ?? initial.definition.rules[0]?.id ?? null
  );
  const [previewIntent, setPreviewIntent] = useState<PreviewIntent | null>(null);
  const [reason, setReason] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [state, setState] = useState<OperationState>('idle');
  const [message, setMessage] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    controllerRef.current?.abort();
    setRevision(initial.revision);
    setBaseline(initial.definition);
    setDraft(initial.definition);
    setActiveRuleId(
      selectedRuleId && initial.definition.rules.some((rule) => rule.id === selectedRuleId)
        ? selectedRuleId
        : initial.definition.rules[0]?.id ?? null
    );
    setPreviewIntent(null);
    setReason('');
    setConfirmed(false);
    setState('idle');
    setMessage(null);
  }, [initial, selectedRuleId]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const activeRule = draft.rules.find((rule) => rule.id === activeRuleId) ?? null;
  const baselineHasActiveRule = baseline.rules.some((rule) => rule.id === activeRuleId);
  const draftChanged = JSON.stringify(draft) !== JSON.stringify(baseline);
  const busy = state === 'loading';

  const invalidatePreview = (): void => {
    controllerRef.current?.abort();
    setPreviewIntent(null);
    setReason('');
    setConfirmed(false);
    setState('idle');
    setMessage(null);
  };

  const updateActiveRule = (update: (rule: LineNotificationRule) => LineNotificationRule): void => {
    if (!activeRuleId) return;
    invalidatePreview();
    setDraft((current) => ({
      rules: current.rules.map((rule) => (rule.id === activeRuleId ? update(rule) : rule)),
    }));
  };

  const updateRuleId = (nextId: string): void => {
    if (!activeRuleId) return;
    const previousId = activeRuleId;
    invalidatePreview();
    setDraft((current) => ({
      rules: current.rules.map((rule) => (
        rule.id === previousId ? { ...rule, id: nextId } : rule
      )),
    }));
    setActiveRuleId(nextId);
  };

  const addRule = (): void => {
    const id = nextRuleId(draft);
    invalidatePreview();
    setDraft((current) => ({ rules: [...current.rules, newRule(id)] }));
    setActiveRuleId(id);
  };

  const cancelNewRule = (): void => {
    if (!activeRuleId || baselineHasActiveRule) return;
    const remaining = draft.rules.filter((rule) => rule.id !== activeRuleId);
    invalidatePreview();
    setDraft({ rules: remaining });
    setActiveRuleId(remaining[0]?.id ?? null);
  };

  const runPreview = async (kind: 'save' | 'delete'): Promise<void> => {
    if (kind === 'save' && !draftChanged) return;
    if (kind === 'delete' && (!activeRuleId || !baselineHasActiveRule || draftChanged)) return;
    const candidate = kind === 'save'
      ? draft
      : { rules: baseline.rules.filter((rule) => rule.id !== activeRuleId) };
    const controller = new AbortController();
    controllerRef.current?.abort();
    controllerRef.current = controller;
    setState('loading');
    setPreviewIntent(null);
    setReason('');
    setConfirmed(false);
    setMessage(null);
    try {
      const result = await client.preview(
        { expected_revision: revision, definition: candidate },
        { signal: controller.signal }
      );
      if (controller.signal.aborted) return;
      const preview = adaptLineNotificationRulesPreview(result);
      setPreviewIntent(
        kind === 'save'
          ? { kind: 'save', preview }
          : { kind: 'delete', ruleId: activeRuleId as string, preview }
      );
      setState('success');
    } catch (error) {
      if (controller.signal.aborted) return;
      setState('error');
      setMessage(displayError(error));
    }
  };

  const applyPreview = async (): Promise<void> => {
    if (!previewIntent || !confirmed || reason.trim().length === 0) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    setState('loading');
    setMessage(null);
    const common = {
      expected_revision: previewIntent.preview.beforeRevision,
      preview_fingerprint: previewIntent.preview.fingerprint,
      reason: reason.trim(),
      idempotency_key: operationIdentity(`line-notification-${previewIntent.kind}-idem`),
      correlation_id: operationIdentity(`line-notification-${previewIntent.kind}-corr`),
    };
    try {
      const receipt = previewIntent.kind === 'save'
        ? adaptLineNotificationRulesSaveReceipt(await client.save(
          { ...common, definition: previewIntent.preview.definition },
          { signal: controller.signal }
        ))
        : adaptLineNotificationRuleDeleteReceipt(await client.deleteRule(
          previewIntent.ruleId,
          common,
          { signal: controller.signal }
        ));
      if (controller.signal.aborted) return;
      const committedDefinition = previewIntent.preview.definition;
      setRevision(receipt.revision);
      setBaseline(committedDefinition);
      setDraft(committedDefinition);
      setActiveRuleId(
        previewIntent.kind === 'delete'
          ? committedDefinition.rules[0]?.id ?? null
          : activeRuleId
      );
      setPreviewIntent(null);
      setReason('');
      setConfirmed(false);
      setState('success');
      setMessage(
        `${receipt.operation === 'save' ? '通知規則已儲存' : `規則 ${receipt.ruleId} 已刪除`}；`
        + `已取消 ${receipt.cancelledIntentCount} 筆待發通知與 ${receipt.cancelledTaskCount} 筆發送工作。`
      );
      onCommitted?.(receipt);
    } catch (error) {
      if (controller.signal.aborted) return;
      setPreviewIntent(null);
      setConfirmed(false);
      setState('error');
      setMessage(displayError(error));
    }
  };

  return (
    <section className="richmenu-card" aria-label="LINE 通知規則維護" style={{ marginBottom: '24px' }}>
      <div className="richmenu-card-header">
        <div>
          <h4 style={{ margin: 0, fontSize: '1.05rem', color: '#1e1b19', fontWeight: 700 }}>
            ⚙️ 通知規則維護
          </h4>
          <p style={{ margin: '4px 0 0', fontSize: '0.82rem', color: '#74593f' }}>
            已載入最新通知規則｜每次儲存或刪除前都必須重新檢查影響。
          </p>
        </div>
        <button
          type="button"
          className="line-primary-btn"
          style={{ padding: '6px 14px', fontSize: '0.82rem' }}
          disabled={busy}
          onClick={addRule}
        >
          新增規則
        </button>
      </div>

      {draft.rules.length > 0 ? (
        <div className="line-search-filter-toolbar" style={{ marginTop: '16px', marginBottom: '16px' }}>
          <label htmlFor="line-notification-rule-selector" style={{ fontSize: '0.85rem', fontWeight: 700, color: '#57423b' }}>
            要編輯的通知規則：
          </label>
          <select
            id="line-notification-rule-selector"
            className="line-filter-select"
            style={{ minWidth: '220px' }}
            value={activeRuleId ?? ''}
            disabled={busy}
            onChange={(event) => {
              invalidatePreview();
              setActiveRuleId(event.target.value);
            }}
          >
            {draft.rules.map((rule) => <option key={rule.id} value={rule.id}>📌 {rule.id}</option>)}
          </select>
        </div>
      ) : <p className="line-scope-note" style={{ marginTop: '12px' }}>目前沒有通知規則；可新增第一筆規則後預覽儲存。</p>}

      {activeRule && (
        <div className="richmenu-drawer-panel" style={{ marginTop: '12px', background: '#fffcfb', border: '1px solid #fed9b8' }}>
          <fieldset disabled={busy} style={{ border: 'none', padding: 0, margin: 0 }}>
            <legend style={{ fontSize: '0.92rem', fontWeight: 800, color: '#a43c12', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              📝 規則欄位
            </legend>

            <div className="richmenu-drawer-grid">
              <div className="richmenu-drawer-field">
                <label htmlFor="line-notification-rule-id">規則 ID</label>
                <input
                  id="line-notification-rule-id"
                  className="richmenu-drawer-input"
                  value={activeRule.id}
                  maxLength={64}
                  onChange={(event) => updateRuleId(event.target.value)}
                />
              </div>

              <div className="richmenu-drawer-field">
                <label htmlFor="line-notification-event-code">事件</label>
                <select
                  id="line-notification-event-code"
                  className="richmenu-drawer-select"
                  value={activeRule.event_code}
                  onChange={(event) => updateActiveRule((rule) => ({
                    ...rule,
                    event_code: event.target.value as LineNotificationEventCode,
                  }))}
                >
                  {EVENT_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </div>

              <div className="richmenu-drawer-field">
                <label htmlFor="line-notification-recipient">收件者</label>
                <select
                  id="line-notification-recipient"
                  className="richmenu-drawer-select"
                  value={activeRule.recipient_selector}
                  onChange={(event) => updateActiveRule((rule) => ({
                    ...rule,
                    recipient_selector: event.target.value as LineNotificationRecipientSelector,
                  }))}
                >
                  {RECIPIENT_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </div>

              <div className="richmenu-drawer-field">
                <label htmlFor="line-notification-template-id">訊息模板 ID</label>
                <input
                  id="line-notification-template-id"
                  className="richmenu-drawer-input"
                  value={activeRule.template_id}
                  maxLength={64}
                  onChange={(event) => updateActiveRule((rule) => ({
                    ...rule,
                    template_id: event.target.value,
                  }))}
                />
              </div>

              <div className="richmenu-drawer-field">
                <label htmlFor="line-notification-schedule-kind">排程方式</label>
                <select
                  id="line-notification-schedule-kind"
                  className="richmenu-drawer-select"
                  value={activeRule.schedule.kind}
                  onChange={(event) => updateActiveRule((rule) => ({
                    ...rule,
                    schedule: event.target.value === 'relative_service_time'
                      ? { kind: 'relative_service_time', offset_seconds: 0 }
                      : { kind: event.target.value as 'immediate' | 'service_end' },
                  }))}
                >
                  <option value="immediate">立即通知</option>
                  <option value="relative_service_time">服務時間後</option>
                  <option value="service_end">服務結束時</option>
                </select>
              </div>

              <div className="richmenu-drawer-field">
                <label htmlFor="line-notification-frequency-kind">頻率</label>
                <select
                  id="line-notification-frequency-kind"
                  className="richmenu-drawer-select"
                  value={activeRule.frequency?.kind ?? 'once'}
                  onChange={(event) => updateActiveRule((rule) => ({
                    ...rule,
                    frequency: event.target.value === 'recurring_bounded'
                      ? { kind: 'recurring_bounded', maximum_occurrences: 1, interval_days: 1 }
                      : { kind: 'once' },
                  }))}
                >
                  <option value="once">一次</option>
                  <option value="recurring_bounded">有限次重複</option>
                </select>
              </div>
            </div>

            {/* 動態子欄位 (秒數 / 次數 / 間隔) */}
            {(activeRule.schedule.kind === 'relative_service_time' || activeRule.frequency?.kind === 'recurring_bounded') && (
              <div className="richmenu-drawer-grid" style={{ paddingTop: '10px', borderTop: '1px dashed #fed9b8' }}>
                {activeRule.schedule.kind === 'relative_service_time' && (
                  <div className="richmenu-drawer-field">
                    <label htmlFor="line-notification-offset-seconds">服務時間後秒數</label>
                    <input
                      id="line-notification-offset-seconds"
                      type="number"
                      className="richmenu-drawer-input"
                      min={0}
                      step={1}
                      value={activeRule.schedule.offset_seconds}
                      onChange={(event) => updateActiveRule((rule) => ({
                        ...rule,
                        schedule: {
                          kind: 'relative_service_time',
                          offset_seconds: Number(event.target.value),
                        },
                      }))}
                    />
                  </div>
                )}
                {activeRule.frequency?.kind === 'recurring_bounded' && (
                  <>
                    <div className="richmenu-drawer-field">
                      <label htmlFor="line-notification-max-occurrences">最多次數</label>
                      <input
                        id="line-notification-max-occurrences"
                        type="number"
                        className="richmenu-drawer-input"
                        min={1}
                        step={1}
                        value={activeRule.frequency.maximum_occurrences}
                        onChange={(event) => updateActiveRule((rule) => ({
                          ...rule,
                          frequency: {
                            kind: 'recurring_bounded',
                            maximum_occurrences: Number(event.target.value),
                            interval_days: rule.frequency?.kind === 'recurring_bounded'
                              ? rule.frequency.interval_days
                              : 1,
                          },
                        }))}
                      />
                    </div>
                    <div className="richmenu-drawer-field">
                      <label htmlFor="line-notification-interval-days">間隔天數</label>
                      <input
                        id="line-notification-interval-days"
                        type="number"
                        className="richmenu-drawer-input"
                        min={1}
                        step={1}
                        value={activeRule.frequency.interval_days}
                        onChange={(event) => updateActiveRule((rule) => ({
                          ...rule,
                          frequency: {
                            kind: 'recurring_bounded',
                            maximum_occurrences: rule.frequency?.kind === 'recurring_bounded'
                              ? rule.frequency.maximum_occurrences
                              : 1,
                            interval_days: Number(event.target.value),
                          },
                        }))}
                      />
                    </div>
                  </>
                )}
              </div>
            )}

            {/* 啟用開關與條件複選 */}
            <div style={{ marginTop: '12px', padding: '12px 14px', background: '#fff', borderRadius: '10px', border: '1px solid #fed9b8' }}>
              <div style={{ marginBottom: '10px' }}>
                <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontWeight: 700, color: '#1e1b19' }}>
                  <input
                    type="checkbox"
                    checked={activeRule.enabled ?? false}
                    onChange={(event) => updateActiveRule((rule) => ({
                      ...rule,
                      enabled: event.target.checked,
                    }))}
                  />
                  啟用此規則
                </label>
              </div>

              <fieldset style={{ border: 'none', padding: 0, margin: 0 }}>
                <legend style={{ fontSize: '0.82rem', fontWeight: 700, color: '#74593f', marginBottom: '6px' }}>
                  條件
                </legend>
                <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                  {PREDICATE_OPTIONS.map((option) => {
                    const checked = (activeRule.predicates ?? []).includes(option.value);
                    return (
                      <label key={option.value} style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', cursor: 'pointer', fontSize: '0.84rem' }}>
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(event) => updateActiveRule((rule) => ({
                            ...rule,
                            predicates: event.target.checked
                              ? [...(rule.predicates ?? []), option.value]
                              : (rule.predicates ?? []).filter((value) => value !== option.value),
                          }))}
                        />
                        {option.label}
                      </label>
                    );
                  })}
                </div>
              </fieldset>
            </div>
          </fieldset>
        </div>
      )}

      <div className="line-action-row" style={{ marginTop: '16px', display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
        <button
          type="button"
          className="line-primary-btn"
          style={{ padding: '8px 16px', fontSize: '0.85rem' }}
          disabled={busy || !draftChanged}
          onClick={() => void runPreview('save')}
        >
          預覽儲存變更
        </button>
        {activeRule && baselineHasActiveRule && (
          <button
            type="button"
            className="line-secondary-btn"
            style={{ padding: '8px 16px', fontSize: '0.85rem', borderColor: '#fca5a5', color: '#dc2626' }}
            disabled={busy || draftChanged}
            onClick={() => void runPreview('delete')}
          >
            預覽刪除規則
          </button>
        )}
        {activeRule && !baselineHasActiveRule && (
          <button
            type="button"
            className="line-secondary-btn"
            style={{ padding: '8px 16px', fontSize: '0.85rem' }}
            disabled={busy}
            onClick={cancelNewRule}
          >
            取消新增規則
          </button>
        )}
      </div>

      {draftChanged && baselineHasActiveRule && (
        <p className="line-scope-note" style={{ marginTop: '8px', color: '#b45309' }}>
          ⚠️ 有未儲存編輯時，刪除功能會鎖定；先儲存或重新載入後再刪除。
        </p>
      )}

      {state === 'loading' && <div className="line-loading" role="status" style={{ marginTop: '12px' }}>正在執行通知規則操作…</div>}

      {previewIntent && (
        <div className="richmenu-drawer-panel" style={{ marginTop: '16px', background: '#fffaf5', border: '2px solid #ff7f50' }}>
          <strong style={{ display: 'block', margin: '0 0 10px', fontSize: '1rem', color: '#a43c12', fontWeight: 800 }}>
            {previewIntent.kind === 'save' ? '儲存預覽已就緒' : '刪除預覽已就緒'}
          </strong>
          <p>套用後規則數：{previewIntent.preview.ruleCount}</p>
          <p>通知規則已通過預覽檢查，請核對啟用狀態與通知對象後套用。</p>

          <div className="richmenu-drawer-field" style={{ marginTop: '10px' }}>
            <label htmlFor="line-notification-mutation-reason">操作原因</label>
            <textarea
              id="line-notification-mutation-reason"
              className="richmenu-drawer-input"
              style={{ minHeight: '70px' }}
              value={reason}
              rows={3}
              maxLength={1_000}
              disabled={busy}
              onChange={(event) => {
                setReason(event.target.value);
                setConfirmed(false);
              }}
              placeholder="請輸入本次變更之業務原因…"
            />
          </div>

          <div style={{ marginTop: '8px', marginBottom: '14px' }}>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontWeight: 700 }}>
              <input
                type="checkbox"
                checked={confirmed}
                disabled={busy}
                onChange={(event) => setConfirmed(event.target.checked)}
              />
              我已確認通知規則與影響範圍
            </label>
          </div>

          <button
            type="button"
            className="line-primary-btn"
            style={{ padding: '8px 20px', fontSize: '0.88rem' }}
            disabled={busy || !confirmed || reason.trim().length === 0}
            onClick={() => void applyPreview()}
          >
            {previewIntent.kind === 'save' ? '確認儲存通知規則' : '確認刪除通知規則'}
          </button>
        </div>
      )}

      {state === 'success' && message && <div className="line-success" role="status" style={{ marginTop: '12px' }}>{message}</div>}
      {state === 'error' && message && <div className="line-error" role="alert" style={{ marginTop: '12px' }}>{message}</div>}
    </section>
  );
};

export default LineNotificationRulesMutationPanel;
