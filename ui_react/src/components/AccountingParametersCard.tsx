/**
 * File: AccountingParametersCard.tsx
 * Description: 案件帳務詳細頂部核心計價參數卡，展示單雙胞胎、補助身分、服務時薪與試算關聯。
 */

import React, { useEffect, useState } from 'react';
import { accountingPricingClient, type CasePricing } from '../api/client_finance/accounting_pricing_client';
import './AccountingParameters.css';

interface AccountingParametersCardProps {
  caseNo: string;
  pricing?: CasePricing | null;
  multiBirthCount?: string | null;
  serviceHours?: number | null;
  customerAmountNtd?: number | bigint | null;
  staffAmountNtd?: number | bigint | null;
  disabled?: boolean;
  onOpenEdit: () => void;
}

export const AccountingParametersCard: React.FC<AccountingParametersCardProps> = ({
  caseNo,
  pricing: propPricing,
  multiBirthCount,
  serviceHours,
  customerAmountNtd,
  staffAmountNtd,
  disabled = false,
  onOpenEdit,
}) => {
  const [pricing, setPricing] = useState<CasePricing | null>(propPricing ?? null);

  useEffect(() => {
    if (propPricing) {
      setPricing(propPricing);
      return;
    }
    if (!caseNo) return;
    setPricing(null);
    let active = true;
    void accountingPricingClient
      .queryCase(caseNo)
      .then((res) => {
        if (active) setPricing(res);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [caseNo, propPricing]);
  const isTwins = multiBirthCount === '雙胞胎' || (pricing?.terms.payroll.excess ?? 0) >= 450;
  const identityName = pricing?.terms.identity_name ?? '待確認';
  const subsidyHours = pricing?.terms.subsidy_hours;
  const clientCovered = pricing?.terms.client.covered;
  const clientExcess = pricing?.terms.client.excess;
  const staffRate = pricing?.terms.payroll.excess;

  const totalHours = serviceHours ?? (pricing?.impact ? pricing.impact.covered_hours + pricing.impact.excess_hours : null);
  const coveredHours = pricing?.impact.covered_hours;
  const excessHours = pricing?.impact.excess_hours;

  const displayCustomerAmount = customerAmountNtd != null
    ? customerAmountNtd.toLocaleString()
    : pricing?.impact?.client_amount?.toLocaleString();

  const displayStaffAmount = staffAmountNtd != null
    ? staffAmountNtd.toLocaleString()
    : pricing?.impact?.staff_total_amount?.toLocaleString();

  return (
    <div className="accounting-params-card" aria-label="帳務計價依據與核心參數">
      <div className="accounting-params-header">
        <div className="accounting-params-title">
          <span className="accounting-params-eyebrow">帳務核心參數</span>
          <h3>本案計價身分、胎數與服務時薪依據</h3>
        </div>
        <button
          type="button"
          className="finance-btn-primary"
          disabled={disabled}
          onClick={onOpenEdit}
          title="調整單雙胞胎、補助時數或服務時薪"
        >
          <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ marginRight: '4px' }}>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
          </svg>
          調整帳務參數
        </button>
      </div>

      {!pricing && <p role="status">計價依據待確認，既有應繳／應付金額仍依正式帳務來源顯示。</p>}

      <div className="accounting-params-grid">
        {/* 胎數類別 */}
        <div className="accounting-param-item">
          <dt>胎數類別</dt>
          <dd>
            <span className={isTwins ? 'chip-twins-multi' : 'chip-twins-single'}>
              {isTwins ? '雙胞胎 (2位·加成)' : '單胞胎 (1位)'}
            </span>
          </dd>
        </div>

        {/* 補助資格 */}
        <div className="accounting-param-item">
          <dt>補助身分與上限</dt>
          <dd>
            <span className="chip-subsidy">
              {identityName}{subsidyHours == null ? '（補助時數待確認）' : ` (${subsidyHours}h)`}
            </span>
          </dd>
        </div>

        {/* 客戶時薪 */}
        <div className="accounting-param-item">
          <dt>客戶自備 / 超額時薪</dt>
          <dd>
            <span>補助: <strong className="param-highlight">{clientCovered == null ? '待確認' : `$${clientCovered}`}</strong></span>
            <span style={{ color: '#dec0b6', margin: '0 2px' }}>/</span>
            <span>超額: <strong className="param-highlight">{clientExcess == null ? '待確認' : `$${clientExcess}`}</strong></span>
          </dd>
        </div>

        {/* 月嫂時薪 */}
        <div className="accounting-param-item">
          <dt>月嫂服務時薪</dt>
          <dd>
            <span>{staffRate == null ? '時薪待確認' : <>每小時 <strong className="param-highlight">${staffRate}</strong> 元</>}</span>
          </dd>
        </div>
      </div>

      <div className="accounting-params-footer">
        <span>
          {totalHours == null || coveredHours == null || excessHours == null ? '服務時數計價依據待確認' : <>💡 計價依據：服務總時數 {totalHours}h（補助範圍 {coveredHours}h + 超額 {excessHours}h）{isTwins ? '｜ 雙胞胎加成費率' : ''}</>}
        </span>
        <span style={{ fontWeight: 600, color: 'var(--md-sys-color-primary)' }}>
          連動總額：客戶應繳 {displayCustomerAmount == null ? '待確認' : `NT$ ${displayCustomerAmount}`} ｜ 月嫂基準應付 {displayStaffAmount == null ? '待確認' : `NT$ ${displayStaffAmount}`}
        </span>
      </div>
    </div>
  );
};
