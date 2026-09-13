/**
 * File: AlertGroupSecurity.tsx
 * Description: 以 typed LINE runtime target 契約完成查詢、Preview、確認、Apply、receipt 與 readback。
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Bell,
  BellOff,
  Check,
  CheckCircle2,
  Copy,
  Eye,
  FileText,
  Info,
  MessageSquare,
  RefreshCw,
  RotateCcw,
  SearchCheck,
  ShieldCheck,
  SlidersHorizontal,
  Smartphone,
  Users,
} from 'lucide-react';
import { lineRuntimeTargetClient } from '../../api/line_runtime_targets/line_runtime_target_client';
import { LineRuntimeTargetError } from '../../api/line_runtime_targets/line_runtime_target_errors';
import type {
  LineRuntimeGroupResetRequest,
  LineRuntimeTarget,
  LineRuntimeTargetEnabledRequest,
  LineRuntimeTargetPreview,
  LineRuntimeTargetReceipt,
} from '../../api/line_runtime_targets/line_runtime_target_schemas';
import '../LineManagementPage.css';

export interface RuntimeTargetClient {
  listTargets: typeof lineRuntimeTargetClient.listTargets;
  previewResetGroup: typeof lineRuntimeTargetClient.previewResetGroup;
  resetGroup: typeof lineRuntimeTargetClient.resetGroup;
  previewSetEnabled: typeof lineRuntimeTargetClient.previewSetEnabled;
  setEnabled: typeof lineRuntimeTargetClient.setEnabled;
  getPreferences?: typeof lineRuntimeTargetClient.getPreferences;
  updatePreferences?: typeof lineRuntimeTargetClient.updatePreferences;
}

export interface AlertGroupSecurityProps {
  client?: RuntimeTargetClient;
  runtimeTargetClient?: RuntimeTargetClient;
}

type PendingAction =
  | {
      kind: 'group_reset';
      target: LineRuntimeTarget;
      request: LineRuntimeGroupResetRequest;
      preview: LineRuntimeTargetPreview;
    }
  | {
      kind: 'toggle';
      target: LineRuntimeTarget;
      request: LineRuntimeTargetEnabledRequest;
      preview: LineRuntimeTargetPreview;
    };

type MessageCategoryKey =
  | 'customer_service'
  | 'dispatch_matching'
  | 'staff_leave_urgent'
  | 'system_health'
  | 'contract_signing';

interface MessageCategoryMeta {
  key: MessageCategoryKey;
  label: string;
  badge: string;
  description: string;
  senderName: string;
  senderTime: string;
  avatarColor: string;
  isFlex?: boolean;
  flexTitle?: string;
  flexCaseNo?: string;
  flexBody?: string;
  flexBtnLabel?: string;
  sampleTitle?: string;
  sampleRows?: { label: string; value: string }[];
  sampleAction?: string | null;
  tipText: string;
}

const MESSAGE_CATEGORIES: MessageCategoryMeta[] = [
  {
    key: 'customer_service',
    label: '客訴與真人客服急件',
    badge: '🚨 業務急件',
    description: '客戶在 LINE 官方帳號情緒字眼、強烈投訴態度、或連續比對失敗主動要求轉真人。',
    senderName: '客服小幫手',
    senderTime: '16:30',
    avatarColor: '#ea580c',
    sampleTitle: '【急件客服告警】',
    sampleRows: [
      { label: '客戶姓名', value: '王小姐 (0912-***-456)' },
      { label: '投訴事由', value: '我要客訴：服務態度很差，請主管協助處理。' },
      { label: '案件編號', value: 'CASE-2026-S12' },
      { label: '急迫等級', value: 'HIGH (需立即接手)' },
      { label: '通報時間', value: '2026-09-13 16:30' },
    ],
    sampleAction: '🔗 點擊開啟手機審核中心接手處理',
    tipText: '建議維持開啟。當重大客訴發生時，群組幹部可即時查看並由電話或私訊接手安撫。',
  },
  {
    key: 'dispatch_matching',
    label: '排班媒合調整（條件協商）',
    badge: '🔄 媒合協商',
    description: '候選月嫂全數未答覆或無意願、或客戶完成意願條件調整，需要專員人工協調。',
    senderName: '排班中心',
    senderTime: '16:32',
    avatarColor: '#047857',
    isFlex: true,
    flexTitle: '媒合需要人工處理',
    flexCaseNo: 'CASE-2026-S13',
    flexBody: '已詢問 3 位月嫂，皆未願意承接。客戶目前無法調整條件，請由工會人員接手處理。',
    flexBtnLabel: '開啟待辦工作台',
    tipText: '建議維持開啟。當 Zero-Pool（所有月嫂皆無法承接）或需人工調整媒合條件時，群組可直接點擊工作台接手。',
  },
  {
    key: 'staff_leave_urgent',
    label: '月嫂突發請假代班',
    badge: '🚨 請假代班',
    description: '月嫂突發急病或事故請假且客戶不順延，急需排班幹部立即指派代班月嫂。',
    senderName: '調派中心',
    senderTime: '16:35',
    avatarColor: '#dc2626',
    sampleTitle: '【緊急代班指派通知】',
    sampleRows: [
      { label: '訂單編號', value: 'CASE-2026-S15' },
      { label: '產婦客戶', value: '林太太 (0933-***-789)' },
      { label: '異常事件', value: '原服務月嫂突發急病請假，客戶需求不中斷' },
      { label: '目前狀態', value: '等待專員代班直接指派' },
    ],
    sampleAction: '🔗 開啟排班總表進行代班指派',
    tipText: '建議維持開啟。可讓幹部第一時間收到缺工通報，避免產婦無人服務引發重大爭議。',
  },
  {
    key: 'system_health',
    label: '系統 IT 健康維運通報',
    badge: '⚙️ IT 監控',
    description: 'LINE Worker 服務斷線、心跳過期、訊息佇列大量積壓或資料庫異常等技術故障告警。',
    senderName: '系統監控',
    senderTime: '16:30',
    avatarColor: '#475569',
    sampleTitle: '【系統異常通知】',
    sampleRows: [
      { label: '故障組件', value: 'LINE Worker / 佇列' },
      { label: '異常狀態', value: 'CRITICAL (嚴重)' },
      { label: '異常說明', value: 'LINE Worker heartbeat 過期或未回應' },
      { label: '記錄時間', value: '2026-09-13 16:30 UTC' },
    ],
    sampleAction: null,
    tipText: '工會專員建議關閉。關閉後系統異常訊息將不會推播到幹部群組，群組只專注處理業務與客訴！',
  },
  {
    key: 'contract_signing',
    label: '服務結案與合約簽署通知',
    badge: '📝 行政合約',
    description: '月嫂服務滿期結案完成、客戶完成線上合約簽署確認。',
    senderName: '行政小幫手',
    senderTime: '15:45',
    avatarColor: '#2563eb',
    sampleTitle: '【合約簽署完成通知】',
    sampleRows: [
      { label: '客戶姓名', value: '張小姐' },
      { label: '訂單編號', value: 'CASE-2026-S10' },
      { label: '辦理項目', value: '線上電子合約雙方已完成簽署' },
      { label: '完成時間', value: '2026-09-13 15:45' },
    ],
    sampleAction: '📄 點擊查看電子簽署紀錄',
    tipText: '可依幹部群組需要開啟。方便行政專員掌握每日簽約結案進度。',
  },
];

function publicFailureMessage(error: unknown): string {
  if (error instanceof LineRuntimeTargetError) {
    return `${error.publicCode ?? error.code}：${error.message}`;
  }
  return 'LINE 通知群組操作失敗，請重新登入或稍後再試。';
}

function stateLabel(state: string): string {
  if (state === 'active') return '啟用';
  if (state === 'disabled') return '停用';
  if (state === 'revoked') return '已解除';
  return '待確認';
}

function minimumStatusLabel(status: LineRuntimeTarget['minimum_status']): string {
  if (status === 'critical') return '重大異常';
  if (status === 'warning') return '重要通知';
  return '一般通知';
}

function identityPart(): string {
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`;
}

function commandIdentity(operation: string): { correlation_id: string; idempotency_key: string } {
  const part = identityPart();
  return {
    correlation_id: `line-security:${operation}:${part}`,
    idempotency_key: `line-security:${operation}:${part}`,
  };
}

export const AlertGroupSecurity: React.FC<AlertGroupSecurityProps> = ({
  client,
  runtimeTargetClient,
}) => {
  const targetClient = client ?? runtimeTargetClient ?? lineRuntimeTargetClient;
  const [targets, setTargets] = useState<LineRuntimeTarget[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [busy, setBusy] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [reason, setReason] = useState<string>('管理員透過後台調整異常通知設定');
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [confirmed, setConfirmed] = useState<boolean>(false);
  const [receipt, setReceipt] = useState<LineRuntimeTargetReceipt | null>(null);
  const [readbackMessage, setReadbackMessage] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState<number>(0);
  const [copied, setCopied] = useState<boolean>(false);
  const [activePreviewKey, setActivePreviewKey] = useState<MessageCategoryKey>('customer_service');
  const [savedSuccessTip, setSavedSuccessTip] = useState<string | null>(null);
  const [prefLoading, setPrefLoading] = useState<boolean>(false);
  const [prefSaving, setPrefSaving] = useState<boolean>(false);

  // 群組訊息推播分類開關偏好
  const [categoryPreferences, setCategoryPreferences] = useState<Record<MessageCategoryKey, boolean>>(() => {
    try {
      const saved = localStorage.getItem('line_alert_msg_categories');
      if (saved) return JSON.parse(saved);
    } catch {}
    return {
      customer_service: true,
      dispatch_matching: true,
      staff_leave_urgent: true,
      system_health: false, // 預設關閉系統 IT 異常，實現使用者「不想讓群組顯示系統異常通知」的需求
      contract_signing: true,
    };
  });

  const groupTarget = targets.find((target) => target.target_kind === 'group') ?? null;
  const activeMeta = MESSAGE_CATEGORIES.find((c) => c.key === activePreviewKey) ?? MESSAGE_CATEGORIES[0];

  useEffect(() => {
    if (!groupTarget) return;
    const fetcher = targetClient.getPreferences ?? lineRuntimeTargetClient.getPreferences;
    let active = true;
    setPrefLoading(true);
    fetcher(groupTarget.target_id, { correlationId: `pref-query-${groupTarget.target_id}` })
      .then((prefs) => {
        if (active) {
          setCategoryPreferences(prefs);
          try {
            localStorage.setItem('line_alert_msg_categories', JSON.stringify(prefs));
          } catch {}
        }
      })
      .catch(() => {
        // Fallback to existing state if error
      })
      .finally(() => {
        if (active) setPrefLoading(false);
      });
    return () => {
      active = false;
    };
  }, [groupTarget?.target_id, targetClient]);

  const handleToggleCategory = async (key: MessageCategoryKey) => {
    const nextState = !categoryPreferences[key];
    const previous = { ...categoryPreferences };
    const updated = { ...categoryPreferences, [key]: nextState };
    setCategoryPreferences(updated);
    try {
      localStorage.setItem('line_alert_msg_categories', JSON.stringify(updated));
    } catch {}

    if (groupTarget) {
      const updater = targetClient.updatePreferences ?? lineRuntimeTargetClient.updatePreferences;
      setPrefSaving(true);
      try {
        const saved = await updater(groupTarget.target_id, updated);
        setCategoryPreferences(saved);
        setSavedSuccessTip(`已儲存「${MESSAGE_CATEGORIES.find((c) => c.key === key)?.label}」推播開關為：${nextState ? '開啟' : '關閉'}`);
        setTimeout(() => setSavedSuccessTip(null), 3000);
      } catch (err) {
        setCategoryPreferences(previous);
        setErrorMessage(publicFailureMessage(err));
      } finally {
        setPrefSaving(false);
      }
    } else {
      setSavedSuccessTip(`已更新「${MESSAGE_CATEGORIES.find((c) => c.key === key)?.label}」推播開關為：${nextState ? '開啟' : '關閉'}`);
      setTimeout(() => setSavedSuccessTip(null), 3000);
    }
  };

  const handleCopyCommand = async (text: string) => {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2200);
    } catch {
      setCopied(false);
    }
  };

  const loadTargets = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const result = await targetClient.listTargets({ correlationId: `line-security-query:${identityPart()}`, signal });
      setTargets(result);
    } catch (error) {
      if (signal?.aborted) return;
      setTargets([]);
      setErrorMessage(publicFailureMessage(error));
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [targetClient]);

  useEffect(() => {
    const controller = new AbortController();
    void loadTargets(controller.signal);
    return () => controller.abort();
  }, [loadTargets, reloadKey]);

  const clearCandidate = () => {
    setPending(null);
    setConfirmed(false);
  };

  const previewToggle = async (target: LineRuntimeTarget) => {
    const normalizedReason = reason.trim() || `管理員透過後台${target.state === 'active' ? '暫停' : '恢復'}通知`;
    setBusy(true);
    setErrorMessage(null);
    setReceipt(null);
    setReadbackMessage(null);
    clearCandidate();
    try {
      const request: LineRuntimeTargetEnabledRequest = {
        expected_version: target.current_version,
        enabled: target.state !== 'active',
        reason: normalizedReason,
        ...commandIdentity('toggle'),
      };
      const preview = await targetClient.previewSetEnabled(target.target_id, request);
      setPending({ kind: 'toggle', target, request, preview });
    } catch (error) {
      setErrorMessage(publicFailureMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const previewGroupReset = async (target: LineRuntimeTarget) => {
    const normalizedReason = reason.trim() || '工會人員調整異常通知群組';
    setBusy(true);
    setErrorMessage(null);
    setReceipt(null);
    setReadbackMessage(null);
    clearCandidate();
    try {
      const request: LineRuntimeGroupResetRequest = {
        expected_version: target.current_version,
        reason: normalizedReason,
        ...commandIdentity('group-reset'),
      };
      const preview = await targetClient.previewResetGroup(request);
      setPending({ kind: 'group_reset', target, request, preview });
    } catch (error) {
      setErrorMessage(publicFailureMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const applyPending = async () => {
    if (!pending || !confirmed) return;
    setBusy(true);
    setErrorMessage(null);
    try {
      const applied = pending.kind === 'group_reset'
        ? await targetClient.resetGroup({
            ...pending.request,
            preview_fingerprint: pending.preview.preview_fingerprint,
          })
        : await targetClient.setEnabled(pending.target.target_id, {
            ...pending.request,
            preview_fingerprint: pending.preview.preview_fingerprint,
          });
      setReceipt(applied);
      setPending(null);
      setConfirmed(false);
      try {
        const readback = await targetClient.listTargets({ correlationId: `line-security-readback:${identityPart()}` });
        setTargets(readback);
        setReadbackMessage('已重新查詢並確認最新狀態。');
      } catch {
        setReadbackMessage('變更已受理，但最新狀態暫時無法取得；可按「重新整理」再次查詢，不會重複提交。');
      }
    } catch (error) {
      setErrorMessage(publicFailureMessage(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="alert-group-security-container">
      <header className="line-hub-page-header alert-security-page-header">
        <div className="line-hub-page-heading">
          <span className="line-hub-page-icon" aria-hidden="true"><ShieldCheck /></span>
          <div>
            <p className="line-hub-eyebrow">LINE 專區</p>
            <h1>幹部通知群組與訊息管理</h1>
            <p>管理工會幹部 LINE 告警群組、設定推播訊息類型、自訂過濾規則與即時訊息模擬。</p>
          </div>
        </div>
      </header>

      <section className="line-workspace-card alert-security-query-section" aria-labelledby="alert-targets-title">
        <div className="line-section-heading">
          <div>
            <h2 id="alert-targets-title">幹部通知群組與目前狀態</h2>
            <p>工會重大業務告警的專屬 LINE 群組推播目標；顯示為啟用代表訊息會正常推播至群組中。</p>
          </div>
          <button
            type="button"
            className="line-secondary-btn"
            onClick={() => setReloadKey((value) => value + 1)}
            disabled={loading || busy}
          >
            <RefreshCw aria-hidden="true" className={loading ? 'spin' : ''} /> {loading ? '查詢中…' : '重新整理'}
          </button>
        </div>

        {errorMessage && <div className="line-error" role="alert">{errorMessage}</div>}

        {/* 尚未綁定群組時的 Onboarding 指引卡片 */}
        {!loading && !errorMessage && targets.length === 0 && (
          <div className="alert-onboarding-card">
            <div className="alert-onboarding-banner">
              <div className="alert-onboarding-title-wrap">
                <span className="alert-onboarding-icon" aria-hidden="true"><Smartphone /></span>
                <div>
                  <h3>目前沒有已登錄的通知對象</h3>
                  <p className="alert-onboarding-desc">
                    尚未綁定幹部通知群組。請依照以下 3 個步驟，將工會官方帳號加入幹部 LINE 群組並完成登錄：
                  </p>
                </div>
              </div>
            </div>

            <div className="alert-onboarding-steps-grid">
              <div className="alert-step-box">
                <div className="alert-step-badge">步驟 1</div>
                <div className="alert-step-body">
                  <strong>邀請官方帳號進群</strong>
                  <p>開啟手機 LINE App 進入幹部管理群組，搜尋並邀請工會 LINE 官方帳號加入群組。</p>
                </div>
              </div>

              <div className="alert-step-box alert-step-highlight">
                <div className="alert-step-badge">步驟 2</div>
                <div className="alert-step-body">
                  <strong>在群組中發送登錄指令</strong>
                  <p>在群組聊天對話框中發送以下專屬指令：</p>
                  <div className="alert-copy-command-bar">
                    <code>設定異常通知群組</code>
                    <button
                      type="button"
                      className="line-copy-btn"
                      onClick={() => void handleCopyCommand('設定異常通知群組')}
                      title="複製指令"
                    >
                      {copied ? (
                        <><Check aria-hidden="true" /> 已複製</>
                      ) : (
                        <><Copy aria-hidden="true" /> 複製指令</>
                      )}
                    </button>
                  </div>
                </div>
              </div>

              <div className="alert-step-box">
                <div className="alert-step-badge">步驟 3</div>
                <div className="alert-step-body">
                  <strong>機器人回覆並確認連線</strong>
                  <p>群組內收到機器人回覆成功後，點擊下方「檢查綁定狀態」，群組資訊即會呈現在本頁面上。</p>
                </div>
              </div>
            </div>

            <div className="alert-onboarding-footer">
              <button
                type="button"
                className="mock-primary-btn alert-check-status-btn"
                onClick={() => setReloadKey((v) => v + 1)}
                disabled={loading || busy}
              >
                <RefreshCw aria-hidden="true" className={loading ? 'spin' : ''} /> {loading ? '檢查中…' : '檢查綁定狀態'}
              </button>
              <span className="field-hint alert-onboarding-subtext">
                通知對象會由正式 LINE 群組綁定流程建立；本頁不會自行新增或猜測群組。
              </span>
            </div>
          </div>
        )}

        {/* 已綁定群組時的核心管理卡片 */}
        {!loading && groupTarget && (
          <div className="alert-group-target-card">
            <div className="alert-group-target-header">
              <div className="alert-group-title-box">
                <span className="alert-group-avatar" aria-hidden="true"><Users /></span>
                <div>
                  <div className="alert-group-headline">
                    <h3 className="alert-group-name">{groupTarget.display_label}</h3>
                    <span className={`line-status ${groupTarget.state === 'active' ? 'line-status-resolved' : 'line-status-waiting'}`}>
                      {groupTarget.state === 'active' ? '🟢 接收中（啟用）' : '🟡 已暫停（停用）'}
                    </span>
                  </div>
                  <p className="field-hint">目標 ID #{groupTarget.target_id} · 最近更新：{groupTarget.updated_at}</p>
                </div>
              </div>

              <div className="alert-group-quick-actions">
                <button
                  type="button"
                  className={`line-action-toggle-btn ${groupTarget.state === 'active' ? 'btn-pause' : 'btn-resume'}`}
                  onClick={() => void previewToggle(groupTarget)}
                  disabled={busy}
                >
                  {groupTarget.state === 'active' ? (
                    <><BellOff aria-hidden="true" /> 暫停接收通知</>
                  ) : (
                    <><Bell aria-hidden="true" /> 恢復接收通知</>
                  )}
                </button>
              </div>
            </div>

            <div className="line-detail-grid alert-security-detail-grid">
              <div><span>目前綁定之群組名稱</span><strong>{groupTarget.display_label}</strong></div>
              <div><span>推播啟用狀態</span><strong>{stateLabel(groupTarget.state)}</strong></div>
              <div><span>告警門檻等級</span><strong>{minimumStatusLabel(groupTarget.minimum_status)}</strong></div>
              <div><span>綁定／更新時間</span><strong>{groupTarget.updated_at}</strong></div>
            </div>

            <div className="line-events alert-security-lock-note">
              <h3>單一互斥鎖定保護</h3>
              <p className="alert-security-explanation">
                系統只允許一個啟用中的群組。新增或替換必須先檢查影響，並由已登入且啟用的內部使用者確認，
                不能由聊天室文字或畫面自行覆蓋正式設定。
              </p>
            </div>
          </div>
        )}

        {/* 所有登錄對象列表 */}
        <div className="line-grid-cards">
          {targets.map((target) => (
            <article className="line-info-card" key={target.target_id}>
              <div className="line-section-heading">
                <strong>{target.display_label}</strong>
                <span className={`line-status ${target.state === 'active' ? 'line-status-resolved' : 'line-status-waiting'}`}>
                  {target.state === 'active' ? '啟用' : '停用'}
                </span>
              </div>
              <div className="line-detail-grid alert-security-detail-grid">
                <div><span>對象類型</span><strong>{target.target_kind === 'group' ? 'LINE 群組' : '內部使用者'}</strong></div>
                <div><span>通知範圍</span><strong>{minimumStatusLabel(target.minimum_status)}</strong></div>
                <div><span>更新時間</span><strong>{target.updated_at}</strong></div>
              </div>
              <div className="line-actions line-block-spacing">
                <button
                  type="button"
                  className="line-secondary-btn"
                  onClick={() => void previewToggle(target)}
                  disabled={busy}
                >
                  檢查{target.state === 'active' ? '停用' : '啟用'}影響
                </button>
              </div>
              {target.target_kind === 'group' && target.state !== 'active' && (
                <p className="field-hint">此群組已解除，不會由網頁或 webhook 靜默重新啟用；請在新的 LINE 群組走正式登錄流程。</p>
              )}
            </article>
          ))}
        </div>
      </section>

      {/* ========================================================================= */}
      {/* 核心功能：群組訊息推播類型管理與即時手機模擬預覽 */}
      {/* ========================================================================= */}
      <section className="line-workspace-card alert-msg-control-section" aria-labelledby="alert-msg-control-title">
        <div className="line-section-heading">
          <div>
            <h2 id="alert-msg-control-title">
              <SlidersHorizontal aria-hidden="true" style={{ width: 20, height: 20, verticalAlign: 'middle', marginRight: 8 }} />
              群組訊息推播分類與即時預覽
            </h2>
            <p>設定此幹部群組要出現哪些訊息；點選不同分類可在右側直接預覽手機 LINE 接收到的排版樣式。</p>
          </div>
          {prefSaving && (
            <div className="alert-save-tip" role="status">
              <RefreshCw aria-hidden="true" className="spin" style={{ width: 14, height: 14, marginRight: 4 }} /> 同步儲存至資料庫中…
            </div>
          )}
          {!prefSaving && savedSuccessTip && (
            <div className="alert-save-tip" role="status">
              <Check aria-hidden="true" /> {savedSuccessTip}
            </div>
          )}
        </div>

        <div className="alert-msg-workbench-layout">
          {/* 左側：訊息種類開關列表 */}
          <div className="alert-msg-list">
            {MESSAGE_CATEGORIES.map((category) => {
              const isEnabled = categoryPreferences[category.key];
              const isSelected = activePreviewKey === category.key;
              return (
                <div
                  key={category.key}
                  className={`alert-msg-card ${isSelected ? 'selected' : ''} ${isEnabled ? 'enabled' : 'disabled'}`}
                  onClick={() => setActivePreviewKey(category.key)}
                >
                  <div className="alert-msg-card-top">
                    <div className="alert-msg-badge-row">
                      <span className="alert-msg-badge">{category.badge}</span>
                      <span className={`alert-msg-status-tag ${isEnabled ? 'tag-enabled' : 'tag-disabled'}`}>
                        {isEnabled ? '🟢 允許推播' : '⚪ 已過濾 (不發送)'}
                      </span>
                    </div>
                    <label className="alert-msg-switch" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={isEnabled}
                        disabled={prefSaving}
                        onChange={() => void handleToggleCategory(category.key)}
                        aria-label={`切換${category.label}`}
                      />
                      <span className="slider round"></span>
                    </label>
                  </div>

                  <strong className="alert-msg-name">{category.label}</strong>
                  <p className="alert-msg-desc">{category.description}</p>

                  <div className="alert-msg-card-bottom">
                    <button
                      type="button"
                      className="alert-preview-trigger-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        setActivePreviewKey(category.key);
                      }}
                    >
                      <Eye aria-hidden="true" style={{ width: 14, height: 14 }} /> 檢視群組訊息效果
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          {/* 右側：手機 LINE 群組訊息模擬預覽 */}
          <div className="alert-phone-mockup-wrapper">
            <div className="alert-phone-mockup">
              <div className="alert-phone-speaker"></div>
              <div className="alert-phone-header">
                <span>LINE 幹部通知群組 (預覽)</span>
              </div>
              <div className="alert-phone-screen">
                <div className="alert-mock-chat-bubble-wrap">
                  <div className="alert-mock-avatar" style={{ backgroundColor: activeMeta.avatarColor }}>
                    <Users aria-hidden="true" style={{ width: 16, height: 16 }} />
                  </div>
                  <div className="alert-mock-bubble-box">
                    <span className="alert-mock-sender">{activeMeta.senderName}</span>
                    {activeMeta.isFlex ? (
                      <div className={`alert-mock-flex-card ${!categoryPreferences[activeMeta.key] ? 'alert-mock-filtered' : ''}`}>
                        <div className="alert-mock-flex-body">
                          <h4 className="alert-mock-flex-title">{activeMeta.flexTitle}</h4>
                          <div className="alert-mock-flex-case">案件編號：{activeMeta.flexCaseNo}</div>
                          <p className="alert-mock-flex-text">{activeMeta.flexBody}</p>
                        </div>
                        <div className="alert-mock-flex-footer">
                          <button type="button" className="alert-mock-flex-btn" tabIndex={-1}>
                            {activeMeta.flexBtnLabel}
                          </button>
                        </div>
                        {!categoryPreferences[activeMeta.key] && (
                          <div className="alert-mock-filtered-overlay">
                            <span className="alert-mock-filtered-text">🚫 此分類已被過濾（群組不推播）</span>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div
                        className={`alert-mock-bubble ${
                          activeMeta.key === 'customer_service' || activeMeta.key === 'staff_leave_urgent'
                            ? 'bubble-urgent'
                            : ''
                        } ${!categoryPreferences[activeMeta.key] ? 'alert-mock-filtered' : ''}`}
                      >
                        <h4 className="alert-mock-title">{activeMeta.sampleTitle}</h4>
                        <div className="alert-mock-content">
                          {activeMeta.sampleRows?.map((row, idx) => (
                            <div className="alert-mock-row" key={idx}>
                              <span className="alert-mock-label">{row.label}：</span>
                              <span className="alert-mock-val">{row.value}</span>
                            </div>
                          ))}
                        </div>
                        {activeMeta.sampleAction && (
                          <div className="alert-mock-action">
                            {activeMeta.sampleAction}
                          </div>
                        )}
                        {!categoryPreferences[activeMeta.key] && (
                          <div className="alert-mock-filtered-overlay">
                            <span className="alert-mock-filtered-text">🚫 此分類已被過濾（群組不推播）</span>
                          </div>
                        )}
                      </div>
                    )}
                    <span className="alert-mock-time">{activeMeta.senderTime}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="alert-phone-tip-box">
              <strong>💡 訊息說明與配置建議：</strong>
              <p>{activeMeta.tipText}</p>
              {!categoryPreferences[activeMeta.key] && (
                <div className="alert-status-callout muted">
                  🛡️ <strong>此訊息目前已被您關閉</strong>：當觸發相關事件時，系統<strong>不會</strong>將此訊息推播到幹部 LINE 群組。
                </div>
              )}
              {categoryPreferences[activeMeta.key] && (
                <div className="alert-status-callout active">
                  📢 <strong>此訊息目前已開啟接收</strong>：當觸發此類事件時，幹部群組會即時收到上方預覽卡片。
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* 通知對象異動與解除綁定 */}
      <section className="line-workspace-card alert-security-change-section" aria-labelledby="alert-change-title">
        <div className="line-section-heading">
          <div>
            <h2 id="alert-change-title">群組異動與安全解除</h2>
            <p>更換幹部群組前，必須先檢查影響，確認後才允許重新配對。</p>
          </div>
        </div>

        <label htmlFor="line-security-reason">異動原因（系統操作稽核紀錄）</label>
        <textarea
          id="line-security-reason"
          className="line-textarea"
          rows={2}
          maxLength={240}
          value={reason}
          onChange={(event) => {
            setReason(event.target.value);
            clearCandidate();
          }}
          disabled={busy}
          aria-describedby="line-security-reason-help"
        />
        <div id="line-security-reason-help" className="field-hint alert-security-reason-help">
          <span>修改原因後必須重新檢查變更影響。</span>
          <span>{reason.length} / 240</span>
        </div>

        {groupTarget && (
          <div className="alert-security-reset-row">
            <div>
              <strong>解除目前異常通知群組</strong>
              <p className="field-hint">
                會保留歷史紀錄，將目前唯一有效群組解除為停用；固定先檢查影響、明確確認、套用，再重新查詢結果。
              </p>
            </div>
            <button
              type="button"
              className="line-warning-btn"
              onClick={() => void previewGroupReset(groupTarget)}
              disabled={busy || groupTarget.state !== 'active'}
            >
              <RotateCcw aria-hidden="true" />預覽解除群組
            </button>
          </div>
        )}
        {groupTarget && groupTarget.state !== 'active' && (
          <p className="field-hint">此群組已解除；請在新的 LINE 群組走正式登錄流程。</p>
        )}
      </section>

      {/* 異動影響確認 Modal */}
      {pending && (
        <div className="line-workspace-card alert-security-preview-card">
          <h3 className="alert-security-preview-title"><SearchCheck aria-hidden="true" />異動影響確認</h3>
          <div className="line-detail-grid alert-security-detail-grid">
            <div><span>操作</span><strong>{pending.kind === 'group_reset' ? '解除目前群組' : '變更通知啟用狀態'}</strong></div>
            <div><span>對象</span><strong>{pending.target.display_label}</strong></div>
            <div><span>目前狀態</span><strong>{stateLabel(pending.preview.previous_state)}</strong></div>
            <div><span>變更後狀態</span><strong>{stateLabel(pending.preview.resulting_state)}</strong></div>
          </div>
          <label className="checkbox-item line-block-spacing">
            <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
            {pending.kind === 'group_reset'
              ? '我已核對目前群組將從有效通知群組解除，確認套用此異動。'
              : '我已核對目前狀態、變更後狀態與影響範圍，確認套用此異動。'}
          </label>
          <div className="line-actions line-block-spacing">
            <button
              type="button"
              className="mock-primary-btn"
              onClick={() => void applyPending()}
              disabled={!confirmed || busy}
            >
              {busy ? '套用中…' : pending.kind === 'group_reset' ? '確認解除群組' : '確認套用'}
            </button>
            <button type="button" className="line-secondary-btn" onClick={clearCandidate} disabled={busy}>
              取消
            </button>
          </div>
        </div>
      )}

      {receipt && (
        <div className="line-success" role="status">
          <strong className="alert-security-receipt-title">
            <CheckCircle2 aria-hidden="true" />
            {receipt.operation === 'group_reset' ? '通知群組已解除' : '通知對象已更新'}
          </strong>
          <div>{stateLabel(receipt.previous_state)} → {stateLabel(receipt.resulting_state)}</div>
          {readbackMessage && <div>{readbackMessage}</div>}
        </div>
      )}
    </div>
  );
};
