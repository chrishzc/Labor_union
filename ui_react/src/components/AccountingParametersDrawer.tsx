/**
 * File: AccountingParametersDrawer.tsx
 * Description: 專案右側滑出式帳務參數調整抽屜（符合 Drawer.css 標準），支援原地調整單雙胞胎、補助上限、客戶與月嫂時薪並即時試算。
 */

import React, { useEffect, useRef, useState } from 'react';
import {
  accountingPricingClient,
  type CasePricing,
  type PricingTerms,
  PricingTermsSchema,
  pricingTermsError,
} from '../api/client_finance/accounting_pricing_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import './AccountingParameters.css';
import './Drawer.css';

interface AccountingParametersDrawerProps {
  caseNo: string;
  isOpen: boolean;
  onClose: () => void;
  onCommitted: () => Promise<void> | void;
  initialPricing?: CasePricing | null;
  initialMultiBirthCount?: string | null;
  totalHours?: number;
}

export const AccountingParametersDrawer: React.FC<AccountingParametersDrawerProps> = ({
  caseNo,
  isOpen,
  onClose,
  onCommitted,
  initialPricing,
  initialMultiBirthCount,
  totalHours = 160,
}) => {
  const [current, setCurrent] = useState<CasePricing | null>(initialPricing ?? null);
  const [isTwins, setIsTwins] = useState<boolean>(
    initialMultiBirthCount === '雙胞胎' || (initialPricing?.terms.payroll.excess ?? 0) >= 450
  );
  const [draft, setDraft] = useState<PricingTerms | null>(initialPricing?.terms ?? null);
  const [reason, setReason] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const inFlight = useRef<boolean>(false);

  // 當抽屜開啟時，載入最新的本案計價資料
  useEffect(() => {
    if (!isOpen || !caseNo) return;
    let active = true;
    setLoading(true);
    setError('');

    void accountingPricingClient
      .queryCase(caseNo)
      .then((res) => {
        if (!active) return;
        setCurrent(res);
        setDraft(structuredClone(res.terms));
        const twinsDetected =
          initialMultiBirthCount === '雙胞胎' || res.terms.payroll.excess >= 450;
        setIsTwins(twinsDetected);
        setLoading(false);
      })
      .catch(() => {
        if (!active) return;
        if (initialPricing) {
          setCurrent(initialPricing);
          setDraft(structuredClone(initialPricing.terms));
        }
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [isOpen, caseNo, initialPricing, initialMultiBirthCount]);

  if (!isOpen) return null;

  // 切換單雙胞胎
  const handleToggleTwins = (twinVal: boolean) => {
    setIsTwins(twinVal);
    if (!draft) return;
    const suggestedRate = twinVal ? 450 : 250;
    setDraft({
      ...draft,
      payroll: {
        covered: draft.subsidy_hours > 0 ? draft.client.covered : suggestedRate,
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
  const staffExcess = draft?.payroll.excess ?? (isTwins ? 450 : 250);

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

    const key = `case-pricing-param:${crypto.randomUUID()}`;
    const applyReason = reason.trim() || `更正帳務參數：${isTwins ? '雙胞胎' : '單胞胎'}，時薪 NT$${staffExcess}/h`;

    try {
      await accountingPricingClient.applyCase(
        caseNo,
        draft,
        current.revision,
        applyReason,
        key
      );
      await onCommitted();
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiHttpError) {
        if (err.status === 409) {
          setError('帳務資料版本已更新，請重新開啟抽屜載入最新資料。');
        } else {
          setError(err.message || '儲存帳務參數未完成，請確認權限與資料。');
        }
      } else {
        setError('儲存失敗，請稍後重試。');
      }
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  };

  return (
    <div
      className="drawer-backdrop open"
      onClick={(e) => {
        if (e.target === e.currentTarget && !saving) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="調整本案帳務參數抽屜"
    >
      <div className="drawer-container drawer-size-normal" onClick={(e) => e.stopPropagation()}>
        {/* 抽屜標題列 */}
        <div className="drawer-header">
          <div className="drawer-title">
            <span>調整本案帳務參數 · {caseNo}</span>
          </div>
          <button
            type="button"
            className="drawer-close-btn"
            disabled={saving}
            onClick={onClose}
            title="關閉抽屜"
          >
            ✕
          </button>
        </div>

        {/* 抽屜內容主體 */}
        <div className="drawer-body">
          <div className="case-banner-note" style={{ margin: '0 0 16px 0' }}>
            <span>💡</span>
            <span>
              在此調整胎數、身分或服務時薪後，系統將<strong>自動重新計算各期款待收與月嫂應付總額</strong>，無需手動重新排班。
            </span>
          </div>

          {loading && <p style={{ color: 'var(--md-sys-color-secondary)' }}>正在讀取本案最新帳務參數…</p>}
          {error && (
            <div style={{ color: 'var(--md-sys-color-error)', background: '#fee2e2', padding: '10px 14px', borderRadius: '8px', fontSize: '0.82rem', marginBottom: '14px' }}>
              ⚠️ {error}
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
                    className={`accounting-segmented-btn ${!isTwins ? 'active' : ''}`}
                    onClick={() => handleToggleTwins(false)}
                    disabled={saving}
                  >
                    👶 單胞胎 (1位)
                  </button>
                  <button
                    type="button"
                    className={`accounting-segmented-btn ${isTwins ? 'active' : ''}`}
                    onClick={() => handleToggleTwins(true)}
                    disabled={saving}
                  >
                    👶👶 雙胞胎 (2位·加成)
                  </button>
                </div>
                <p className="accounting-drawer-hint">
                  切換為雙胞胎時，月嫂服務時薪將自動依工會標準建議為 $450/h。
                </p>
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
                  disabled={saving}
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
                  disabled={saving || draft.rule === 'non_citizen'}
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
                          disabled={saving || draft.rule === 'non_citizen'}
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
                          disabled={saving || draft.rule === 'non_citizen'}
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
                          disabled={saving}
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
                          disabled={saving}
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
                  disabled={saving}
                  onChange={(e) => setReason(e.target.value)}
                />
              </div>
            </>
          )}
        </div>

        {/* 抽屜底部操作按鈕 */}
        <div className="drawer-footer">
          <button
            type="button"
            className="finance-btn-secondary"
            disabled={saving}
            onClick={onClose}
          >
            取消
          </button>
          <button
            type="button"
            className="finance-btn-primary"
            disabled={saving || loading || !draft}
            onClick={() => void handleApply()}
          >
            {saving ? '儲存並同步重算中…' : '儲存本案帳務參數並重算'}
          </button>
        </div>
      </div>
    </div>
  );
};
