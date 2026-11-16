/**
 * File: AccountingParametersDrawer.tsx
 * Description: 專案右側滑出式帳務參數調整抽屜（符合 Drawer.css 標準），支援原地調整單雙胞胎、補助上限、客戶與月嫂時薪並即時試算。
 */

import React, { useEffect, useEffectEvent, useRef, useState } from 'react';
import {
  accountingPricingClient,
  type CasePricing,
  type PricingTerms,
  PricingTermsSchema,
  pricingTermsError,
} from '../api/client_finance/accounting_pricing_client';
import { clientRegistryClient } from '../api/client_registry/client_registry_client';
import type { RegistryMutationPreview } from '../api/client_registry/client_registry_schemas';
import { ApiHttpError } from '../api/shared/typed_errors';
import { HistoricalServiceAccountingWorkbench } from './HistoricalServiceAccountingWorkbench';
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
  totalHours?: number;
}

type BirthCount = '單胞胎' | '雙胞胎';

type PricingSave = {
  terms: PricingTerms;
  revision: number;
  reason: string;
  key: string;
};

type BirthCountSave = {
  value: BirthCount;
  preview: RegistryMutationPreview;
  key: string;
};

type PendingSave =
  | { stage: 'confirm'; pricing: PricingSave; birth: BirthCountSave }
  | { stage: 'retry'; pricing: PricingSave; birth?: BirthCountSave };

