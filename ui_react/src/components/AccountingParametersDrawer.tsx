/**
 * File: AccountingParametersDrawer.tsx
 * Description: 帳務參數調整抽屜，支援更正正式胎數、補助上限、客戶與月嫂時薪。
 */

import React, { useEffect, useEffectEvent, useRef, useState } from 'react';
import {
  accountingPricingClient,
  type CasePricing,
  type PricingPreview,
  type PricingTerms,
  PricingTermsSchema,
  pricingIdentityLabel,
  pricingRequestError,
  pricingTermsError,
} from '../api/client_finance/accounting_pricing_client';
import { clientRegistryClient } from '../api/client_registry/client_registry_client';
import type { ClientRegistryDetail, RegistryMutationPreview } from '../api/client_registry/client_registry_schemas';
import { ApiHttpError } from '../api/shared/typed_errors';
import { HistoricalServiceAccountingWorkbench } from './HistoricalServiceAccountingWorkbench';
import { HistoricalAccountingPending, HistoricalCorrectionAccounting } from './HistoricalCorrectionAccounting';
import { useUnsavedChanges, useUnsavedNavigation } from './UnsavedChanges';
import './AccountingParameters.css';
import './Drawer.css';

interface AccountingParametersDrawerProps {
  caseNo: string;
  isOpen: boolean;
  onClose: () => void;
  onCommitted: () => Promise<void> | void;
  initialPricing?: CasePricing | null;
  canEditHistoricalDays?: boolean;
}

type BirthCount = '單胞胎' | '雙胞胎';

type PricingSave = {
  terms: PricingTerms;
  revision: number;
  key: string;
};

type BirthCountSave = {
  value: BirthCount;
  preview: RegistryMutationPreview;
  key: string;
};

type HistoricalSave =
  | { kind: 'historical-birth'; reason: string; birth: BirthCountSave }
  | { kind: 'historical-pricing'; reason: string; pricing: PricingSave; preview: PricingPreview };

type SaveCommand = HistoricalSave
  | { kind: 'standard'; reason: string; pricing?: PricingSave; birth?: BirthCountSave };

type PendingSave =
  | { stage: 'confirm' | 'retry'; command: SaveCommand }
  | { stage: 'readback'; command: HistoricalSave; accountingPending: readonly string[] };

type RegistryBirthState = { value: BirthCount | null; version: number | null; locked: boolean; historical: boolean };

function registryBirthState(beclass: ClientRegistryDetail['beclass']): RegistryBirthState {
  const value = beclass.values?.multi_birth_count;
  const capability = beclass.field_capabilities.multi_birth_count;
  return {
    value: value === '單胞胎' || value === '雙胞胎' ? value : null,
    version: beclass.status === 'ready' && capability?.editable ? beclass.version : null,
    locked: capability?.reason === 'multi_birth_count_locked_after_service_start',
    historical: beclass.birth_count_correction_mode === 'historical_service_completed',
  };
}

