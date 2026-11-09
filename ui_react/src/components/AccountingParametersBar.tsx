/**
 * File: AccountingParametersBar.tsx
 * Description: 銀行核對抽屜專用的精簡帳務參數醒目條與原地更正入口。
 */

import React from 'react';
import type { CasePricing } from '../api/client_finance/accounting_pricing_client';
import './AccountingParameters.css';

interface AccountingParametersBarProps {
  caseNo: string;
  pricing?: CasePricing | null;
  multiBirthCount?: string | null;
  customerStage2Due?: number | bigint | null;
  disabled?: boolean;
  onOpenEdit: () => void;
}

export const AccountingParametersBar: React.FC<AccountingParametersBarProps> = ({
  pricing,
  multiBirthCount,
  customerStage2Due,
  disabled = false,
  onOpenEdit,
}) => {
  const isTwins = multiBirthCount === '雙胞胎' || (pricing?.terms.payroll.excess ?? 0) >= 450;
  const identityName = pricing?.terms.identity_name || '一般市民';
  const subsidyHours = pricing?.terms.subsidy_hours ?? 0;
  const clientExcess = pricing?.terms.client.excess ?? 300;

  return (
    <div className="bank-params-inline-bar" aria-label="本案計價依據">
      <div className="bank-params-summary-text">
        <span>⚡ <strong>本案計價依據：</strong></span>
        <span className={isTwins ? 'chip-twins-multi' : 'chip-twins-single'}>
          {isTwins ? '雙胞胎' : '單胞胎'}
        </span>
        <span className="chip-subsidy">
          {identityName} ({subsidyHours}h)
        </span>
        <span>客戶超額時薪：<strong>${clientExcess}/h</strong></span>
        {customerStage2Due != null && (
          <span>預期應繳：<strong>NT$ {customerStage2Due.toLocaleString()}</strong></span>
        )}
      </div>
      <button
        type="button"
        className="finance-btn-secondary"
        style={{ padding: '5px 12px', fontSize: '0.78rem' }}
        disabled={disabled}
        onClick={onOpenEdit}
        title="原地調整本案帳務參數（胎數、補助上限、服務時薪）"
      >
        ✏️ 原地更正參數
      </button>
    </div>
  );
};
