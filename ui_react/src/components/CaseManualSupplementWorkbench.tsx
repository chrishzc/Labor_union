/**
 * File: CaseManualSupplementWorkbench.tsx
 * Description: 案件抽屜手動補登款項工作台，提供操作銀行（永豐、台新）、交易方向、沖銷對象選擇，自動標準化並完成銷帳。
 */
import { useState, useId } from 'react';
import {
  financeAccountingClient,
  type AccountingItem,
  type CaseAccounting,
  type CaseManualSupplementCommand,
} from '../api/finance_import/finance_accounting_client';
import { financeMoney } from './FinanceReceiptsWorkspace';
import './FinanceCompactCase.css';

interface Props {
  caseNo: string;
  clientItems: CaseAccounting['client_items'];
  staffItems: AccountingItem[];
  subsidyNtd?: number;
  onSuccess: (updated: CaseAccounting) => void;
  onClose: () => void;
}

export function CaseManualSupplementWorkbench({
  caseNo,
  clientItems,
  staffItems,
  subsidyNtd = 0,
  onSuccess,
  onClose,
}: Props) {
  const bankGroupId = useId();
  const dirGroupId = useId();

  const [bank, setBank] = useState<'sinopac' | 'taishin'>('sinopac');
  const [direction, setDirection] = useState<'client_receipt' | 'staff_salary' | 'client_refund' | 'government_subsidy'>('client_receipt');

  // 計算候選期款項目
  const stageNames: Record<string, string> = { deposit: '訂金', first: '第一期', second: '第二期' };

  let candidateItems: { identity: string; label: string; remaining: number | bigint }[] = [];
  if (direction === 'client_receipt') {
    candidateItems = clientItems
      .filter(i => i.direction === 'receivable' && i.payment_stage)
      .map(i => ({
        identity: i.identity,
        label: `${stageNames[i.payment_stage!] || i.label}（待收 ${financeMoney(i.remaining_ntd ?? 0)}／應收 ${financeMoney(i.expected_ntd)}）`,
        remaining: i.remaining_ntd ?? i.expected_ntd,
      }));
  } else if (direction === 'staff_salary') {
    candidateItems = staffItems
      .filter(i => i.direction === 'payable')
      .map(i => ({
        identity: i.identity,
        label: `${i.party} · ${i.label || '月嫂薪資'}（待付 ${financeMoney(i.remaining_ntd ?? 0)}／應付 ${financeMoney(i.expected_ntd)}）`,
        remaining: i.remaining_ntd ?? i.expected_ntd,
      }));
  } else if (direction === 'client_refund') {
    candidateItems = clientItems
      .filter(i => i.direction === 'payable')
      .map(i => ({
        identity: i.identity,
        label: `客戶退款 · ${i.label}（待退 ${financeMoney(i.remaining_ntd ?? 0)}／應退 ${financeMoney(i.expected_ntd)}）`,
        remaining: i.remaining_ntd ?? i.expected_ntd,
      }));
  } else if (direction === 'government_subsidy') {
    candidateItems = [
      {
        identity: 'government_subsidy',
        label: subsidyNtd > 0 ? `政府補助款（本案補助 ${financeMoney(subsidyNtd)}）` : '政府補助款（G 流向）',
        remaining: subsidyNtd,
      },
    ];
  }

  const [targetItem, setTargetItem] = useState<string>(candidateItems[0]?.identity || '');
  const [amount, setAmount] = useState<string>(String(candidateItems[0]?.remaining || ''));
  const [transactionDate, setTransactionDate] = useState<string>(
    new Date().toISOString().slice(0, 10)
  );
  const [reason, setReason] = useState<string>('');
  const [busy, setBusy] = useState<boolean>(false);
  const [error, setError] = useState<string>('');

  function handleDirectionChange(newDir: 'client_receipt' | 'staff_salary' | 'client_refund' | 'government_subsidy') {
    setDirection(newDir);
    if (newDir === 'government_subsidy') {
      setBank('taishin');
    }
    let nextCandidates: typeof candidateItems = [];
    if (newDir === 'client_receipt') {
      nextCandidates = clientItems
        .filter(i => i.direction === 'receivable' && i.payment_stage)
        .map(i => ({
          identity: i.identity,
          label: `${stageNames[i.payment_stage!] || i.label}`,
          remaining: i.remaining_ntd ?? i.expected_ntd,
        }));
    } else if (newDir === 'staff_salary') {
      nextCandidates = staffItems
        .filter(i => i.direction === 'payable')
        .map(i => ({
          identity: i.identity,
          label: `${i.party} · ${i.label || '月嫂薪資'}`,
          remaining: i.remaining_ntd ?? i.expected_ntd,
        }));
    } else if (newDir === 'client_refund') {
      nextCandidates = clientItems
        .filter(i => i.direction === 'payable')
        .map(i => ({
          identity: i.identity,
          label: `客戶退款 · ${i.label}`,
          remaining: i.remaining_ntd ?? i.expected_ntd,
        }));
    } else {
      nextCandidates = [
        {
          identity: 'government_subsidy',
          label: subsidyNtd > 0 ? `政府補助款（本案補助 ${financeMoney(subsidyNtd)}）` : '政府補助款（G 流向）',
          remaining: subsidyNtd,
        },
      ];
    }
    const first = nextCandidates[0];
    if (first) {
      setTargetItem(first.identity);
      setAmount(String(first.remaining > 0 ? first.remaining : ''));
    } else {
      setTargetItem('');
      setAmount('');
    }
  }

  function handleTargetChange(identity: string) {
    setTargetItem(identity);
    const found = candidateItems.find(c => c.identity === identity);
    if (found && found.remaining > 0) {
      setAmount(String(found.remaining));
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const parsedAmount = /^[0-9]+$/.test(amount.trim()) ? BigInt(amount.trim()) : 0n;
    if (!targetItem) {
      setError('請選擇沖銷對象／期款');
      return;
    }
    if (parsedAmount <= 0n) {
      setError('請輸入有效的正整數金額');
      return;
    }
    if (!transactionDate) {
      setError('請選擇交易日期');
      return;
    }

    setBusy(true);
    setError('');

    const command: CaseManualSupplementCommand = {
      bank,
      direction,
      target_item: targetItem,
      amount_ntd: parsedAmount <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(parsedAmount) : parsedAmount.toString(),
      transaction_date: transactionDate,
      reason: reason.trim() || null,
    };

    const idempotencyKey = `manual-supp-${caseNo}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

    try {
      const updated = await financeAccountingClient.manualSupplement(caseNo, command, idempotencyKey);
      onSuccess(updated);
      onClose();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '補登失敗，請確認資料後重試。';
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="case-manual-supplement-card" aria-label="手動補登款項">
      <div className="case-manual-supplement-header">
        <div>
          <h3>手動補登款項並自動銷帳</h3>
          <p>輸入後系統將自動轉化為標準規格對帳單明細並完成銷帳；入帳資訊將註記「人工補登」。</p>
        </div>
        <button
          type="button"
          className="finance-btn-secondary"
          onClick={onClose}
          disabled={busy}
          aria-label="關閉補登表單"
        >
          取消關閉
        </button>
      </div>

      {error && <div className="case-accounting-warning" role="alert"><p>{error}</p></div>}

      <form onSubmit={handleSubmit} className="case-manual-supplement-form">
        <div className="supplement-form-row">
          <label id={bankGroupId} className="supplement-field-label">操作銀行</label>
          <div className="supplement-radio-group" role="radiogroup" aria-labelledby={bankGroupId}>
            <label className={`supplement-radio-pill ${bank === 'sinopac' ? 'is-active' : ''}`}>
              <input
                type="radio"
                name="bank"
                value="sinopac"
                checked={bank === 'sinopac'}
                onChange={() => setBank('sinopac')}
                disabled={busy}
              />
              <span>永豐銀行</span>
            </label>
            <label className={`supplement-radio-pill ${bank === 'taishin' ? 'is-active' : ''}`}>
              <input
                type="radio"
                name="bank"
                value="taishin"
                checked={bank === 'taishin'}
                onChange={() => setBank('taishin')}
                disabled={busy}
              />
              <span>台新銀行</span>
            </label>
          </div>
        </div>

        <div className="supplement-form-row">
          <label id={dirGroupId} className="supplement-field-label">交易方向</label>
          <div className="supplement-radio-group" role="radiogroup" aria-labelledby={dirGroupId}>
            <label className={`supplement-radio-pill ${direction === 'client_receipt' ? 'is-active' : ''}`}>
              <input
                type="radio"
                name="direction"
                value="client_receipt"
                checked={direction === 'client_receipt'}
                onChange={() => handleDirectionChange('client_receipt')}
                disabled={busy}
              />
              <span>客戶收款（入帳）</span>
            </label>
            <label className={`supplement-radio-pill ${direction === 'staff_salary' ? 'is-active' : ''}`}>
              <input
                type="radio"
                name="direction"
                value="staff_salary"
                checked={direction === 'staff_salary'}
                onChange={() => handleDirectionChange('staff_salary')}
                disabled={busy}
              />
              <span>月嫂薪資（出款）</span>
            </label>
            <label className={`supplement-radio-pill ${direction === 'client_refund' ? 'is-active' : ''}`}>
              <input
                type="radio"
                name="direction"
                value="client_refund"
                checked={direction === 'client_refund'}
                onChange={() => handleDirectionChange('client_refund')}
                disabled={busy}
              />
              <span>客戶退款（出款）</span>
            </label>
            <label className={`supplement-radio-pill ${direction === 'government_subsidy' ? 'is-active' : ''}`}>
              <input
                type="radio"
                name="direction"
                value="government_subsidy"
                checked={direction === 'government_subsidy'}
                onChange={() => handleDirectionChange('government_subsidy')}
                disabled={busy}
              />
              <span>政府入款（G 補助）</span>
            </label>
          </div>
        </div>

        <div className="supplement-form-grid">
          <div className="supplement-form-field">
            <label htmlFor="supplement-target">沖銷對象／期款</label>
            {candidateItems.length > 0 ? (
              <select
                id="supplement-target"
                className="finance-select"
                value={targetItem}
                onChange={e => handleTargetChange(e.target.value)}
                disabled={busy}
              >
                {candidateItems.map(c => (
                  <option key={c.identity} value={c.identity}>
                    {c.label}
                  </option>
                ))}
              </select>
            ) : (
              <p className="finance-state">目前無符合此方向之款項項目。</p>
            )}
          </div>

          <div className="supplement-form-field">
            <label htmlFor="supplement-amount">補登金額 (NT$)</label>
            <input
              id="supplement-amount"
              type="number"
              min="1"
              className="finance-input"
              value={amount}
              onChange={e => setAmount(e.target.value)}
              placeholder="請輸入金額"
              disabled={busy}
              required
            />
          </div>

          <div className="supplement-form-field">
            <label htmlFor="supplement-date">交易日期</label>
            <input
              id="supplement-date"
              type="date"
              className="finance-input"
              value={transactionDate}
              onChange={e => setTransactionDate(e.target.value)}
              disabled={busy}
              required
            />
          </div>

          <div className="supplement-form-field">
            <label htmlFor="supplement-reason">備註說明（選填）</label>
            <input
              id="supplement-reason"
              type="text"
              maxLength={200}
              className="finance-input"
              value={reason}
              onChange={e => setReason(e.target.value)}
              placeholder="例如：現金臨櫃收訖、ATM無摺存款"
              disabled={busy}
            />
          </div>
        </div>

        <div className="supplement-form-actions">
          <button
            type="submit"
            className="finance-btn-primary"
            disabled={busy || !targetItem || candidateItems.length === 0}
          >
            {busy ? '正在自動銷帳...' : '確認補登並自動銷帳'}
          </button>
        </div>
      </form>
    </section>
  );
}
