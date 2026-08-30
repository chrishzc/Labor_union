/**
 * File: AnomaliesPage.tsx
 * Description: 顯示異常根因，並依 owner form schema 路由可回讀驗證的人工修正工作區。
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { CurrentAnomaliesPage } from './CurrentAnomaliesPage';
import './AnomaliesPage.css';
import { Drawer } from '../components/Drawer';
import { ClientOverRefundRecoveryWorkbench } from '../components/ClientOverRefundRecoveryWorkbench';
import { GovernmentOverpaymentRecoveryWorkbench, type GovernmentOverpaymentRefreshResult } from '../components/GovernmentOverpaymentRecoveryWorkbench';
import { StaffOverpaymentRecoveryActions } from '../components/StaffOverpaymentRecoveryActions';
import { StaffPayoutRemediationWorkbench } from '../components/StaffPayoutRemediationWorkbench';
import { HistoricalOrderReviewRemediationWorkbench } from '../components/HistoricalOrderReviewRemediationWorkbench';
import { HistoricalOperationalBaselineReadback } from '../components/HistoricalOperationalBaselineReadback';
import { ClientSettlementRemediationWorkbench } from '../components/ClientSettlementRemediationWorkbench';
import { anomalyQueryClient } from '../api/anomalies/anomaly_query_client';
import { AnomalyValidationError } from '../api/anomalies/anomaly_query_errors';
import { anomalyDetailClient } from '../api/anomalies/anomaly_detail_client';
import { AnomalyDetailError } from '../api/anomalies/anomaly_detail_errors';
import type { AnomalyRecoveryContextView, RecoveryAction } from '../api/anomalies/anomaly_detail_schemas';
import {
  financeImportCorrectionClient,
  type FinanceImportCorrectionJobAccepted,
  type FinanceImportCorrectionJobOutcome,
  type FinanceImportCorrectionPreview,
  type FinanceImportCorrectionSelection,
} from '../api/finance_import/finance_import_correction_client';
import { importWarningTransitionClient } from '../api/import_warning/import_warning_transition_client';
import { ImportWarningTransitionError } from '../api/import_warning/import_warning_transition_errors';
import type { WarningTransitionRequest } from '../api/import_warning/import_warning_transition_schemas';
import {
  adaptImportWarningTransitionPreview,
  adaptImportWarningTransitionReceipt,
  type ImportWarningTransitionPreviewViewModel,
  type ImportWarningTransitionReceiptViewModel,
} from '../adapters/import_warning/import_warning_transition_adapter';
import {
  adaptAnomalyDetailBundle,
  visibleEvidenceItems,
  type AnomalyDetailBundleViewModel,
} from '../adapters/anomalies/anomaly_detail_adapter';
import {
  adaptAnomalySummary,
  adaptImportWarningTask,
  adaptImportWarningReferral,
  mapImportWarningLaneLabel,
  mapImportWarningStatusLabel,
  calculateAnomalyKPIs,
  filterAnomalies,
  CATEGORY_TAB_KEYS,
  type CategoryTabKey,
  type AnomalySummaryViewModel,
  type ImportWarningTaskViewModel,
  type ImportWarningReferralViewModel,
} from '../adapters/anomalies/anomaly_query_adapter';
import { financeOwnerRecoveryTarget, payoutOwnerDetailTarget, type FinanceOwnerRecoveryTarget } from '../adapters/anomalies/finance_owner_recovery_target';
import { clientSettlementTarget, type ClientSettlementTarget } from '../adapters/anomalies/client_settlement_target';

type WarningFlowStatus =
  | 'idle' | 'editing' | 'preview_loading' | 'preview_ready' | 'apply_pending'
  | 'receipt_received' | 'requery_loading' | 'observed' | 'stale'
  | 'outcome_unknown' | 'observation_failed' | 'typed_error';

type CorrectionFlowStatus = 'idle' | 'preview_loading' | 'preview_ready' | 'apply_pending' | 'accepted' | 'observing' | 'completed' | 'typed_error';

function anomalyDetailErrorMessage(error: unknown, subject: '詳情' | '處理方式'): string {
  if (error instanceof AnomalyDetailError) {
    if (error.code === 'NOT_FOUND') return subject === '處理方式'
      ? '目前沒有可用的系統處理方式，請交由對應業務負責人處理。'
      : '目前沒有可顯示的異常詳情。';
    if (error.code === 'UNAUTHENTICATED') return '登入已失效，請重新登入後再試。';
    if (error.code === 'FORBIDDEN') return '目前帳號無法查看這項資料。';
    if (error.retryable) return `${subject}暫時無法載入，請稍後重試。`;
  }
  return `${subject}資料無法使用，請聯絡管理員。`;
}

const ANOMALY_PAGE_SIZE = 200;
const FINANCE_CORRECTION_CONTRACTS = {
  classify_and_post_bank_row: {
    operations: ['PreviewCorrectAndPostFinanceImportRow', 'CorrectAndPostFinanceImportRow'],
    inputs: ['classification_type', 'evidence', 'reason', 'target_obligation_identities'],
    completion: 'finance_import_manual_review_cleared',
  },
  classify_client_refund_return: {
    operations: ['PreviewCorrectAndPostClientRefundReturn', 'CorrectAndPostClientRefundReturn'],
    inputs: ['evidence', 'reason', 'refund_ledger_entry_identity', 'target_obligation_identities'],
    completion: 'client_refund_return_cleared',
  },
} as const;

function warningKey(prefix: string): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') return `${prefix}-${globalThis.crypto.randomUUID()}`;
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

function financeCorrectionAction(context: AnomalyRecoveryContextView | null): RecoveryAction | null {
  if (!context) return null;
  return context.available_actions.find((action) => {
    const contract = FINANCE_CORRECTION_CONTRACTS[action.action_key as keyof typeof FINANCE_CORRECTION_CONTRACTS];
    return contract !== undefined
      && action.form_schema_key === 'finance_import.correction.v1'
      && action.action_contract_version === 1
      && action.owning_domain === 'finance_import'
      && action.required_capability === 'finance_import.correct_and_post'
      && action.requires_preview
      && action.preview_operation === contract.operations[0]
      && action.apply_operation === contract.operations[1]
      && action.completion_predicate === contract.completion
      && action.source_binding_keys.join('|') === 'finance_import_row_identity|source_version'
      && action.required_operator_inputs.join('|') === contract.inputs.join('|')
      && action.source_bindings.length === 2;
  }) ?? null;
}

function correctionClassification(action: RecoveryAction): FinanceImportCorrectionSelection['classification_type'] {
  return action.action_key === 'classify_client_refund_return' ? 'client_refund_return' : 'client_receipt';
}

function correctionClassificationLabel(classification: string): string {
  const labels: Record<string, string> = {
    client_receipt: '客戶收款',
    client_refund: '客戶退款',
    client_refund_return: '客戶退款退匯',
    client_subsidy_return: '客戶補助退回',
    government_subsidy: '政府補助',
    staff_payout: '月嫂付款',
  };
  return labels[classification] ?? '待確認分類';
}

function correctionBinding(action: RecoveryAction, key: string): string | number | null {
  return action.source_bindings.find((binding) => binding.key === key)?.value ?? null;
}

export const LegacyAnomaliesPage: React.FC = () => {
  const [selectedCategory, setSelectedCategory] = useState<CategoryTabKey>('全部');
  const [selectedStatusFilter, setSelectedStatusFilter] = useState<'all' | 'open' | 'claimed' | 'resolved'>('all');
  const [selectedAnomaly, setSelectedAnomaly] = useState<AnomalySummaryViewModel | null>(null);
  const [selectedWarning, setSelectedWarning] = useState<ImportWarningTaskViewModel | null>(null);

  const [anomalyDetail, setAnomalyDetail] = useState<AnomalyDetailBundleViewModel | null>(null);
  const [anomalyRecovery, setAnomalyRecovery] = useState<AnomalyRecoveryContextView | null>(null);
  const [payoutDetailTarget, setPayoutDetailTarget] = useState<Extract<FinanceOwnerRecoveryTarget, { kind: 'staff_payout' }> | null>(null);
  const [clientSettlement, setClientSettlement] = useState<ClientSettlementTarget | null>(null);
  const [anomalyDetailLoading, setAnomalyDetailLoading] = useState(false);
  const [anomalyDetailError, setAnomalyDetailError] = useState<string | null>(null);
  const [anomalyRecoveryError, setAnomalyRecoveryError] = useState<string | null>(null);
  const [warningReferral, setWarningReferral] = useState<ImportWarningReferralViewModel | null>(null);
  const [warningReferralLoading, setWarningReferralLoading] = useState(false);
  const [warningReferralError, setWarningReferralError] = useState<string | null>(null);
  const [warningFlowStatus, setWarningFlowStatus] = useState<WarningFlowStatus>('idle');
  const [warningAction, setWarningAction] = useState<WarningTransitionRequest['target_status']>('awaiting_external_confirmation');
  const [warningReason, setWarningReason] = useState('');
  const [warningPreview, setWarningPreview] = useState<ImportWarningTransitionPreviewViewModel | null>(null);
  const [warningReceipt, setWarningReceipt] = useState<ImportWarningTransitionReceiptViewModel | null>(null);
  const [warningFlowError, setWarningFlowError] = useState<string | null>(null);
  const [correctionClassificationType, setCorrectionClassificationType] = useState<FinanceImportCorrectionSelection['classification_type']>('client_receipt');
  const [correctionObligations, setCorrectionObligations] = useState('');
  const [correctionRefundLedgerEntry, setCorrectionRefundLedgerEntry] = useState('');
  const [correctionReason, setCorrectionReason] = useState('');
  const [correctionEvidence, setCorrectionEvidence] = useState('');
  const [correctionPreview, setCorrectionPreview] = useState<FinanceImportCorrectionPreview | null>(null);
  const [correctionAccepted, setCorrectionAccepted] = useState<FinanceImportCorrectionJobAccepted | null>(null);
  const [correctionOutcome, setCorrectionOutcome] = useState<FinanceImportCorrectionJobOutcome | null>(null);
  const [correctionFlowStatus, setCorrectionFlowStatus] = useState<CorrectionFlowStatus>('idle');
  const [correctionError, setCorrectionError] = useState<string | null>(null);

  // Dual-lane State: Anomalies
  const [anomalies, setAnomalies] = useState<AnomalySummaryViewModel[]>([]);
  const [anomaliesLoading, setAnomaliesLoading] = useState<boolean>(true);
  const [anomaliesLoadingMore, setAnomaliesLoadingMore] = useState<boolean>(false);
  const [anomaliesHasMore, setAnomaliesHasMore] = useState<boolean>(false);
  const [anomaliesError, setAnomaliesError] = useState<string | null>(null);

  // Dual-lane State: Import Warnings
  const [importWarnings, setImportWarnings] = useState<ImportWarningTaskViewModel[]>([]);
  const [importWarningsLoading, setImportWarningsLoading] = useState<boolean>(true);
  const [importWarningsError, setImportWarningsError] = useState<string | null>(null);

  // Race condition guards
  const anomalyRequestSeq = useRef<number>(0);
  const anomalyNextOffset = useRef<number>(0);
  const latestAnomalyRefresh = useRef<{ succeeded: boolean; snapshot: AnomalySummaryViewModel[] }>({ succeeded: false, snapshot: [] });
  const importWarningRequestSeq = useRef<number>(0);
  const drawerRequestSeq = useRef<number>(0);
  const drawerAbortController = useRef<AbortController | null>(null);
  const warningFlowSeq = useRef(0);
  const warningPreviewKey = useRef(warningKey('warning-preview'));
  const warningApplyKey = useRef(warningKey('warning-apply'));
  const warningCorrelationId = useRef(warningKey('warning-transition'));
  const correctionFlowSeq = useRef(0);
  const correctionApplyKey = useRef(warningKey('finance-correction-apply'));
  const correctionCorrelationId = useRef(warningKey('finance-correction'));
  const warningFlowLocked = ['apply_pending', 'receipt_received', 'requery_loading', 'outcome_unknown'].includes(warningFlowStatus);
  const correctionFlowLocked = correctionFlowStatus === 'apply_pending' || correctionFlowStatus === 'observing';
  const drawerFlowLocked = warningFlowLocked || correctionFlowLocked;
  const drawerLockReason = correctionFlowLocked
    ? '帳務更正正在提交或確認結果；為避免結果不明，目前不能關閉或切換篩選。'
    : warningFlowLocked
      ? '追蹤狀態正在提交或確認結果；為避免重複操作，目前不能關閉或切換篩選。'
      : null;
  const correctionApplyDisabledReason = correctionFlowStatus === 'preview_ready'
    ? null
    : correctionFlowLocked
      ? '帳務更正正在提交或確認結果，請等待目前流程完成。'
      : correctionFlowStatus === 'completed'
        ? '本次帳務更正已完成；如需其他修正，請重新開啟對應異常。'
        : '請先完成更正影響檢查；修改任何內容後都必須重新檢查。';
  const warningPreviewDisabledReason = warningFlowLocked
    ? '追蹤狀態正在提交或確認結果，請等待目前流程完成。'
    : !warningReason.trim()
      ? '請先填寫處理說明，再檢查狀態變更影響。'
      : warningFlowStatus === 'preview_loading'
        ? '正在檢查狀態變更影響。'
        : null;
  const warningApplyDisabledReason = warningFlowStatus === 'preview_ready'
    ? null
    : warningFlowLocked
      ? '追蹤狀態正在提交或確認結果，請等待目前流程完成。'
      : '請先完成狀態變更影響檢查；修改內容後必須重新檢查。';

  // Fetch Anomalies from live API
  const fetchAnomalies = useCallback(async (requireSuccess = false, originalFingerprint?: string): Promise<GovernmentOverpaymentRefreshResult> => {
    const seq = ++anomalyRequestSeq.current;
    latestAnomalyRefresh.current = { succeeded: false, snapshot: [] };
    setAnomaliesLoading(true);
    setAnomaliesError(null);

    try {
      const rawList = await anomalyQueryClient.queryAnomalies({ activeOnly: true, limit: ANOMALY_PAGE_SIZE, offset: 0 });
      const adaptedList = rawList.map(adaptAnomalySummary);
      if (seq === anomalyRequestSeq.current) {
        setAnomalies(adaptedList);
        anomalyNextOffset.current = rawList.length;
        setAnomaliesHasMore(rawList.length === ANOMALY_PAGE_SIZE);
      }
      if (seq === anomalyRequestSeq.current) latestAnomalyRefresh.current = { succeeded: true, snapshot: adaptedList };
      if (seq !== anomalyRequestSeq.current) return { succeeded: false, originalFingerprintPresent: true };
      return {
        succeeded: true,
        originalFingerprintPresent: originalFingerprint !== undefined
          && adaptedList.some((anomaly) => anomaly.fingerprint === originalFingerprint),
      };
    } catch (err) {
      if (seq === anomalyRequestSeq.current) {
        const msg = err instanceof Error ? err.message : '載入異常資料失敗';
        setAnomaliesError(msg);
      }
      if (requireSuccess) throw err;
      return { succeeded: false, originalFingerprintPresent: true };
    } finally {
      if (seq === anomalyRequestSeq.current) {
        setAnomaliesLoading(false);
      }
    }
  }, []);

  const loadMoreAnomalies = useCallback(async () => {
    const seq = ++anomalyRequestSeq.current;
    const offset = anomalyNextOffset.current;
    setAnomaliesLoadingMore(true);
    setAnomaliesError(null);
    try {
      const rawList = await anomalyQueryClient.queryAnomalies({ activeOnly: true, limit: ANOMALY_PAGE_SIZE, offset });
      if (seq === anomalyRequestSeq.current) {
        const adaptedList = rawList.map(adaptAnomalySummary);
        setAnomalies((current) => {
          const known = new Set(current.map((item) => item.id));
          return [...current, ...adaptedList.filter((item) => !known.has(item.id))];
        });
        anomalyNextOffset.current = offset + rawList.length;
        setAnomaliesHasMore(rawList.length === ANOMALY_PAGE_SIZE);
      }
    } catch (err) {
      if (seq === anomalyRequestSeq.current) {
        setAnomaliesError(err instanceof Error ? err.message : '載入更多異常資料失敗');
      }
    } finally {
      if (seq === anomalyRequestSeq.current) setAnomaliesLoadingMore(false);
    }
  }, []);

  // Fetch Import Warning Tasks from live API
  const fetchImportWarnings = useCallback(async () => {
    const seq = ++importWarningRequestSeq.current;
    setImportWarningsLoading(true);
    setImportWarningsError(null);

    try {
      const rawTasks = await anomalyQueryClient.queryImportWarningTasks({ activeOnly: true });
      if (seq === importWarningRequestSeq.current) {
        const adaptedTasks = rawTasks.map(adaptImportWarningTask);
        setImportWarnings(adaptedTasks);
      }
    } catch (err) {
      if (seq === importWarningRequestSeq.current) {
        const msg = err instanceof Error ? err.message : '載入匯入警示資料失敗';
        setImportWarningsError(msg);
      }
    } finally {
      if (seq === importWarningRequestSeq.current) {
        setImportWarningsLoading(false);
      }
    }
  }, []);

  const closeDrawer = useCallback(() => {
    if (drawerFlowLocked) return;
    drawerRequestSeq.current += 1;
    correctionFlowSeq.current += 1;
    drawerAbortController.current?.abort();
    drawerAbortController.current = null;
    setSelectedAnomaly(null);
    setSelectedWarning(null);
    setAnomalyDetail(null);
    setAnomalyRecovery(null);
    setPayoutDetailTarget(null);
    setClientSettlement(null);
    setWarningReferral(null);
    setAnomalyDetailLoading(false);
    setWarningReferralLoading(false);
    setWarningFlowStatus('idle');
    setWarningPreview(null);
    setWarningReceipt(null);
    setWarningFlowError(null);
    setCorrectionPreview(null);
    setCorrectionAccepted(null);
    setCorrectionOutcome(null);
    setCorrectionFlowStatus('idle');
    setCorrectionError(null);
  }, [drawerFlowLocked]);

  const openAnomalyDrawer = useCallback((anomaly: AnomalySummaryViewModel) => {
    const seq = ++drawerRequestSeq.current;
    correctionFlowSeq.current += 1;
    drawerAbortController.current?.abort();
    const controller = new AbortController();
    drawerAbortController.current = controller;
    setSelectedAnomaly(anomaly);
    setSelectedWarning(null);
    setAnomalyDetail(null);
    setAnomalyRecovery(null);
    setPayoutDetailTarget(null);
    setClientSettlement(null);
    setAnomalyDetailError(null);
    setAnomalyRecoveryError(null);
    setAnomalyDetailLoading(true);
    setWarningReferral(null);
    void Promise.allSettled([
      anomalyDetailClient.queryAnomalyDetail({ fingerprint: anomaly.fingerprint }, { signal: controller.signal }),
      anomaly.issueKey
        ? anomalyDetailClient.queryAnomalyRecovery(
          { issueKey: anomaly.issueKey },
          { signal: controller.signal },
        )
        : Promise.reject(new AnomalyDetailError('NOT_FOUND', '目前沒有 current issue key。')),
    ])
      .then(([detailResult, recoveryResult]) => {
        if (seq === drawerRequestSeq.current && !controller.signal.aborted) {
          if (detailResult.status === 'rejected') throw detailResult.reason;
          const recovery = recoveryResult.status === 'fulfilled' ? recoveryResult.value : null;
          setAnomalyDetail(adaptAnomalyDetailBundle(detailResult.value, recovery));
          setAnomalyRecovery(recovery);
          const payoutDetailFallbackAllowed = recoveryResult.status === 'fulfilled'
            ? recoveryResult.value.available_actions.length === 0
            : recoveryResult.reason instanceof AnomalyDetailError
              && recoveryResult.reason.code === 'NOT_FOUND';
          setPayoutDetailTarget(
            payoutDetailFallbackAllowed
              ? payoutOwnerDetailTarget(detailResult.value)
              : null,
          );
          setClientSettlement(clientSettlementTarget(detailResult.value));
          const action = financeCorrectionAction(recovery);
          correctionApplyKey.current = warningKey('finance-correction-apply');
          correctionCorrelationId.current = warningKey('finance-correction');
          setCorrectionPreview(null);
          setCorrectionAccepted(null);
          setCorrectionOutcome(null);
          setCorrectionFlowStatus('idle');
          setCorrectionError(null);
          setCorrectionClassificationType(action ? correctionClassification(action) : 'client_receipt');
          const actionBindings = action?.source_bindings ?? [];
          const bindingValue = (key: string) => actionBindings.find((binding) => binding.key === key)?.value;
          const obligationIdentities = bindingValue('target_obligation_identities');
          setCorrectionObligations(typeof obligationIdentities === 'string' ? obligationIdentities : '');
          const refundLedgerEntry = bindingValue('original_refund_ledger_entry_identity');
          setCorrectionRefundLedgerEntry(typeof refundLedgerEntry === 'string' ? refundLedgerEntry : '');
          setCorrectionReason('');
          setCorrectionEvidence('');
          if (recoveryResult.status === 'rejected' && anomaly.code !== 'HISTORICAL-ORDER-001') {
            setAnomalyRecoveryError(anomalyDetailErrorMessage(recoveryResult.reason, '處理方式'));
          }
        }
      })
      .catch((err: unknown) => {
        if (seq === drawerRequestSeq.current && !controller.signal.aborted) {
          setAnomalyDetailError(anomalyDetailErrorMessage(err, '詳情'));
        }
      })
      .finally(() => {
        if (seq === drawerRequestSeq.current && !controller.signal.aborted) {
          setAnomalyDetailLoading(false);
        }
      });
  }, []);

  const openWarningDrawer = useCallback((warning: ImportWarningTaskViewModel) => {
    const seq = ++drawerRequestSeq.current;
    correctionFlowSeq.current += 1;
    drawerAbortController.current?.abort();
    const controller = new AbortController();
    drawerAbortController.current = controller;
    setSelectedWarning(warning);
    setSelectedAnomaly(null);
    setWarningReferral(null);
    setWarningReferralError(null);
    setWarningReferralLoading(true);
    setAnomalyDetail(null);
    setClientSettlement(null);
    warningFlowSeq.current += 1;
    warningPreviewKey.current = warningKey('warning-preview');
    warningApplyKey.current = warningKey('warning-apply');
    warningCorrelationId.current = warningKey('warning-transition');
    setWarningFlowStatus('idle');
    setWarningAction('awaiting_external_confirmation');
    setWarningReason('');
    setWarningPreview(null);
    setWarningReceipt(null);
    setWarningFlowError(null);
    void anomalyQueryClient
      .queryImportWarningReferral(
        {
          occurrenceIdentity: warning.occurrenceIdentity,
          expectedVersion: warning.version,
        },
        { signal: controller.signal }
      )
      .then((referral) => {
        if (seq === drawerRequestSeq.current && !controller.signal.aborted) {
          setWarningReferral(adaptImportWarningReferral(referral));
        }
      })
      .catch((err: unknown) => {
        if (seq === drawerRequestSeq.current && !controller.signal.aborted) {
          setWarningReferralError(
            err instanceof AnomalyValidationError && err.upstreamCode === 'import_warning_referral_unavailable'
              ? '此警示尚未支援來源修復；可更新追蹤狀態，但不會修改來源根事實。'
              : err instanceof Error ? err.message : '轉介資訊暫時無法取得，請關閉後重試。',
          );
        }
      })
      .finally(() => {
        if (seq === drawerRequestSeq.current && !controller.signal.aborted) {
          setWarningReferralLoading(false);
        }
      });
  }, []);

  const invalidateWarningPreview = () => {
    if (warningFlowLocked) return;
    warningFlowSeq.current += 1;
    warningPreviewKey.current = warningKey('warning-preview');
    warningApplyKey.current = warningKey('warning-apply');
    warningCorrelationId.current = warningKey('warning-transition');
    setWarningPreview(null);
    setWarningReceipt(null);
    setWarningFlowError(null);
    setWarningFlowStatus('editing');
  };

  const warningRequest = (): WarningTransitionRequest | null => {
    if (!selectedWarning || !warningReason.trim()) return null;
    return {
      expected_version: selectedWarning.version,
      target_status: warningAction,
      reason_code: warningReason.trim(),
      note: null,
      evidence_reference: selectedWarning.evidenceReference,
    };
  };

  const previewWarningTransition = async () => {
    const request = warningRequest();
    if (!selectedWarning || !request || warningFlowLocked) {
      setWarningFlowError('請先選擇轉態並輸入理由。');
      return;
    }
    const seq = ++warningFlowSeq.current;
    setWarningFlowStatus('preview_loading');
    setWarningFlowError(null);
    try {
      const preview = adaptImportWarningTransitionPreview(await importWarningTransitionClient.preview(
        selectedWarning.occurrenceIdentity,
        request,
        { idempotencyKey: warningPreviewKey.current, correlationId: warningCorrelationId.current },
      ));
      if (seq !== warningFlowSeq.current) return;
      if (preview.occurrenceIdentity !== selectedWarning.occurrenceIdentity || preview.expectedVersion !== selectedWarning.version) {
        throw new Error('Preview identity 與目前匯入警示不一致。');
      }
      setWarningPreview(preview);
      setWarningFlowStatus('preview_ready');
    } catch (error) {
      if (seq !== warningFlowSeq.current) return;
      const typed = error instanceof ImportWarningTransitionError ? error : null;
      setWarningPreview(null);
      setWarningFlowStatus(typed?.code === 'IMPORT_WARNING_STALE' ? 'stale' : 'typed_error');
      setWarningFlowError(error instanceof Error ? error.message : 'Preview 無法完成。');
      if (typed?.code === 'IMPORT_WARNING_STALE') await fetchImportWarnings();
    }
  };

  const observeWarningReceipt = async (receipt: ImportWarningTransitionReceiptViewModel, seq: number) => {
    setWarningFlowStatus('requery_loading');
    try {
      const observed = adaptImportWarningTransitionReceipt(await importWarningTransitionClient.queryReceipt(
        receipt.receiptIdentity,
        { correlationId: warningCorrelationId.current },
      ));
      if (seq !== warningFlowSeq.current) return;
      if (
        observed.occurrenceIdentity !== receipt.occurrenceIdentity
        || observed.beforeStatus !== receipt.beforeStatus
        || observed.afterStatus !== receipt.afterStatus
        || observed.resultingVersion !== receipt.resultingVersion
        || observed.receiptIdentity !== receipt.receiptIdentity
        || observed.correlationId !== receipt.correlationId
      ) throw new Error('Receipt re-query 與 Apply receipt 不一致。');
      setWarningReceipt(observed);
      setWarningFlowStatus('observed');
      setWarningFlowError(null);
      setSelectedWarning((current) => current ? {
        ...current,
        status: observed.afterStatus,
        statusLabel: mapImportWarningStatusLabel(observed.afterStatus),
        version: observed.resultingVersion,
      } : current);
      setImportWarnings((items) => items.map((item) => item.occurrenceIdentity === observed.occurrenceIdentity ? {
        ...item,
        status: observed.afterStatus,
        statusLabel: mapImportWarningStatusLabel(observed.afterStatus),
        version: observed.resultingVersion,
      } : item));
    } catch (error) {
      if (seq !== warningFlowSeq.current) return;
      setWarningFlowStatus('observation_failed');
      setWarningFlowError(error instanceof Error ? error.message : 'Receipt 觀察失敗。');
    }
  };

  const applyWarningTransition = async (retry = false) => {
    const request = warningRequest();
    if (!selectedWarning || !request || !warningPreview) return;
    if (!retry && warningFlowStatus !== 'preview_ready') return;
    if (retry && warningFlowStatus !== 'outcome_unknown') return;
    const seq = retry ? warningFlowSeq.current : ++warningFlowSeq.current;
    setWarningFlowStatus('apply_pending');
    setWarningFlowError(null);
    try {
      const receipt = adaptImportWarningTransitionReceipt(await importWarningTransitionClient.apply(
        selectedWarning.occurrenceIdentity,
        request,
        { idempotencyKey: warningApplyKey.current, correlationId: warningCorrelationId.current },
      ));
      if (seq !== warningFlowSeq.current) return;
      if (
        receipt.occurrenceIdentity !== selectedWarning.occurrenceIdentity
        || receipt.beforeStatus !== selectedWarning.status
        || receipt.afterStatus !== warningPreview.resultingStatus
        || receipt.resultingVersion !== warningPreview.resultingVersion
      ) throw new Error('Apply receipt 與 Preview／warning identity 不一致。');
      setWarningReceipt(receipt);
      setWarningFlowStatus('receipt_received');
      await observeWarningReceipt(receipt, seq);
    } catch (error) {
      if (seq !== warningFlowSeq.current) return;
      const typed = error instanceof ImportWarningTransitionError ? error : null;
      if (typed?.outcomeUnknown) setWarningFlowStatus('outcome_unknown');
      else if (typed?.code === 'IMPORT_WARNING_STALE') {
        setWarningFlowStatus('stale');
        setWarningPreview(null);
        await fetchImportWarnings();
      } else setWarningFlowStatus('typed_error');
      setWarningFlowError(error instanceof Error ? error.message : 'Apply 無法完成。');
    }
  };

  const invalidateCorrectionPreview = () => {
    if (correctionFlowStatus === 'apply_pending' || correctionFlowStatus === 'observing') return;
    correctionFlowSeq.current += 1;
    correctionApplyKey.current = warningKey('finance-correction-apply');
    correctionCorrelationId.current = warningKey('finance-correction');
    setCorrectionPreview(null);
    setCorrectionAccepted(null);
    setCorrectionOutcome(null);
    setCorrectionError(null);
    setCorrectionFlowStatus('idle');
  };

  const correctionRequest = (): FinanceImportCorrectionSelection | null => {
    const action = financeCorrectionAction(anomalyRecovery);
    const rowIdentity = action ? correctionBinding(action, 'finance_import_row_identity') : null;
    const obligations = correctionObligations.split(/\r?\n/).map((value) => value.trim()).filter(Boolean);
    const evidence = correctionEvidence.split(/\r?\n/).map((value) => value.trim()).filter(Boolean);
    const refundLedgerEntry = correctionRefundLedgerEntry.trim();
    if (!action || typeof rowIdentity !== 'string' || !rowIdentity || !correctionReason.trim() || obligations.length === 0 || evidence.length === 0) return null;
    if (action.required_operator_inputs.includes('refund_ledger_entry_identity') && !refundLedgerEntry) return null;
    return {
      row_identity: rowIdentity,
      classification_type: action.action_key === 'classify_and_post_bank_row' ? correctionClassificationType : correctionClassification(action),
      target_obligation_identities: obligations,
      refund_ledger_entry_identity: refundLedgerEntry || null,
      allow_partial_refund_recovery: false,
      allow_refund_overage_recovery: false,
      allow_client_receipt_overage: false,
      reason: correctionReason.trim(),
      evidence,
    };
  };

  const previewCorrection = async () => {
    const request = correctionRequest();
    if (!request) {
      setCorrectionError('請填寫分類、至少一筆義務識別、理由與佐證。');
      return;
    }
    const seq = ++correctionFlowSeq.current;
    setCorrectionFlowStatus('preview_loading');
    setCorrectionError(null);
    try {
      const preview = await financeImportCorrectionClient.preview(request);
      if (seq !== correctionFlowSeq.current) return;
      if (preview.candidate.row_identity !== request.row_identity || preview.candidate.classification_type !== request.classification_type) throw new Error('Preview 與目前 Finance Import 更正輸入不一致。');
      setCorrectionPreview(preview);
      setCorrectionFlowStatus('preview_ready');
    } catch (error) {
      if (seq !== correctionFlowSeq.current) return;
      setCorrectionPreview(null);
      setCorrectionFlowStatus('typed_error');
      setCorrectionError(error instanceof Error ? error.message : 'Finance Import 更正 Preview 無法完成。');
    }
  };

  const observeCorrectionOutcome = async (accepted = correctionAccepted, activeSeq?: number) => {
    if (!accepted) return;
    const seq = activeSeq ?? ++correctionFlowSeq.current;
    if (seq !== correctionFlowSeq.current) return;
    setCorrectionFlowStatus('observing');
    setCorrectionError(null);
    try {
      const outcome = await financeImportCorrectionClient.queryOutcome(accepted.job_id);
      if (seq !== correctionFlowSeq.current) return;
      if (!['queued', 'running', 'succeeded', 'failed', 'cancelled'].includes(outcome.status)) {
        throw new Error('帳務更正結果狀態未知，已停止自動判定；請以同一 job/root 重新查詢。');
      }
      if (outcome.status === 'succeeded' && outcome.receipt === null) throw new Error('已完成的 Finance Import 更正 job 缺少 terminal receipt。');
      setCorrectionOutcome(outcome);
      if (outcome.status === 'succeeded' && outcome.receipt) {
        const originalFingerprint = selectedAnomaly?.fingerprint;
        if (!originalFingerprint) throw new Error('找不到原異常 fingerprint，已停止完成判定；請以同一 job/root 重新查詢。');

        try {
          const terminalDetail = await anomalyDetailClient.queryAnomalyDetail({ fingerprint: originalFingerprint });
          if (seq !== correctionFlowSeq.current) return;
          if (terminalDetail.summary.fingerprint !== originalFingerprint) {
            throw new Error('異常詳情與原 fingerprint 不一致，已停止完成判定；請以同一 job/root 重新查詢。');
          }
          if (terminalDetail.summary.predicate_active) {
            setCorrectionFlowStatus('accepted');
            setCorrectionError('帳務更正已提交，來源異常仍待核對；根因條件仍成立，請以同一 job/root 重新查詢。');
            return;
          }

          await fetchAnomalies();
          if (seq !== correctionFlowSeq.current) return;
          const refreshedAnomalies = latestAnomalyRefresh.current;
          if (!refreshedAnomalies.succeeded) {
            throw new Error('帳務更正已提交，來源異常仍待核對；最新異常清單查詢失敗，請以同一 job/root 重新查詢。');
          }
          if (refreshedAnomalies.snapshot.some((anomaly) => anomaly.fingerprint === originalFingerprint)) {
            setCorrectionFlowStatus('accepted');
            setCorrectionError('帳務更正已提交，來源異常仍待核對；最新清單仍顯示原異常，請以同一 job/root 重新查詢。');
            return;
          }
          setCorrectionFlowStatus('completed');
          setCorrectionError(null);
        } catch (error) {
          if (seq !== correctionFlowSeq.current) return;
          setCorrectionFlowStatus('accepted');
          setCorrectionError(error instanceof Error
            ? error.message
            : '帳務更正已提交，來源異常仍待核對；根因查詢失敗，請以同一 job/root 重新查詢。');
        }
      } else {
        setCorrectionFlowStatus('accepted');
      }
    } catch (error) {
      if (seq !== correctionFlowSeq.current) return;
      setCorrectionFlowStatus('typed_error');
      setCorrectionError(error instanceof Error ? error.message : 'Finance Import 更正 receipt 暫時無法取得。');
    }
  };

  const applyCorrection = async () => {
    const request = correctionRequest();
    if (!request || !correctionPreview || correctionFlowStatus !== 'preview_ready') return;
    const seq = ++correctionFlowSeq.current;
    setCorrectionFlowStatus('apply_pending');
    setCorrectionError(null);
    try {
      const accepted = await financeImportCorrectionClient.apply(correctionPreview, request, { idempotencyKey: correctionApplyKey.current, correlationId: correctionCorrelationId.current });
      if (seq !== correctionFlowSeq.current) return;
      setCorrectionAccepted(accepted);
      setCorrectionFlowStatus('accepted');
      await observeCorrectionOutcome(accepted, seq);
    } catch (error) {
      if (seq !== correctionFlowSeq.current) return;
      setCorrectionFlowStatus('typed_error');
      setCorrectionError(error instanceof Error ? error.message : 'Finance Import 更正 Apply 無法完成。');
    }
  };

  useEffect(() => {
    fetchAnomalies();
    fetchImportWarnings();
    return () => {
      anomalyRequestSeq.current += 1;
      importWarningRequestSeq.current += 1;
      drawerRequestSeq.current += 1;
      correctionFlowSeq.current += 1;
      drawerAbortController.current?.abort();
    };
  }, [fetchAnomalies, fetchImportWarnings]);

  const kpis = calculateAnomalyKPIs(anomalies);
  const filteredAnomalies = filterAnomalies(anomalies, selectedCategory, selectedStatusFilter);
  const categoryCounts = Object.fromEntries(
    CATEGORY_TAB_KEYS.map((category) => [
      category,
      filterAnomalies(anomalies, category, selectedStatusFilter).length,
    ])
  ) as Record<CategoryTabKey, number>;
  const correctionAction = financeCorrectionAction(anomalyRecovery);
  const financeOwnerTarget = financeOwnerRecoveryTarget(anomalyRecovery) ?? payoutDetailTarget;
  const correctionLocked = correctionFlowLocked;
  const isHistoricalOrderAlert = selectedAnomaly?.code === 'HISTORICAL-ORDER-001';
  const historicalBaselineCaseNo = selectedAnomaly?.code === 'HISTORICAL-BASELINE-ROOTS-001'
    ? anomalyDetail?.evidence.find((item) => item.key === 'case_no' && item.kind === 'identity')?.value ?? null
    : null;

  return (
    <div data-surface-id="anomalies.page">
      <div className="page-header-banner" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 className="page-title">⚠️ 異常與退款處理中心</h1>
          <p className="page-subtitle">集中查看會阻擋流程或需要補正的案件、排班、匯入與帳務問題。</p>
        </div>
      </div>

      {/* 4 Metric Summary Cards */}
      <div className="anomalies-kpi-grid" data-surface-id="anomalies.kpis">
        <div className="anomaly-kpi-card" style={{ borderLeft: '6px solid #dc2626' }}>
          <div className="anomaly-kpi-label">🔴 阻擋型嚴重異常</div>
          <div className="anomaly-kpi-value" style={{ color: '#dc2626' }}>{kpis.criticalCount} 筆</div>
          <div className="anomaly-kpi-sub">阻擋跨階段推進與正式簽約</div>
        </div>

        <div className="anomaly-kpi-card" style={{ borderLeft: '6px solid #f59e0b' }}>
          <div className="anomaly-kpi-label">🟡 待補正警示</div>
          <div className="anomaly-kpi-value" style={{ color: '#d97706' }}>{kpis.warningCount} 筆</div>
          <div className="anomaly-kpi-sub">意願逾期、帳號缺失等提示</div>
        </div>

        <div className="anomaly-kpi-card">
          <div className="anomaly-kpi-label">⏳ 待處理</div>
          <div className="anomaly-kpi-value" style={{ color: '#1e1b19' }}>{kpis.openCount} 筆</div>
          <div className="anomaly-kpi-sub">等待行政或會計人員認領</div>
        </div>

        <div className="anomaly-kpi-card">
          <div className="anomaly-kpi-label">🔵 處理中</div>
          <div className="anomaly-kpi-value" style={{ color: '#3b82f6' }}>{kpis.claimedCount} 筆</div>
          <div className="anomaly-kpi-sub">已指派人員進行排查修復</div>
        </div>
      </div>

      {/* 8 Categories Filter Bar */}
      <div className="anomalies-category-bar" data-surface-id="anomalies.category-filters">
        {CATEGORY_TAB_KEYS.map((cat) => (
          <button
            key={cat}
            disabled={warningFlowLocked}
            aria-describedby={warningFlowLocked ? 'anomalies-drawer-lock-reason' : undefined}
            className={`anomaly-cat-btn ${selectedCategory === cat ? 'active' : ''}`}
            onClick={() => setSelectedCategory(cat)}
          >
            {cat} ({categoryCounts[cat]})
          </button>
        ))}
      </div>

      {/* Status Secondary Filter Pills */}
      <div data-surface-id="anomalies.status-filters" style={{ display: 'flex', gap: '8px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <button
          disabled={warningFlowLocked}
          aria-describedby={warningFlowLocked ? 'anomalies-drawer-lock-reason' : undefined}
          style={{
            padding: '4px 12px',
            borderRadius: '9999px',
            border: '1px solid #dec0b6',
            backgroundColor: selectedStatusFilter === 'all' ? '#ff7f50' : '#fff',
            color: selectedStatusFilter === 'all' ? '#fff' : '#57423b',
            fontSize: '0.8rem',
            fontWeight: 700,
            cursor: 'pointer',
          }}
          onClick={() => setSelectedStatusFilter('all')}
        >
          全部狀態 ({anomalies.length})
        </button>
        <button
          disabled={warningFlowLocked}
          aria-describedby={warningFlowLocked ? 'anomalies-drawer-lock-reason' : undefined}
          style={{
            padding: '4px 12px',
            borderRadius: '9999px',
            border: '1px solid #dec0b6',
            backgroundColor: selectedStatusFilter === 'open' ? '#ff7f50' : '#fff',
            color: selectedStatusFilter === 'open' ? '#fff' : '#57423b',
            fontSize: '0.8rem',
            fontWeight: 700,
            cursor: 'pointer',
          }}
          onClick={() => setSelectedStatusFilter('open')}
        >
          🟡 待處理 ({kpis.openCount})
        </button>
        <button
          disabled={warningFlowLocked}
          aria-describedby={warningFlowLocked ? 'anomalies-drawer-lock-reason' : undefined}
          style={{
            padding: '4px 12px',
            borderRadius: '9999px',
            border: '1px solid #dec0b6',
            backgroundColor: selectedStatusFilter === 'claimed' ? '#ff7f50' : '#fff',
            color: selectedStatusFilter === 'claimed' ? '#fff' : '#57423b',
            fontSize: '0.8rem',
            fontWeight: 700,
            cursor: 'pointer',
          }}
          onClick={() => setSelectedStatusFilter('claimed')}
        >
          🔵 已認領 ({kpis.claimedCount})
        </button>
        <button
          disabled={warningFlowLocked}
          aria-describedby={warningFlowLocked ? 'anomalies-drawer-lock-reason' : undefined}
          style={{
            padding: '4px 12px',
            borderRadius: '9999px',
            border: '1px solid #dec0b6',
            backgroundColor: selectedStatusFilter === 'resolved' ? '#ff7f50' : '#fff',
            color: selectedStatusFilter === 'resolved' ? '#fff' : '#57423b',
            fontSize: '0.8rem',
            fontWeight: 700,
            cursor: 'pointer',
          }}
          onClick={() => setSelectedStatusFilter('resolved')}
        >
          ✅ 已排除
        </button>
      </div>

      <section data-surface-id="anomalies.list">
      {/* Anomalies List (Lane 1) */}
      {anomaliesLoading && (
        <div className="anomalies-loading">正在載入即時異常數據...</div>
      )}

      {anomaliesError && (
        <div className="anomalies-error">
          <span>載入異常資料失敗：{anomaliesError}</span>
          <button className="anomalies-retry-btn" onClick={() => { void fetchAnomalies(); }}>重試</button>
        </div>
      )}

      {!anomaliesLoading && !anomaliesError && filteredAnomalies.length === 0 && (
        <div className="anomalies-empty">目前無符合條件之異常項目。</div>
      )}

      {!anomaliesLoading && !anomaliesError && filteredAnomalies.length > 0 && (
        <div className="anomalies-list">
          {filteredAnomalies.map((anm) => (
            <div
              key={anm.id}
              className={`anomaly-card ${anm.severityClass}`}
            >
              <div className="anomaly-card-top">
                <div className="anomaly-code-tag">
                  <span style={{ fontSize: '1.05rem', fontWeight: 700 }}>{anm.title}</span>
                </div>

                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <span className={`anomaly-severity-badge ${anm.severityClass}`}>
                    {anm.severity}
                  </span>
                  <span style={{
                    padding: '3px 10px',
                    borderRadius: '9999px',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    backgroundColor: anm.rawWorkflowStatus === 'resolved' ? '#dcfce7' : anm.rawWorkflowStatus === 'claimed' ? '#dbeafe' : '#fef3c7',
                    color: anm.rawWorkflowStatus === 'resolved' ? '#166534' : anm.rawWorkflowStatus === 'claimed' ? '#1e40af' : '#92400e'
                  }}>
                    {anm.status}
                  </span>
                </div>
              </div>

              {/* Middle: business impact and next-step summary */}
              <div style={{ fontSize: '0.88rem', color: '#57423b', lineHeight: '1.5' }}>
                <div><strong>影響對象：</strong><span style={{ color: '#c2410c', fontWeight: 600 }}>{anm.relatedEntity}</span></div>
                <div style={{ marginTop: '2px' }}><strong>處理說明：</strong>{anm.description}</div>
              </div>

              {/* Bottom Actions Row */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '10px', borderTop: '1px dashed #f2e2dc' }}>
                <div style={{ fontSize: '0.8rem', color: '#888' }}>
                  💡 {anm.suggestedAction}
                </div>

                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    data-control-id="anomalies.card.drawer_open"
                    style={{ padding: '6px 14px', backgroundColor: '#ff7f50', color: '#fff', border: 'none', borderRadius: '6px', fontWeight: 700, fontSize: '0.82rem', cursor: 'pointer' }}
                    onClick={() => openAnomalyDrawer(anm)}
                  >
                    查看處理方式 ➔
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      {!anomaliesLoading && anomaliesHasMore && (
        <div className="anomalies-pagination">
          <button
            type="button"
            data-control-id="anomalies.list.load-more"
            disabled={anomaliesLoadingMore}
            onClick={() => void loadMoreAnomalies()}
          >
            {anomaliesLoadingMore ? '正在載入更多異常…' : '載入更多異常'}
          </button>
        </div>
      )}
      </section>

      {/* Import Warning Tasks Section (Lane 2) */}
      {(selectedCategory === '全部' || selectedCategory === '匯入資料') && (
      <section data-surface-id="anomalies.import-warnings">
      <div className="anomalies-section-title">
        <span>📥 匯入資料待辦</span>
      </div>

      {importWarningsLoading && (
        <div className="anomalies-loading">正在載入匯入警示追蹤數據...</div>
      )}

      {importWarningsError && (
        <div className="anomalies-error">
          <span>載入匯入警示資料失敗：{importWarningsError}</span>
          <button className="anomalies-retry-btn" onClick={fetchImportWarnings}>重試</button>
        </div>
      )}

      {!importWarningsLoading && !importWarningsError && importWarnings.length === 0 && (
        <div className="anomalies-empty">目前無待追蹤之匯入警示任務。</div>
      )}

      {!importWarningsLoading && !importWarningsError && importWarnings.length > 0 && (
        <div className="import-warnings-list">
          {importWarnings.map((task) => (
            <div key={task.occurrenceIdentity} className="import-warning-card">
              <div className="import-warning-header">
                <div className="import-warning-badges">
                  <span className="import-warning-lane-badge">{task.laneLabel}</span>
                </div>
                <span className={`import-warning-status-badge ${task.status}`}>
                  {task.statusLabel}
                </span>
              </div>

              <div className="import-warning-body">
                <div><strong>待修正資料：</strong><span>{task.maskedSubject}</span></div>
              </div>

              <div style={{ fontSize: '0.88rem', color: '#1e1b19', fontWeight: 600 }}>
                {task.displayMessage}
              </div>

              <div className="import-warning-footer">
                <div />
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <button
                    data-control-id="anomalies.warning.drawer_open"
                    type="button"
                    onClick={() => openWarningDrawer(task)}
                    style={{ padding: '4px 12px', backgroundColor: '#ff7f50', color: '#fff', border: 'none', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 700, cursor: 'pointer' }}
                  >
                    查看警示詳情
                  </button>
                  {task.navigationAction && (
                    <a
                      data-surface-id="anomalies.navigation.data-import"
                      href="#data-import"
                      style={{
                        display: 'inline-block',
                        padding: '4px 12px',
                        backgroundColor: '#6366f1',
                        color: '#fff',
                        borderRadius: '6px',
                        fontSize: '0.8rem',
                        fontWeight: 700,
                        textDecoration: 'none',
                      }}
                    >
                      前往匯入中心 ➔
                    </a>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      </section>
      )}

      {/* Diagnostic & Recovery Drawer */}
      <Drawer
        isOpen={selectedAnomaly !== null || selectedWarning !== null}
        onClose={closeDrawer}
        closeDisabled={drawerFlowLocked}
        size="wide"
        title={selectedAnomaly ? `⚠️ ${selectedAnomaly.title}` : '📥 匯入警示處理'}
        footer={
          <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', alignItems: 'center' }}>
            <span id={drawerLockReason ? 'anomalies-drawer-lock-reason' : undefined} style={{ fontSize: '0.85rem', color: '#888' }}>
              {drawerLockReason ?? '💡 完成處理後系統會重新核對原因；根因仍存在時會再次列入待辦。'}
            </span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                disabled={drawerFlowLocked}
                aria-describedby={drawerFlowLocked ? 'anomalies-drawer-lock-reason' : undefined}
                style={{ padding: '8px 16px', border: '1px solid #dec0b6', borderRadius: '8px', background: '#fff', cursor: 'pointer' }}
                onClick={closeDrawer}
              >
                關閉
              </button>
              {selectedAnomaly ? (
                <span
                  data-surface-id="anomalies.drawer.resolve-guidance"
                  style={{ maxWidth: '380px', color: '#57423b', fontSize: '0.84rem', fontWeight: 700 }}
                >
                  請先依上方處理方式修正來源資料；系統會自動重新核對異常。
                </span>
              ) : (
                <span
                  data-surface-id="anomalies.warning.transition-guidance"
                  style={{ maxWidth: '380px', color: '#57423b', fontSize: '0.84rem', fontWeight: 700 }}
                >
                  請依上方轉介流程處理來源資料；追蹤狀態不代表來源已修復。
                </span>
              )}
            </div>
          </div>
        }
      >
        {selectedAnomaly && (
          <div data-surface-id="anomalies.drawer" style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            {/* Anomaly Overview Box */}
            <div style={{ backgroundColor: selectedAnomaly.severityClass === 'critical' ? '#fff1f2' : '#fffbeb', padding: '18px', borderRadius: '12px', border: selectedAnomaly.severityClass === 'critical' ? '1px solid #fecdd3' : '1px solid #fed7aa' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontWeight: 700, color: selectedAnomaly.severityClass === 'critical' ? '#991b1b' : '#92400e', fontSize: '1.05rem' }}>
                  {selectedAnomaly.title}
                </span>
              </div>
              <p style={{ fontSize: '0.88rem', color: '#57423b', lineHeight: '1.5' }}>
                <strong>目前是否仍需處理：</strong>{selectedAnomaly.metadata.predicateActive ? '是' : '否'}<br />
                <strong>影響對象：</strong>{selectedAnomaly.relatedEntity}<br />
                <strong>處理說明：</strong>{selectedAnomaly.description}
              </p>
            </div>

            <div data-surface-id="anomalies.drawer.detail" className="anomalies-detail-card">
              <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e1b19', marginBottom: '8px' }}>📄 問題詳情</h4>
              {anomalyDetailLoading && <div className="anomalies-detail-loading">正在載入問題詳情與可處理方式...</div>}
              {!anomalyDetailLoading && anomalyDetailError && <div className="anomalies-detail-error">{anomalyDetailError}</div>}
              {!anomalyDetailLoading && !anomalyDetailError && !anomalyDetail && <div className="anomalies-detail-empty">目前沒有可顯示的異常詳情。</div>}
              {!anomalyDetailLoading && anomalyDetail && (
                <>
                  <div data-surface-id="anomalies.drawer.evidence" className="anomalies-evidence-card">
                    <strong>判斷依據</strong>
                    {visibleEvidenceItems(anomalyDetail.evidence).map((item) => (
                      <div className="anomaly-evidence-row" key={`${item.key}-${item.kind}`}>
                        <span>{item.label}</span><span>{item.value}</span>
                      </div>
                    ))}
                    {visibleEvidenceItems(anomalyDetail.evidence).length === 0 && (
                      <div className="anomalies-detail-empty">目前沒有需要顯示的業務判斷資料。</div>
                    )}
                  </div>
                  <div data-surface-id="anomalies.drawer.timeline" className="anomalies-timeline-card">
                    <strong>處理紀錄</strong>
                    {anomalyDetail.detailTimeline.length === 0 && <span>尚無工作流事件。</span>}
                    {anomalyDetail.detailTimeline.map((event) => (
                      <div className="anomaly-recovery-metadata-row" key={`${event.correlationId}-${event.resultingVersion}`}>
                        <span>{event.action} · {event.createdAt}</span>
                        <span>{event.actor}；{event.reason}</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>

            <div data-surface-id="anomalies.drawer.current-details" className="anomalies-root-evidence-card root-evidence">
              <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e1b19', marginBottom: '8px' }}>
                🔍 問題判斷依據
              </h4>
              {!anomalyDetail && <div className="anomalies-detail-empty">正在等待正式資料。</div>}
              {anomalyDetail && visibleEvidenceItems(anomalyDetail.currentDetails).map((item) => (
                <div className="anomaly-evidence-row" key={item.key}>
                  <span>{item.label}</span><span>{item.value}</span>
                </div>
              ))}
              {anomalyDetail && visibleEvidenceItems(anomalyDetail.currentDetails).length === 0 && (
                <div className="anomalies-detail-empty">技術識別已保留在稽核紀錄，不顯示於日常處理畫面。</div>
              )}
            </div>

            <div data-surface-id="anomalies.drawer.recovery" className="anomalies-recovery-card recovery">
              <h4>🎯 可採取的處理方式</h4>
              {selectedAnomaly.staffCalendarNavigation && (
                <a href="#scheduling">
                  前往排班調度 ➔（目標日期: {selectedAnomaly.staffCalendarNavigation.target_date}，月嫂 ID: #{selectedAnomaly.staffCalendarNavigation.staff_id}）
                </a>
              )}
              {anomalyRecoveryError && !clientSettlement && !financeOwnerTarget && <div className="anomalies-detail-error">{anomalyRecoveryError}</div>}
              {anomalyDetail && <>
                {clientSettlement && (
                  <div className="anomaly-recovery-metadata-row">
                    <span>正式處理方式</span>
                    <span>依下方 Client Finance 根事實執行 Query／Preview／Apply</span>
                  </div>
                )}
                {!isHistoricalOrderAlert && anomalyDetail.recoveryAvailable && <div className="anomaly-recovery-metadata-row"><span>目前是否阻擋作業</span><span>{anomalyDetail.blocking ? '是' : '否'}</span></div>}
                {!isHistoricalOrderAlert && anomalyDetail.recoveryAvailable && anomalyDetail.actions.length === 0 && <div className="anomalies-detail-empty">目前沒有可用的處理方式。</div>}
                {isHistoricalOrderAlert && (
                  <div className="anomaly-recovery-metadata-row"><span>正式處理方式</span><span>上傳只含此 review 對應列的更正工作簿</span></div>
                )}
                {!isHistoricalOrderAlert && anomalyDetail.actions.map((action) => (
                  <div className="anomaly-recovery-metadata-row" key={action.key}>
                    <span>{action.label}</span>
                    <span>{action.requiredInputs.length > 0 ? `需填寫 ${action.requiredInputs.length} 項資料` : '可直接進行檢查'}</span>
                  </div>
                ))}
              </>}
            </div>

            {isHistoricalOrderAlert && (
              <HistoricalOrderReviewRemediationWorkbench
                reviewIdentity={selectedAnomaly.sourceIdentity}
                onResolved={() => { void fetchAnomalies(); }}
              />
            )}

            {historicalBaselineCaseNo && (
              <HistoricalOperationalBaselineReadback caseNo={historicalBaselineCaseNo} />
            )}

            {!isHistoricalOrderAlert && financeOwnerTarget?.kind === 'government' && (
              <GovernmentOverpaymentRecoveryWorkbench
                overpaymentIdentity={financeOwnerTarget.overpaymentIdentity}
                anomalyFingerprint={selectedAnomaly?.fingerprint ?? ''}
                onResolved={(fingerprint) => fetchAnomalies(true, fingerprint)}
              />
            )}
            {!isHistoricalOrderAlert && financeOwnerTarget?.kind === 'client' && (
              <ClientOverRefundRecoveryWorkbench
                caseNo={financeOwnerTarget.caseNo}
                recoveryIdentity={financeOwnerTarget.recoveryIdentity}
                initialFinanceImportRowId={financeOwnerTarget.financeImportRowId}
                onCommitted={(query) => {
                  if (query.remaining_amount_ntd === 0 && (query.status === 'recovered' || query.status === 'adjusted')) {
                    void fetchAnomalies();
                  }
                }}
              />
            )}
            {!isHistoricalOrderAlert && financeOwnerTarget?.kind === 'staff' && (
              <StaffOverpaymentRecoveryActions
                staffId={financeOwnerTarget.staffId}
                recoveryIdentity={financeOwnerTarget.recoveryIdentity}
                initialFinanceImportRowId={financeOwnerTarget.financeImportRowId}
                onCommitted={() => { void fetchAnomalies(); }}
              />
            )}
            {!isHistoricalOrderAlert && financeOwnerTarget?.kind === 'staff_payout' && (
              <StaffPayoutRemediationWorkbench
                target={{
                  staffId: financeOwnerTarget.staffId,
                  obligationIdentity: financeOwnerTarget.obligationIdentity,
                }}
                onResolved={() => { void fetchAnomalies(); }}
              />
            )}
            {!isHistoricalOrderAlert && clientSettlement && (
              <ClientSettlementRemediationWorkbench
                target={clientSettlement}
                onResolved={() => { void fetchAnomalies(); }}
              />
            )}
            {!isHistoricalOrderAlert && !financeOwnerTarget && !clientSettlement && (correctionAction ? (
              <section data-surface-id="anomalies.finance-correction" style={{ border: '1px solid #b7d8d1', padding: '16px', borderRadius: '12px', backgroundColor: '#f5fffc' }}>
                <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#115e59', marginBottom: '6px' }}>帳務資料更正</h4>
                <p style={{ fontSize: '0.84rem', color: '#365b55', marginTop: 0 }}>此表單只執行「{correctionAction.label}」的影響檢查與確認；問題排除後，系統會再核對來源資料。</p>
                <div className="anomaly-recovery-metadata-row"><span>處理資料</span><span>銀行流水資料</span></div>
                <label className="import-warning-transition-field"><span>分類類型</span><select data-control-id="anomalies.finance-correction.classification" value={correctionClassificationType} disabled={correctionLocked || correctionAction.action_key !== 'classify_and_post_bank_row'} aria-describedby={correctionAction.action_key !== 'classify_and_post_bank_row' ? 'anomalies-correction-classification-reason' : correctionLocked ? 'anomalies-drawer-lock-reason' : undefined} onChange={(event) => { setCorrectionClassificationType(event.target.value as FinanceImportCorrectionSelection['classification_type']); invalidateCorrectionPreview(); }}>
                  <option value="client_receipt">客戶收款</option><option value="client_refund">客戶退款</option><option value="client_refund_return">客戶退款退匯</option><option value="client_subsidy_return">客戶補助退回</option><option value="government_subsidy">政府補助</option><option value="staff_payout">月嫂付款</option>
                </select></label>
                {correctionAction.action_key !== 'classify_and_post_bank_row' && <p id="anomalies-correction-classification-reason" className="anomalies-detail-empty">此異常的分類由正式處理方式固定，不能在此改成其他分類。</p>}
                <label className="import-warning-transition-field"><span>對應收付款紀錄編號（每行一筆）</span><textarea data-control-id="anomalies.finance-correction.obligations" value={correctionObligations} disabled={correctionLocked} rows={3} onChange={(event) => { setCorrectionObligations(event.target.value); invalidateCorrectionPreview(); }} placeholder="請填寫收付款紀錄編號" /></label>
                <label className="import-warning-transition-field"><span>原退款紀錄編號（需要時填寫）</span><input data-control-id="anomalies.finance-correction.refund-ledger" value={correctionRefundLedgerEntry} disabled={correctionLocked} onChange={(event) => { setCorrectionRefundLedgerEntry(event.target.value); invalidateCorrectionPreview(); }} placeholder="請填寫原退款紀錄編號" /></label>
                <label className="import-warning-transition-field"><span>更正理由</span><textarea data-control-id="anomalies.finance-correction.reason" value={correctionReason} disabled={correctionLocked} rows={2} maxLength={500} onChange={(event) => { setCorrectionReason(event.target.value); invalidateCorrectionPreview(); }} /></label>
                <label className="import-warning-transition-field"><span>佐證（每行一筆）</span><textarea data-control-id="anomalies.finance-correction.evidence" value={correctionEvidence} disabled={correctionLocked} rows={3} onChange={(event) => { setCorrectionEvidence(event.target.value); invalidateCorrectionPreview(); }} placeholder="例：銀行交易明細或內部佐證編號" /></label>
                <div className="import-warning-transition-actions">
                  <button type="button" data-control-id="anomalies.finance-correction.preview" disabled={correctionLocked || correctionFlowStatus === 'preview_loading'} onClick={() => void previewCorrection()}>{correctionFlowStatus === 'preview_loading' ? '檢查中…' : '檢查更正影響'}</button>
                  <button type="button" data-control-id="anomalies.finance-correction.apply" disabled={correctionFlowStatus !== 'preview_ready'} aria-describedby={correctionApplyDisabledReason ? 'anomalies-correction-apply-reason' : undefined} onClick={() => void applyCorrection()}>確認並提交更正</button>
                  {correctionAccepted && correctionFlowStatus !== 'completed' && <button type="button" data-control-id="anomalies.finance-correction.observe" disabled={correctionLocked} onClick={() => void observeCorrectionOutcome()}>重新查詢更正結果</button>}
                </div>
                {correctionApplyDisabledReason && <p id="anomalies-correction-apply-reason" className="anomalies-detail-empty">{correctionApplyDisabledReason}</p>}
                {correctionPreview && <div className="import-warning-transition-preview"><strong>更正影響預覽（尚未寫入）</strong><span>{correctionClassificationLabel(correctionPreview.candidate.classification_type)} · NT$ {correctionPreview.candidate.bank_amount_ntd.toLocaleString('en-US')}</span></div>}
                {correctionAccepted && <div className="import-warning-transition-receipt"><strong>更正已受理</strong><span>{correctionAccepted.replayed ? '同一筆更正已受理，正在查回原結果。' : '系統正在處理，完成前不會顯示為已更正。'}</span></div>}
                {correctionFlowStatus === 'completed' && correctionOutcome?.receipt && <div className="import-warning-transition-observed"><strong>帳務更正完成</strong><span>正式結果已確認，可重新查詢帳務資料核對。</span></div>}
                {correctionAccepted && correctionOutcome && correctionOutcome.status !== 'succeeded' && <div className="import-warning-transition-warning">帳務更正尚未完成；請稍後重新查詢結果。</div>}
                {correctionError && <div className="anomalies-detail-error">{correctionError}</div>}
              </section>
            ) : (
              <div style={{ border: '1px solid #dec0b6', padding: '16px', borderRadius: '12px', backgroundColor: '#fff' }}>
                <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e1b19', marginBottom: '10px' }}>來源資料修正</h4>
                <div className="anomalies-detail-empty">此異常目前沒有可直接使用的帳務更正表單，請交由對應業務負責人處理。</div>
              </div>
            ))}
          </div>
        )}
        {selectedWarning && (
          <div data-surface-id="anomalies.drawer" style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            <div data-surface-id="anomalies.drawer.referral" style={{ border: '1px solid #dec0b6', padding: '18px', borderRadius: '12px', backgroundColor: '#fff' }}>
              <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e1b19', marginBottom: '10px' }}>🔗 負責處理流程</h4>
              {warningReferralLoading && <div className="anomalies-loading">正在載入匯入警示導向...</div>}
              {!warningReferralLoading && (warningReferralError || !warningReferral) && (
                <div style={{ color: '#888' }}>{warningReferralError ?? '轉介資訊暫時無法取得，請關閉後重試。'}</div>
              )}
              {!warningReferralLoading && warningReferral && (
                <div style={{ color: '#57423b', lineHeight: '1.7' }}>
                  <div><strong>負責單位：</strong>{mapImportWarningLaneLabel(warningReferral.owningLane)}</div>
                  <div><strong>待修正資料：</strong>{warningReferral.maskedSubject}</div>
                  <div><strong>問題說明：</strong>{warningReferral.displayMessage}</div>
                  <div><strong>下一步：</strong>{warningReferral.actionKind === 'owner_preview_apply' ? '由負責流程檢查後修正' : '等待對應資料完成'}</div>
                  {warningReferral.navigationAction === 'hcm_import_center' && (
                    <a href="#data-import" data-surface-id="anomalies.navigation.data-import">前往匯入中心 ➔</a>
                  )}
                </div>
              )}
            </div>
            <div data-surface-id="anomalies.drawer.recovery" className="import-warning-transition-panel">
              <div className="import-warning-transition-heading">
                <div>
                  <h4>更新處理狀態</h4>
                  <p>此處只記錄處理進度；來源資料仍須由負責流程實際修正。</p>
                </div>
                {warningFlowStatus === 'idle' && <button
                  type="button"
                  data-control-id="anomalies.import-warning.transition.open"
                  onClick={() => setWarningFlowStatus('editing')}
                >
                  開啟追蹤狀態變更
                </button>}
              </div>

              {warningFlowStatus !== 'idle' && <>
                <label className="import-warning-transition-field">
                  <span>目標追蹤狀態</span>
                  <select
                    data-control-id="anomalies.import-warning.transition.action"
                    value={warningAction}
                    disabled={warningFlowLocked}
                    onChange={(event) => {
                      setWarningAction(event.target.value as WarningTransitionRequest['target_status']);
                      invalidateWarningPreview();
                    }}
                  >
                    <option value="awaiting_external_confirmation">等待外部確認</option>
                    <option value="response_recorded">已記錄回應</option>
                    <option value="reimport_requested">已請求重新匯入</option>
                    <option value="closed">關閉追蹤</option>
                  </select>
                </label>
                <label className="import-warning-transition-field">
                  <span>處理說明</span>
                  <input
                    data-control-id="anomalies.import-warning.transition.reason"
                    value={warningReason}
                    maxLength={100}
                    disabled={warningFlowLocked}
                    onChange={(event) => {
                      setWarningReason(event.target.value);
                      invalidateWarningPreview();
                    }}
                    placeholder="例：已聯繫申請人補件"
                  />
                </label>
                <div className="import-warning-transition-actions">
                  <button
                    type="button"
                    data-control-id="anomalies.import-warning.transition.preview"
                    disabled={warningFlowLocked || warningFlowStatus === 'preview_loading' || !warningReason.trim()}
                    aria-describedby={warningPreviewDisabledReason ? 'anomalies-warning-preview-reason' : undefined}
                    onClick={() => void previewWarningTransition()}
                  >
                    {warningFlowStatus === 'preview_loading' ? '檢查中…' : '檢查狀態變更影響'}
                  </button>
                  <button
                    type="button"
                    data-control-id="anomalies.import-warning.transition.apply"
                    disabled={warningFlowStatus !== 'preview_ready'}
                    aria-describedby={warningApplyDisabledReason ? 'anomalies-warning-apply-reason' : undefined}
                    onClick={() => void applyWarningTransition(false)}
                  >
                    套用追蹤狀態變更
                  </button>
                  {warningFlowStatus === 'outcome_unknown' && (
                    <button type="button" data-control-id="anomalies.import-warning.transition.retry" onClick={() => void applyWarningTransition(true)}>
                      重試原本的狀態變更
                    </button>
                  )}
                  {warningFlowStatus === 'observation_failed' && warningReceipt && (
                    <button type="button" data-control-id="anomalies.import-warning.transition.observe" onClick={() => void observeWarningReceipt(warningReceipt, warningFlowSeq.current)}>
                      重新查詢變更結果
                    </button>
                  )}
                </div>
                {warningPreviewDisabledReason && <p id="anomalies-warning-preview-reason" className="anomalies-detail-empty">{warningPreviewDisabledReason}</p>}
                {warningApplyDisabledReason && <p id="anomalies-warning-apply-reason" className="anomalies-detail-empty">{warningApplyDisabledReason}</p>}
              </>}

              {warningPreview && (
                <div className="import-warning-transition-preview">
                  <strong>狀態變更影響（尚未套用）</strong>
                  <span>預計變更為：{mapImportWarningStatusLabel(warningPreview.resultingStatus)}</span>
                </div>
              )}
              {warningReceipt && (
                <div className="import-warning-transition-receipt">
                  <strong>追蹤狀態變更已受理</strong>
                  <span>{mapImportWarningStatusLabel(warningReceipt.beforeStatus)} → {mapImportWarningStatusLabel(warningReceipt.afterStatus)}</span>
                </div>
              )}
              {warningFlowStatus === 'observed' && (
                <div className="import-warning-transition-observed">已確認追蹤狀態變更完成；這不代表來源資料已修復。</div>
              )}
              {warningFlowStatus === 'outcome_unknown' && (
                <div className="import-warning-transition-warning">變更結果尚未確認；系統已保留本次提交內容，請使用下方按鈕重試。</div>
              )}
              {warningFlowStatus === 'observation_failed' && (
                <div className="import-warning-transition-warning">狀態變更已受理，但結果查詢失敗；請重新查詢，不需重複提交。</div>
              )}
              {warningFlowStatus === 'stale' && (
                <div className="import-warning-transition-warning">資料已更新；系統已重新查詢清單，請關閉後重開並再次檢查。</div>
              )}
              {warningFlowError && <div className="anomalies-detail-error">{warningFlowError}</div>}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};

export const AnomaliesPage = CurrentAnomaliesPage;
export default AnomaliesPage;