export const AccountingParametersDrawer: React.FC<AccountingParametersDrawerProps> = ({
  caseNo,
  isOpen,
  onClose,
  onCommitted,
  initialPricing,
  canEditHistoricalDays = false,
}) => {
  const [current, setCurrent] = useState<CasePricing | null>(null);
  const [birthCount, setBirthCount] = useState<BirthCount | null>(null);
  const [birth, setBirth] = useState<RegistryBirthState | null>(null);
  const [draft, setDraft] = useState<PricingTerms | null>(null);
  const [reason, setReason] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [showHistoricalDays, setShowHistoricalDays] = useState(false);
  const [pendingSave, setPendingSave] = useState<PendingSave | null>(null);
  const [saveNotice, setSaveNotice] = useState('');
  const { requestLeave } = useUnsavedNavigation();
  const inFlight = useRef<boolean>(false);
  const birthVersion = birth?.version ?? null;
  const historicalBirth = birth?.historical === true;
  const birthChanged = birthCount !== null && birthCount !== birth?.value;
  const saveUncertain = pendingSave?.stage === 'retry' || pendingSave?.stage === 'readback';
  const fieldsDisabled = saving || pendingSave !== null;
  const pricingFieldsDisabled = fieldsDisabled || (historicalBirth && birthChanged);
  const savedBirthLabel = birth?.value ?? '待確認';
  const birthDraftChanges = isOpen && birthChanged ? [{ label: '胎數', before: savedBirthLabel, after: birthCount }] : [];
  const pricingDraftChanges = isOpen && current && draft ? [
    { label: '補助上限', before: String(current.terms.subsidy_hours), after: String(draft.subsidy_hours) },
    ...(['client', 'payroll'] as const).flatMap(owner => (['covered', 'excess'] as const).map(tier => ({
      label: `${owner === 'client' ? '客戶' : '月嫂'}${tier === 'covered' ? '補助內' : '超額'}時薪`,
      before: String(current.terms[owner][tier]), after: String(draft[owner][tier]),
    }))),
  ].filter(change => change.before !== change.after) : [];
  const drawerRef = useUnsavedChanges('更正本案計價參數', [...birthDraftChanges, ...pricingDraftChanges], {
    busy: isOpen && (saving || saveUncertain),
  });
  const resetPricingForOpen = useEffectEvent(() => {
    const fallback = initialPricing?.case_no === caseNo ? initialPricing : null;
    setCurrent(fallback);
    setDraft(fallback?.terms ?? null);
  });

  useEffect(() => {
    if (!isOpen || !caseNo) return;
    const controller = new AbortController();
    setLoading(true);
    setError('');
    setReason('');
    resetPricingForOpen();
    setBirth(null);
    setBirthCount(null);
    setSaveNotice('');
    setPendingSave(null);
    void Promise.allSettled([
      accountingPricingClient.queryCase(caseNo),
      clientRegistryClient.query(caseNo, controller.signal),
    ]).then(([pricing, registry]) => {
      if (controller.signal.aborted) return;
      if (pricing.status === 'fulfilled') {
        setCurrent(pricing.value);
        setDraft(structuredClone(pricing.value.terms));
      }
      if (registry.status === 'fulfilled') {
        const registered = registryBirthState(registry.value.beclass);
        setBirthCount(registered.value);
        setBirth(registered);
      }
      setLoading(false);
    });
    return () => controller.abort();
  }, [isOpen, caseNo]);

  if (!isOpen) return null;

  const close = () => {
    const proceed = () => {
      setShowHistoricalDays(false);
      onClose();
    };
    requestLeave(proceed);
  };

  const handleBirthCountChange = (value: BirthCount) => {
    if (birthVersion !== null) setBirthCount(value);
  };

  const identityLabel = draft ? pricingIdentityLabel(draft) : '';
  const confirmation = pendingSave?.stage === 'confirm' ? pendingSave.command : null;
  const confirmedBirth = confirmation && confirmation.kind !== 'historical-pricing' ? confirmation.birth : undefined;
  const confirmedPricing = confirmation?.kind === 'historical-pricing' ? confirmation.preview : undefined;

  const handleApply = async () => {
    if (inFlight.current || saving) return;
    inFlight.current = true;
    setSaving(true);
    setError('');
    setSaveNotice('');

    let command = pendingSave?.command;
    let accountingPending = pendingSave?.stage === 'readback' ? pendingSave.accountingPending : [];
    let stage: 'preview' | 'birth' | 'pricing' | 'readback' | 'refresh' = 'preview';
    let standardBirthCommitted = false;

    try {
      if (!command) {
        const reasonText = reason.trim();
        let pricing: PricingSave | undefined;
        if (current && draft && (!birthChanged || (!historicalBirth && pricingDraftChanges.length > 0))) {
          const validationError = pricingTermsError(draft);
          const parsed = PricingTermsSchema.safeParse(draft);
          if (validationError || !parsed.success) {
            setError(validationError || '請確認輸入的時薪數值為正整數。');
            return;
          }
          pricing = { terms: parsed.data, revision: current.revision, key: `case-pricing-param:${crypto.randomUUID()}` };
        }
        if (birthChanged && birthCount !== null) {
          if (birthVersion === null) {
            setError('目前無法更正胎數，請重新開啟抽屜確認。');
            return;
          }
          const preview = await clientRegistryClient.preview(caseNo, 'beclass', { multi_birth_count: birthCount }, birthVersion);
          const birthSave = { value: birthCount, preview, key: `case-birth-count:${crypto.randomUUID()}` };
          if (historicalBirth && !preview.historical_impact) {
            setError('案件的更正資格已更新，請重新開啟抽屜確認。');
            return;
          }
          command = preview.historical_impact
            ? { kind: 'historical-birth', birth: birthSave, reason: reasonText }
            : { kind: 'standard', birth: birthSave, pricing, reason: reasonText };
          setPendingSave({ stage: 'confirm', command });
          return;
        }
        if (!pricing) return;
        if (current?.historical) {
          const preview = await accountingPricingClient.previewCase(caseNo, pricing.terms, pricing.revision);
          setPendingSave({ stage: 'confirm', command: { kind: 'historical-pricing', reason: reasonText, pricing, preview } });
          return;
        }
        command = { kind: 'standard', pricing, reason: reasonText };
      }

      if (pendingSave?.stage !== 'readback') {
        if (command.kind !== 'historical-pricing' && command.birth) {
          stage = 'birth';
          const { birth: proposed } = command;
          const receipt = await clientRegistryClient.apply(caseNo, 'beclass', { multi_birth_count: proposed.value },
            proposed.preview.current_version, proposed.preview.preview_fingerprint, command.reason, proposed.key);
          accountingPending = receipt.accounting_pending ?? [];
          if (command.kind === 'standard') {
            if (receipt.readback.multi_birth_count !== proposed.value) {
              setPendingSave(null);
              setBirth(null);
              setError('目前正式胎數與本次更正不同，請重新開啟抽屜確認最新資料。');
              return;
            }
            setBirth(previous => previous && { ...previous, value: proposed.value, version: receipt.resulting_version });
            setSaveNotice(`胎數已儲存為${proposed.value}。`);
            command = { ...command, birth: undefined };
            standardBirthCommitted = true;
          }
        }
        if (command.kind !== 'historical-birth' && command.pricing) {
          stage = 'pricing';
          const { pricing, reason: savedReason } = command;
          if (command.kind === 'historical-pricing') {
            const receipt = await accountingPricingClient.applyCase(caseNo, pricing.terms, pricing.revision, savedReason, pricing.key,
              command.preview.preview_fingerprint);
            accountingPending = receipt.accounting_pending ?? [];
          } else {
            await accountingPricingClient.applyCase(caseNo, pricing.terms, pricing.revision, savedReason, pricing.key);
          }
        }
      }

      if (command.kind !== 'standard') {
        stage = 'readback';
        const [registry, pricing] = await Promise.all([clientRegistryClient.query(caseNo), accountingPricingClient.queryCase(caseNo)]);
        const registered = registryBirthState(registry.beclass);
        setBirth(registered);
        setBirthCount(registered.value);
        setCurrent({ ...pricing, accounting_pending: pricing.accounting_pending ?? [...accountingPending] });
        setDraft(structuredClone(pricing.terms));
        setReason('');
        setSaveNotice(command.kind === 'historical-birth'
          ? `正式胎數現為${registered.value ?? '待確認'}。`
          : '歷史計價更正已儲存。');
      }
      setPendingSave(null);
      stage = 'refresh';
      await onCommitted();
      if (command.kind === 'standard') onClose();
    } catch (err: unknown) {
      const owner = stage === 'birth' || (stage === 'preview' && birthChanged) ? '胎數' : '計價參數';
      const outcomeUncertain = (stage === 'birth' || stage === 'pricing')
        && (!(err instanceof ApiHttpError) || err.status >= 500 || err.status === 408);
      if (stage === 'readback' && command && command.kind !== 'standard') {
        setPendingSave({ stage: 'readback', command, accountingPending });
        setError('更正已儲存，最新資料讀取失敗。請重新讀取。');
      } else {
        setPendingSave(outcomeUncertain && command ? { stage: 'retry', command } : null);
        if (stage === 'refresh') {
          setError('資料已儲存。帳務畫面更新失敗，請重新整理。');
        } else if (outcomeUncertain) {
          setError(`${owner}儲存結果尚未確認。請按「重試儲存」確認原操作。`);
        } else if (stage === 'pricing' && err instanceof ApiHttpError) {
          setError(pricingRequestError(err, '計價參數未儲存。'));
        } else if (err instanceof ApiHttpError && err.status === 409) {
          setError(`${owner}資料版本已更新，請重新開啟抽屜載入最新資料。`);
        } else {
          const detail = err instanceof ApiHttpError && err.message;
          setError(detail ? `${owner}未儲存。${detail}` : `${owner}未儲存，請稍後重試。`);
        }
      }
      if (standardBirthCommitted && stage === 'pricing') await Promise.resolve().then(onCommitted).catch(() => undefined);
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  };

  return (
    <div
      className="drawer-backdrop open"
      onClick={(e) => {
        if (e.target === e.currentTarget && !saving && !saveUncertain) close();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="調整本案帳務參數抽屜"
    >
      <div ref={drawerRef} className="drawer-container drawer-size-normal" onClick={(e) => e.stopPropagation()}>
        {/* 抽屜標題列 */}
        <div className="drawer-header">
          <div className="drawer-title">
            <span>調整本案帳務參數 · {caseNo}</span>
          </div>
          <button
            type="button"
            className="drawer-close-btn"
            disabled={saving || saveUncertain}
            onClick={close}
            title="關閉抽屜"
          >
            ✕
          </button>
        </div>

        {/* 抽屜內容主體 */}
        <div className="drawer-body">
          {showHistoricalDays ? (
            <HistoricalServiceAccountingWorkbench key={caseNo} caseNo={caseNo} onSaved={onCommitted} />
          ) : (
          <>
          {canEditHistoricalDays && (
            <button type="button" className="finance-btn-secondary" disabled={fieldsDisabled} onClick={() => setShowHistoricalDays(true)}>
              調整歷史訂單服務天數
            </button>
          )}
          <div className="case-banner-note" style={{ margin: '0 0 16px 0' }}>
            <span>💡</span>
            <span>
              {historicalBirth ? '歷史服務完成案件可預覽胎數更正與帳務差額。胎數與人工計價請分別確認。'
                : '服務開始前可更正正式胎數。調整計價會重新計算本案帳務。'}
            </span>
          </div>

          {loading && <p style={{ color: 'var(--md-sys-color-secondary)' }}>正在讀取本案最新帳務參數…</p>}
          {error && (
            <div role="alert" style={{ color: 'var(--md-sys-color-error)', background: '#fee2e2', padding: '10px 14px', borderRadius: '8px', fontSize: '0.82rem', marginBottom: '14px' }}>
              ⚠️ {error}
            </div>
          )}
          {saveNotice && <p role="status">{saveNotice}</p>}
          <HistoricalAccountingPending pending={pendingSave?.stage === 'readback' ? pendingSave.accountingPending : current?.accounting_pending ?? []} />
          {confirmedBirth && (
            <div className="case-banner-note">
              <p>胎數將由{confirmedBirth.preview.before.multi_birth_count ?? '待確認'}更正為{confirmedBirth.value}。</p>
              {confirmedBirth.preview.historical_impact && <HistoricalCorrectionAccounting impact={confirmedBirth.preview.historical_impact} />}
            </div>
          )}
          {confirmedPricing?.historical_plan && <HistoricalCorrectionAccounting impact={confirmedPricing.historical_plan} />}

          {(draft || birthVersion !== null) && !loading && (
            <>
              {/* 1. 胎數設定 */}
              <div className="accounting-drawer-form-group">
                <label className="accounting-drawer-label">👶 胎數設定 (單胞胎 / 雙胞胎)</label>
                <div className="accounting-segmented-control">
                  <button
                    type="button"
                    className={`accounting-segmented-btn ${birthCount === '單胞胎' ? 'active' : ''}`}
                    aria-pressed={birthCount === '單胞胎'}
                    onClick={() => handleBirthCountChange('單胞胎')}
                    disabled={fieldsDisabled || birthVersion === null || (historicalBirth && pricingDraftChanges.length > 0)}
                  >
                    👶 單胞胎 (1位)
                  </button>
                  <button
                    type="button"
                    className={`accounting-segmented-btn ${birthCount === '雙胞胎' ? 'active' : ''}`}
                    aria-pressed={birthCount === '雙胞胎'}
                    onClick={() => handleBirthCountChange('雙胞胎')}
                    disabled={fieldsDisabled || birthVersion === null || (historicalBirth && pricingDraftChanges.length > 0)}
                  >
                    👶👶 雙胞胎 (2位·加成)
                  </button>
                </div>
                <p className="accounting-drawer-hint">
                  {birth?.locked ? '服務已開始，胎數不可更正。'
                    : birthVersion === null ? '目前無法更正胎數，請查閱客戶名冊。'
                    : historicalBirth ? '胎數更正沿用本案的帳務資料。'
                    : '胎數更正會套用本案適用費率。'}
                </p>
                {birthCount === null && <p className="accounting-drawer-hint">正式胎數待確認。</p>}
              </div>

              {draft && <>
              {/* 2. 補助身分與資格 */}
              <div className="accounting-drawer-form-group">
                <label className="accounting-drawer-label" htmlFor="param-identity">補助身分</label>
                <input id="param-identity" className="form-input" value={identityLabel} readOnly />
                {identityLabel !== draft.identity_name && <p className="accounting-drawer-hint">原版本名稱：{draft.identity_name}</p>}
              </div>

              {/* 3. 補助時數上限 */}
              <div className="accounting-drawer-form-group">
                <label className="accounting-drawer-label" htmlFor="param-subsidy-hours">
                  ⏱️ 補助時數上限（小時）
                </label>
                <input
                  id="param-subsidy-hours"
                  type="number"
                  min="0"
                  step="0.5"
                  className="form-input"
                  value={draft.subsidy_hours}
                  disabled={pricingFieldsDisabled || draft.rule === 'non_citizen'}
                  onChange={(e) =>
                    setDraft({ ...draft, subsidy_hours: Math.max(0, Number(e.target.value)) })
                  }
                />
                <p className="accounting-drawer-hint">
                  補助上限按本案實際服務時數累計，超過上限的時數按用盡後時薪計價。
                </p>
              </div>

              {/* 4. 服務時薪標準表格 */}
              <div className="accounting-drawer-form-group">
                <label className="accounting-drawer-label">💰 服務時薪標準 (新臺幣/時)</label>
                <table className="accounting-rates-table">
                  <thead>
                    <tr>
                      <th>計價範圍</th>
                      <th>客戶負擔時薪</th>
                      <th>月嫂服務時薪</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td><strong>補助範圍內</strong></td>
                      <td>
                        <input
                          type="number"
                          min="0"
                          step="1"
                          value={draft.client.covered}
                          disabled={pricingFieldsDisabled || draft.rule === 'non_citizen'}
                          aria-label="補助範圍內客戶時薪"
                          onChange={(e) => {
                            const val = Number(e.target.value);
                            setDraft({
                              ...draft,
                              client: { ...draft.client, covered: val },
                              payroll: { ...draft.payroll, covered: val },
                            });
                          }}
                        />
                      </td>
                      <td>
                        <input
                          type="number"
                          min="0"
                          step="1"
                          value={draft.payroll.covered}
                          disabled={pricingFieldsDisabled || draft.rule === 'non_citizen'}
                          aria-label="補助範圍內月嫂時薪"
                          onChange={(e) => {
                            const val = Number(e.target.value);
                            setDraft({
                              ...draft,
                              client: { ...draft.client, covered: val },
                              payroll: { ...draft.payroll, covered: val },
                            });
                          }}
                        />
                      </td>
                    </tr>
                    <tr>
                      <td><strong>補助用盡後 (超額)</strong></td>
                      <td>
                        <input
                          type="number"
                          min="1"
                          step="1"
                          value={draft.client.excess}
                          disabled={pricingFieldsDisabled}
                          aria-label="補助用盡後客戶時薪"
                          onChange={(e) =>
                            setDraft({
                              ...draft,
                              client: { ...draft.client, excess: Math.max(1, Number(e.target.value)) },
                            })
                          }
                        />
                      </td>
                      <td>
                        <input
                          type="number"
                          min="1"
                          step="1"
                          value={draft.payroll.excess}
                          disabled={pricingFieldsDisabled}
                          aria-label="補助用盡後月嫂時薪"
                          onChange={(e) =>
                            setDraft({
                              ...draft,
                              payroll: { ...draft.payroll, excess: Math.max(1, Number(e.target.value)) },
                            })
                          }
                        />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              </>}

              {/* 調整原因備註 */}
              <div className="accounting-drawer-form-group">
                <label className="accounting-drawer-label" htmlFor="param-reason-input">
                  📝 調整原因說明（留存稽核）
                </label>
                <input
                  id="param-reason-input"
                  type="text"
                  className="form-input"
                  placeholder="例如：依報名問卷更正胎數"
                  maxLength={500}
                  value={reason}
                  disabled={fieldsDisabled}
                  onChange={(e) => setReason(e.target.value)}
                />
              </div>
            </>
          )}
          </>
          )}
        </div>

        {/* 抽屜底部操作按鈕 */}
        <div className="drawer-footer">
          {showHistoricalDays ? (
            <button type="button" className="finance-btn-secondary" onClick={() => requestLeave(() => setShowHistoricalDays(false))}>
              返回帳務參數
            </button>
          ) : (
          <>
          <button
            type="button"
            className="finance-btn-secondary"
            disabled={saving || saveUncertain}
            onClick={pendingSave?.stage === 'confirm' ? () => setPendingSave(null) : close}
          >
            {pendingSave?.stage === 'confirm' ? '返回調整' : '取消'}
          </button>
          <button
            type="button"
            className="finance-btn-primary"
            disabled={saving || loading || (!draft && !birthChanged && !pendingSave)}
            onClick={() => void handleApply()}
          >
            {saving ? '處理中…' : pendingSave?.stage === 'readback' ? '重新讀取已儲存資料'
              : pendingSave?.stage === 'retry' ? '重試儲存'
              : confirmedBirth ? '確認胎數並儲存' : confirmedPricing ? '確認歷史計價更正'
              : historicalBirth && birthChanged ? '預覽歷史胎數更正' : current?.historical ? '預覽歷史計價更正'
              : '儲存本案帳務參數並重算'}
          </button>
          </>
          )}
        </div>
      </div>
    </div>
  );
};