export const AccountingParametersDrawer: React.FC<AccountingParametersDrawerProps> = ({
  caseNo,
  isOpen,
  onClose,
  onCommitted,
  initialPricing,
  canEditHistoricalDays = false,
  totalHours = 160,
}) => {
  const [current, setCurrent] = useState<CasePricing | null>(null);
  const [birthCount, setBirthCount] = useState<BirthCount | null>(null);
  const [savedBirthCount, setSavedBirthCount] = useState<BirthCount | null>(null);
  const [birthVersion, setBirthVersion] = useState<number | null>(null);
  const [birthLocked, setBirthLocked] = useState(false);
  const [draft, setDraft] = useState<PricingTerms | null>(null);
  const [reason, setReason] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [showHistoricalDays, setShowHistoricalDays] = useState(false);
  const [pendingSave, setPendingSave] = useState<PendingSave | null>(null);
  const [birthSaveNotice, setBirthSaveNotice] = useState('');
  const { requestLeave } = useUnsavedNavigation();
  const inFlight = useRef<boolean>(false);
  const birthChanged = birthCount !== null && birthCount !== savedBirthCount;
  const saveUncertain = pendingSave?.stage === 'retry';
  const fieldsDisabled = saving || pendingSave !== null;
  const savedBirthLabel = savedBirthCount ?? '待確認';
  const birthDraftChanges = isOpen && birthChanged ? [{ label: '胎數', before: savedBirthLabel, after: birthCount }] : [];
  const pricingDraftChanges = isOpen && current && draft ? [
    { label: '補助身分', before: current.terms.identity_name, after: draft.identity_name },
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
    setBirthVersion(null);
    setBirthLocked(false);
    setBirthCount(null);
    setSavedBirthCount(null);
    setBirthSaveNotice('');
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
        const beclass = registry.value.beclass;
        const value = beclass.values?.multi_birth_count;
        const verifiedBirthCount = value === '單胞胎' || value === '雙胞胎' ? value : null;
        const capability = beclass.field_capabilities.multi_birth_count;
        setBirthCount(verifiedBirthCount);
        setSavedBirthCount(verifiedBirthCount);
        setBirthLocked(capability?.reason === 'multi_birth_count_locked_after_service_start');
        if (beclass.status === 'ready' && capability?.editable) setBirthVersion(beclass.version);
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

  // 切換單雙胞胎
  const handleBirthCountChange = (value: BirthCount) => {
    if (!draft || birthVersion === null || birthCount === value) return;
    setBirthCount(value);
    const suggestedRate = value === '雙胞胎' ? 450 : 250;
    setDraft({
      ...draft,
      payroll: {
        ...draft.payroll,
        excess: suggestedRate,
      },
    });
  };

  // 身分切換
  const handleIdentityChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    if (!draft) return;
    const val = e.target.value;
    let rule: 'citizen' | 'social' | 'non_citizen' = 'citizen';
    let subsidyHours = 120;
    let identityName = '補助市民';

    if (val === 'low_income') {
      rule = 'social';
      identityName = '低收入戶';
      subsidyHours = 120;
    } else if (val === 'indigenous') {
      rule = 'citizen';
      identityName = '原住民';
      subsidyHours = 80;
    } else if (val === 'regular_citizen') {
      rule = 'citizen';
      identityName = '一般市民';
      subsidyHours = 0;
    } else if (val === 'non_citizen') {
      rule = 'non_citizen';
      identityName = '非市民';
      subsidyHours = 0;
    }

    setDraft({
      ...draft,
      rule,
      identity_name: identityName,
      subsidy_hours: subsidyHours,
      client: {
        ...draft.client,
        covered: subsidyHours === 0 ? 0 : val === 'indigenous' ? 350 : draft.client.covered,
      },
      payroll: val === 'indigenous' ? { ...draft.payroll, covered: 350 } : draft.payroll,
    });
  };

  // 計算即時影響
  const subsidyHours = draft?.subsidy_hours ?? 0;
  const clientCovered = draft?.client.covered ?? 0;
  const clientExcess = draft?.client.excess ?? 300;
  const staffExcess = draft?.payroll.excess ?? 0;

  const coveredHours = Math.min(totalHours, subsidyHours);
  const excessHours = Math.max(0, totalHours - coveredHours);
  const previewClientTotal = coveredHours * clientCovered + excessHours * clientExcess;
  const previewStaffTotal = totalHours * staffExcess;

  // 儲存送出
  const handleApply = async () => {
    if (!current || !draft || inFlight.current || saving) return;

    // 驗證規則
    const validationError = pricingTermsError(draft);
    if (validationError) {
      setError(validationError);
      return;
    }

    const parseResult = PricingTermsSchema.safeParse(draft);
    if (!parseResult.success) {
      setError('請確認輸入的時薪數值為正整數。');
      return;
    }

    inFlight.current = true;
    setSaving(true);
    setError('');

    let birth = pendingSave?.birth;
    const pricing: PricingSave = pendingSave?.pricing ?? {
      terms: draft,
      revision: current.revision,
      reason: reason.trim(),
      key: `case-pricing-param:${crypto.randomUUID()}`,
    };
    let stage: 'preview' | 'birth' | 'pricing' | 'refresh' = 'preview';
    let birthCommitted = false;

    try {
      if (!pendingSave && birthChanged) {
        if (birthVersion === null) {
          setError('目前無法更正胎數，請重新開啟抽屜確認。');
          return;
        }
        const preview = await clientRegistryClient.preview(caseNo, 'beclass', { multi_birth_count: birthCount }, birthVersion);
        setPendingSave({ stage: 'confirm', pricing, birth: { value: birthCount, preview, key: `case-birth-count:${crypto.randomUUID()}` } });
        return;
      }
      if (birth) {
        stage = 'birth';
        const receipt = await clientRegistryClient.apply(caseNo, 'beclass', { multi_birth_count: birth.value },
          birth.preview.current_version, birth.preview.preview_fingerprint, pricing.reason, birth.key);
        if (receipt.readback.multi_birth_count !== birth.value) {
          setPendingSave(null);
          setBirthVersion(null);
          setError('目前正式胎數與本次更正不同，計價參數尚未送出。請重新開啟抽屜確認最新資料。');
          return;
        }
        setSavedBirthCount(birth.value);
        setBirthVersion(receipt.resulting_version);
        setBirthSaveNotice(`胎數已儲存為${birth.value}。`);
        birth = undefined;
        birthCommitted = true;
      }
      stage = 'pricing';
      const pricingReceipt = await accountingPricingClient.applyCase(caseNo, pricing.terms, pricing.revision, pricing.reason, pricing.key);
      setCurrent({ ...current, revision: pricingReceipt.revision, terms: pricing.terms, source: 'manual' });
      setPendingSave(null);
      stage = 'refresh';
      await onCommitted();
      onClose();
    } catch (err: unknown) {
      const owner = stage === 'birth' || stage === 'preview' ? '胎數' : '計價參數';
      const outcomeUncertain = (stage === 'birth' || stage === 'pricing')
        && (!(err instanceof ApiHttpError) || err.status >= 500 || err.status === 408);
      setPendingSave(outcomeUncertain ? { stage: 'retry', pricing, birth } : null);
      if (stage === 'refresh') {
        setError('計價參數已儲存。帳務畫面更新失敗，請重新整理。');
      } else if (outcomeUncertain) {
        setError(`${owner}儲存結果尚未確認。請按「重試儲存」確認原操作。`);
      } else if (err instanceof ApiHttpError && err.status === 409) {
        setError(`${owner}資料版本已更新，請重新開啟抽屜載入最新資料。`);
      } else {
        const detail = err instanceof ApiHttpError && err.message;
        setError(detail ? `${owner}未儲存。${detail}` : `${owner}未儲存，請稍後重試。`);
      }
      if (birthCommitted && stage === 'pricing') await Promise.resolve().then(onCommitted).catch(() => undefined);
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
              服務開始前可更正正式胎數。調整計價後，系統會<strong>重新計算本案帳務</strong>。
            </span>
          </div>

          {loading && <p style={{ color: 'var(--md-sys-color-secondary)' }}>正在讀取本案最新帳務參數…</p>}
          {error && (
            <div role="alert" style={{ color: 'var(--md-sys-color-error)', background: '#fee2e2', padding: '10px 14px', borderRadius: '8px', fontSize: '0.82rem', marginBottom: '14px' }}>
              ⚠️ {error}
            </div>
          )}
          {birthSaveNotice && <p role="status">{birthSaveNotice}</p>}
          {pendingSave?.stage === 'confirm' && (
            <div role="status" className="case-banner-note">
              <p>胎數將由{pendingSave.birth.preview.before.multi_birth_count ?? '待確認'}更正為{pendingSave.birth.value}。請確認後儲存胎數及計價參數。</p>
            </div>
          )}

          {draft && !loading && (
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
                    disabled={fieldsDisabled || birthVersion === null}
                  >
                    👶 單胞胎 (1位)
                  </button>
                  <button
                    type="button"
                    className={`accounting-segmented-btn ${birthCount === '雙胞胎' ? 'active' : ''}`}
                    aria-pressed={birthCount === '雙胞胎'}
                    onClick={() => handleBirthCountChange('雙胞胎')}
                    disabled={fieldsDisabled || birthVersion === null}
                  >
                    👶👶 雙胞胎 (2位·加成)
                  </button>
                </div>
                <p className="accounting-drawer-hint">
                  {birthLocked ? '服務已開始，胎數不可更正。'
                    : birthVersion === null ? '目前無法更正胎數，請查閱客戶名冊。'
                    : '選擇雙胞胎會帶入月嫂超額時薪 450 元，可再調整。'}
                </p>
                {birthCount === null && <p className="accounting-drawer-hint">正式胎數待確認。</p>}
              </div>

              {/* 2. 補助身分與資格 */}
              <div className="accounting-drawer-form-group">
                <label className="accounting-drawer-label" htmlFor="param-identity-select">
                  🏛️ 補助身分等級
                </label>
                <select
                  id="param-identity-select"
                  className="form-select"
                  value={
                    draft.rule === 'social'
                      ? 'low_income'
                      : draft.rule === 'non_citizen'
                      ? 'non_citizen'
                      : draft.subsidy_hours === 0
                      ? 'regular_citizen'
                      : draft.identity_name === '原住民'
                      ? 'indigenous'
                      : 'citizen_subsidy'
                  }
                  disabled={fieldsDisabled}
                  onChange={handleIdentityChange}
                >
                  <option value="citizen_subsidy">補助市民（一般補助 · 上限 120h）</option>
                  <option value="low_income">低收入戶市民（全額免自備 · 上限 120h）</option>
                  <option value="indigenous">原住民市民（預設上限 80h · 350 元）</option>
                  <option value="regular_citizen">一般市民（無補助自備 · 上限 0h）</option>
                  <option value="non_citizen">非市民（全額自費 · 上限 0h）</option>
                </select>
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
                  disabled={fieldsDisabled || draft.rule === 'non_citizen'}
                  onChange={(e) =>
                    setDraft({ ...draft, subsidy_hours: Math.max(0, Number(e.target.value)) })
                  }
                />
                <p className="accounting-drawer-hint">
                  本案累計總服務時數約 {totalHours} 小時。超出補助上限之 {excessHours} 小時將計入超額自費。
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
                          disabled={fieldsDisabled || draft.rule === 'non_citizen'}
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
                          disabled={fieldsDisabled || draft.rule === 'non_citizen'}
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
                          disabled={fieldsDisabled}
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
                          disabled={fieldsDisabled}
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

              {/* 5. 即時試算連動影響 */}
              <div className="accounting-impact-card">
                <div className="accounting-impact-header">
                  <span>✨ 即時試算連動影響</span>
                </div>
                <div className="accounting-impact-grid">
                  <div>
                    <span>客戶應收總額 (自備+超額):</span>
                    <strong>NT$ {previewClientTotal.toLocaleString()}</strong>
                  </div>
                  <div>
                    <span>月嫂基準應付總額:</span>
                    <strong style={{ color: 'var(--md-sys-color-primary)' }}>
                      NT$ {previewStaffTotal.toLocaleString()}
                    </strong>
                  </div>
                </div>
              </div>

              {/* 6. 調整原因備註 */}
              <div className="accounting-drawer-form-group">
                <label className="accounting-drawer-label" htmlFor="param-reason-input">
                  📝 調整原因說明（留存稽核）
                </label>
                <input
                  id="param-reason-input"
                  type="text"
                  className="form-input"
                  placeholder="例如：更正雙胞胎補助資格，連動調整時薪與各期應繳"
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
            disabled={saving || loading || !draft}
            onClick={() => void handleApply()}
          >
            {saving ? '處理中…' : pendingSave?.stage === 'confirm' ? '確認胎數並儲存'
              : saveUncertain ? '重試儲存' : '儲存本案帳務參數並重算'}
          </button>
          </>
          )}
        </div>
      </div>
    </div>
  );
};
