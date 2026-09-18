/**
 * File: LineNotificationRulesMutationPanel.tsx
 * Description: 提供通知規則欄位編輯、零寫入 Preview、人工確認 Save 與安全 Delete 操作。
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Eye, FilePenLine, Info, Save, Settings, Trash2, TriangleAlert } from 'lucide-react';
import {
  LINE_FLEX_DESIGN_SOURCES,
  type LineFlexDesignSource,
} from '../adapters/line_flex_design/line_flex_design_adapter';
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
import type { LineNotificationTemplateClient } from '../api/line_notification_rules/line_notification_template_client';
import { LineFlexDesignPreview } from './LineFlexDesignPreview';
import { LineNotificationTemplateEditor } from './LineNotificationTemplateEditor';

export interface LineNotificationRulesMutationPanelProps {
  catalog: LineNotificationRulesCatalog;
  selectedRuleId?: string | null;
  client?: LineNotificationRulesMutationClient;
  templateClient?: LineNotificationTemplateClient;
  onCommitted?: (receipt: LineNotificationRulesMutationReceiptModel) => void;
}

type OperationState = 'idle' | 'loading' | 'success' | 'error';
type PreviewIntent =
  | { kind: 'save'; preview: LineNotificationRulesPreviewModel }
  | { kind: 'delete'; ruleId: string; preview: LineNotificationRulesPreviewModel };

const NOTIFICATION_RULE_LABELS: Record<LineNotificationEventCode, string> = {
  'gateway.identity_mismatch.second_attempt': '身分核對連續兩次失敗',
  'scheduling.leave.extension_requested': '月嫂請假－請客戶確認',
  'staff.retirement.committed': '月嫂辦理退休生效',
  'router.deterministic.reply_committed': 'AI 確定性指令回覆',
  'feedback.resolved.recorded': '客服回答評為已解決',
  'feedback.unresolved.recorded': '客服回答評為未解決',
  'matching.zero_pool.preview_applied': '候選池協調建議',
  'client.leave.extension_agreed': '產婦同意服務順延',
  'client.leave.extension_rejected': '產婦不同意順延需代班',
  'runtime.alert.review_required': '系統重大異常',
  'complaint.ingress.hold_high_ticket': '重大客訴告警',
  'payroll.substitute.obligation_projected': '代班出勤薪資拆帳結算',
  'order_lifecycle_transition': '訂單生命週期變更',
  'service_time_checkpoint': '提醒上傳寶寶日誌',
  'beclass_completion_changed': 'BeClass 完成狀態變更',
  'deposit_confirmed': '訂金確認',
  'order.pre_start_reminder': '服務開始前 3 天提醒',
  'order.second_payment_reminder': '第二期款（尾款）繳款提醒',
};
const RECIPIENT_OPTIONS: ReadonlyArray<{
  value: LineNotificationRecipientSelector;
  label: string;
}> = [
  { value: 'customer_service.ticket_owner', label: '客服工單專員' },
  { value: 'client.bound_case', label: '案件產婦' },
  { value: 'staff.binding_owner', label: '綁定月嫂' },
  { value: 'conversation.bound_actor', label: '對話使用者' },
  { value: 'matching.request.participants', label: '媒合相關對象' },
  { value: 'assignment.client_snapshot', label: '指派產婦' },
  { value: 'assignment.staff_snapshot', label: '指派月嫂' },
  { value: 'scheduling.owner', label: '排班調度負責人' },
  { value: 'admin.review_actor', label: '工會幹部審核群' },
  { value: 'customer_service.claim_owner', label: '客訴專責處理人' },
  { value: 'staff_payables.anomaly_owner', label: '財務核銷專員' },
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

interface OwnerManagedNotification {
  format: 'card' | 'text';
  state: 'connected' | 'gap';
  summary: string;
  detail: string;
  flexSource?: LineFlexDesignSource;
}

const OWNER_MANAGED_NOTIFICATIONS: Partial<
  Record<LineNotificationEventCode, OwnerManagedNotification>
> = {
  'scheduling.leave.extension_requested': {
    format: 'card',
    state: 'connected',
    summary: '互動卡片｜已由月嫂請假流程觸發',
    detail: '卡片的同意／不同意操作會綁定案件、請假申請版本與收件者，不能改成一般文字通知。',
    flexSource: LINE_FLEX_DESIGN_SOURCES.flex_leave_confirm,
  },
  'matching.zero_pool.preview_applied': {
    format: 'card',
    state: 'connected',
    summary: '互動卡片｜已由媒合協調流程觸發',
    detail: '卡片會帶入當次候選池與限時互動憑證；客戶回覆不等同完成派案。',
    flexSource: LINE_FLEX_DESIGN_SOURCES.flex_negotiation,
  },
  'runtime.alert.review_required': {
    format: 'card',
    state: 'gap',
    summary: '應為告警卡片｜目前實際路徑仍送文字',
    detail: '安全審核連結與卡片發送尚未接通，因此不能在此宣稱卡片已啟用。',
    flexSource: LINE_FLEX_DESIGN_SOURCES.flex_alert_critical,
  },
  'complaint.ingress.hold_high_ticket': {
    format: 'card',
    state: 'gap',
    summary: '應為告警卡片｜尚無真實客訴來源',
    detail: '目前只有需求與設計稿，尚未形成 HIGH 工單、去敏告警與正式發送閉環。',
    flexSource: LINE_FLEX_DESIGN_SOURCES.flex_alert_critical,
  },
};

const OwnerManagedNotificationPanel: React.FC<{
  notification: OwnerManagedNotification;
}> = ({ notification }) => (
  <section className="notification-template-editor" aria-label="通知內容與觸發狀態">
    <div className="notification-template-heading">
      <div>
        <h5>{notification.format === 'card' ? '通知卡片內容' : '通知訊息內容'}</h5>
        <p>{notification.detail}</p>
      </div>
      <span className={notification.state === 'connected' ? 'line-status line-status-bound' : 'line-status line-status-revoked'}>
        {notification.state === 'connected' ? '真實流程已接通' : '尚未接通'}
      </span>
    </div>
    <div className={notification.state === 'connected' ? 'line-scope-note' : 'line-warning'} role="status">
      <Info aria-hidden="true" />{notification.summary}
    </div>
    {notification.flexSource && <LineFlexDesignPreview source={notification.flexSource} />}
  </section>
);

function operationIdentity(prefix: string): string {
  const suffix = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function displayError(error: unknown): string {
  if (error instanceof LineNotificationRulesMutationError) {
    if (error.status === 401) return '登入已失效，請重新登入後再試。';
    if (error.status === 403) return '目前帳號沒有維護 LINE 通知規則的權限。';
    if (error.status === 404) return '找不到這筆通知規則，請重新載入最新規則。';
    if (error.status === 409) return '通知規則已變更，請重新載入並再次檢查影響。';
    if (error.status === 422) return '通知規則內容不完整，請檢查欄位後再試。';
    if (error.retryable) return 'LINE 通知規則服務暫時無法使用，請重新載入最新規則後再試。';
    return 'LINE 通知規則操作未完成，請重新載入最新規則後再試。';
  }
  return 'LINE 通知規則操作未完成，請重新載入最新規則後再試。';
}

function eventLabel(eventCode: LineNotificationEventCode): string {
  return NOTIFICATION_RULE_LABELS[eventCode] ?? eventCode;
}

export const LineNotificationRulesMutationPanel: React.FC<
  LineNotificationRulesMutationPanelProps
> = ({
  catalog,
  selectedRuleId = null,
  client = lineNotificationRulesMutationClient,
  templateClient,
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
  const committedActiveRule = baseline.rules.find((rule) => rule.id === activeRuleId) ?? null;
  const ownerManagedNotification = activeRule
    ? OWNER_MANAGED_NOTIFICATIONS[activeRule.event_code]
    : undefined;
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
    <section className="richmenu-card notification-mutation-panel" aria-label="LINE 通知規則維護">
      <div className="richmenu-card-header">
        <div>
          <h4 className="richmenu-editor-title">
            <Settings aria-hidden="true" />通知規則維護
          </h4>
          <p className="richmenu-editor-description">
            已載入最新通知規則｜每次儲存或刪除前都必須重新檢查影響。
          </p>
        </div>
      </div>

      {draft.rules.length > 0 ? (
        <div className="line-search-filter-toolbar notification-rule-selector-row">
          <label htmlFor="line-notification-rule-selector" className="notification-rule-selector-label">
            通知規則：
          </label>
          <select
            id="line-notification-rule-selector"
            className="line-filter-select notification-rule-selector"
            value={activeRuleId ?? ''}
            disabled={busy}
            onChange={(event) => {
              invalidatePreview();
              setActiveRuleId(event.target.value);
            }}
          >
            {draft.rules.map((rule) => (
              <option key={rule.id} value={rule.id}>{eventLabel(rule.event_code)}</option>
            ))}
          </select>
        </div>
      ) : <p className="line-scope-note line-block-spacing-12">目前沒有可維護的通知規則。</p>}

      {activeRule && (
        <div className="richmenu-drawer-panel notification-rule-editor-panel">
          <fieldset disabled={busy || Boolean(ownerManagedNotification)} className="line-fieldset-reset">
            <legend className="notification-rule-editor-legend">
              <FilePenLine aria-hidden="true" />規則欄位
            </legend>

            <div className="richmenu-drawer-grid">
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
              <div className="richmenu-drawer-grid notification-rule-dependent-fields">
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
            <div className="notification-rule-options-panel">
              <div className="notification-rule-enabled-row">
                <label className="notification-rule-check-label">
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

              <fieldset className="line-fieldset-reset">
                <legend className="notification-rule-predicate-legend">
                  條件
                </legend>
                <div className="notification-rule-predicates">
                  {PREDICATE_OPTIONS.map((option) => {
                    const checked = (activeRule.predicates ?? []).includes(option.value);
                    return (
                      <label key={option.value} className="notification-rule-check-label is-compact">
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

      {ownerManagedNotification ? (
        <OwnerManagedNotificationPanel notification={ownerManagedNotification} />
      ) : activeRule && committedActiveRule && activeRule.template_id === committedActiveRule.template_id ? (
        <LineNotificationTemplateEditor ruleId={committedActiveRule.id} client={templateClient} />
      ) : activeRule ? (
        <p className="line-scope-note notification-rule-dirty-note">
          <TriangleAlert aria-hidden="true" />請先儲存通知規則變更，再編輯實際發送的訊息內容。
        </p>
      ) : null}

      {ownerManagedNotification && (
        <p className="line-scope-note notification-rule-dirty-note">
          <Info aria-hidden="true" />此通知由業務流程管理，避免重複發送，收件者、排程、頻率與啟用狀態不在通知規則頁修改。
        </p>
      )}

      {!ownerManagedNotification && (
        <div className="line-action-row notification-rule-action-row">
          <button
            type="button"
            className="line-secondary-btn"
            disabled={busy || !draftChanged}
            onClick={() => void runPreview('save')}
          >
            <Eye aria-hidden="true" />預覽儲存變更
          </button>
          {activeRule && baselineHasActiveRule && (
            <button
              type="button"
              className="line-danger-btn"
              disabled={busy || draftChanged}
              onClick={() => void runPreview('delete')}
            >
              <Trash2 aria-hidden="true" />預覽刪除規則
            </button>
          )}
        </div>
      )}

      {draftChanged && baselineHasActiveRule && (
        <p className="line-scope-note notification-rule-dirty-note">
          <TriangleAlert aria-hidden="true" />有未儲存編輯時，刪除功能會鎖定；先儲存或重新載入後再刪除。
        </p>
      )}

      {state === 'loading' && <div className="line-loading line-block-spacing-12" role="status">正在執行通知規則操作…</div>}

      {previewIntent && (
        <div className="richmenu-drawer-panel notification-rule-preview-panel">
          <strong className="notification-rule-preview-title">
            {previewIntent.kind === 'save' ? '儲存預覽已就緒' : '刪除預覽已就緒'}
          </strong>
          <p>套用後規則數：{previewIntent.preview.ruleCount}</p>
          <p>通知規則已通過預覽檢查，請核對啟用狀態與通知對象後套用。</p>

          <div className="richmenu-drawer-field line-block-spacing-compact">
            <label htmlFor="line-notification-mutation-reason">操作原因</label>
            <textarea
              id="line-notification-mutation-reason"
              className="richmenu-drawer-input notification-rule-reason-input"
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

          <div className="notification-rule-confirm-row">
            <label className="notification-rule-check-label">
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
            className={previewIntent.kind === 'delete' ? 'line-danger-btn' : 'line-primary-btn'}
            disabled={busy || !confirmed || reason.trim().length === 0}
            onClick={() => void applyPreview()}
          >
            {previewIntent.kind === 'save' ? <><Save aria-hidden="true" />確認儲存通知規則</> : <><Trash2 aria-hidden="true" />確認刪除通知規則</>}
          </button>
        </div>
      )}

      {state === 'success' && message && <div className="line-success line-block-spacing-12" role="status">{message}</div>}
      {state === 'error' && message && <div className="line-error line-block-spacing-12" role="alert">{message}</div>}
    </section>
  );
};

export default LineNotificationRulesMutationPanel;
