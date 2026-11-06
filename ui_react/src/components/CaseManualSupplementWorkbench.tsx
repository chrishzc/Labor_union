/**
 * File: CaseManualSupplementWorkbench.tsx
 * Description: 案件抽屜手動補登款項工作台，提供操作銀行（永豐、台新）、交易方向、沖銷對象選擇，自動標準化並完成銷帳。
 */
import { useState, useId, useRef, useEffect } from 'react';
import {
  financeAccountingClient,
  type AccountingItem,
  type CaseAccounting,
  type CaseManualSupplementCommand,
} from '../api/finance_import/finance_accounting_client';
import { financeMoney } from './FinanceReceiptsWorkspace';
import { ApiHttpError } from '../api/shared/typed_errors';
import { sessionClient } from '../api/auth/session_client';
import {
  clearPendingManualSupplement, manualSupplementSignature, ManualSupplementStorageError,
  readPendingManualSupplement, savePendingManualSupplement, type PendingManualSupplement,
} from '../api/finance_import/case_manual_supplement_pending';
import './FinanceCompactCase.css';

interface Props {
  caseNo: string;
  clientItems: CaseAccounting['client_items'];
  staffItems: AccountingItem[];
  initialStaffObligation?: string;
  subsidyNtd?: number;
  onSuccess: (updated: CaseAccounting) => void;
  onClose: () => void;
}

export function CaseManualSupplementWorkbench({
  caseNo,
  clientItems,
  staffItems,
  initialStaffObligation,
  subsidyNtd = 0,
  onSuccess,
  onClose,
}: Props) {
  const bankGroupId = useId();
  const dirGroupId = useId();

  const [bank, setBank] = useState<'sinopac' | 'taishin'>('sinopac');
  const [direction, setDirection] = useState<'client_receipt' | 'staff_salary' | 'client_refund' | 'government_subsidy'>(
    initialStaffObligation ? 'staff_salary' : 'client_receipt',
  );

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

  const initialTarget = initialStaffObligation
    ? candidateItems.find(item => item.identity === initialStaffObligation)
    : candidateItems[0];
  const [targetItem, setTargetItem] = useState<string>(initialTarget?.identity ?? '');
  const [amount, setAmount] = useState<string>(String(initialTarget?.remaining || ''));
  const [transactionDate, setTransactionDate] = useState<string>(
    new Date().toISOString().slice(0, 10)
  );
  const [reason, setReason] = useState<string>('');
  const [allowOverageDisposition, setAllowOverageDisposition] = useState(false);
  const [busy, setBusy] = useState<boolean>(false);
  const [unknown, setUnknown] = useState(false);
  const [error, setError] = useState<string>('');
  const pendingCommand = useRef<PendingManualSupplement | null>(null);
  const [restoring, setRestoring] = useState(() => {
    try { return readPendingManualSupplement(caseNo) !== null; } catch { return true; }
  });
  const [storageError, setStorageError] = useState('');
  const [recoveryRevision, setRecoveryRevision] = useState(0);
  const inFlight = useRef(false);
  const alive = useRef(true);
  const activeCase = useRef(caseNo); activeCase.current = caseNo;
  const disabled = busy || unknown || restoring || Boolean(storageError);

  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  useEffect(() => {
    const controller = new AbortController();
    setStorageError('');
    try {
      const stored = readPendingManualSupplement(caseNo)
        ?? (pendingCommand.current?.caseNo === caseNo ? pendingCommand.current : null);
      if (stored === null) {
        pendingCommand.current = null;
        setUnknown(false); setRestoring(false);
        return () => controller.abort();
      }
      setRestoring(true);
      void sessionClient.fetchCurrentUser({ signal: controller.signal }).then(user => {
        if (controller.signal.aborted) return;
        if (user.id === null || user.id !== stored.actorId) {
          throw new ManualSupplementStorageError('此案有另一位管理員尚未確認的補登操作，請由原管理員登入查回。');
        }
        pendingCommand.current = stored;
        setBank(stored.command.bank); setDirection(stored.command.direction);
        setTargetItem(stored.command.target_item); setAmount(String(stored.command.amount_ntd));
        setTransactionDate(stored.command.transaction_date); setReason(stored.command.reason ?? '');
        setAllowOverageDisposition(stored.command.allow_overage_disposition);
        setUnknown(true); setRestoring(false);
        setError('已還原尚未確認的補登操作，請確認原操作結果。');
      }).catch(failure => {
        if (controller.signal.aborted) return;
        setStorageError(failure instanceof ManualSupplementStorageError ? failure.message : '無法確認原補登的登入管理員，請重新登入後讀取補登狀態。');
        setRestoring(false);
      });
    } catch (failure) {
      setStorageError(failure instanceof Error ? failure.message : '無法讀取原補登操作。');
      setRestoring(false);
    }
    return () => controller.abort();
  }, [caseNo, recoveryRevision]);

  function handleDirectionChange(newDir: 'client_receipt' | 'staff_salary' | 'client_refund') {
    setDirection(newDir);
    setAllowOverageDisposition(false);
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
    setAllowOverageDisposition(false);
    const found = candidateItems.find(c => c.identity === identity);
    if (found && found.remaining > 0) {
      setAmount(String(found.remaining));
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (inFlight.current || restoring || storageError) return;
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
      allow_overage_disposition: (direction === 'client_receipt' || direction === 'client_refund') && allowOverageDisposition,
    };

    const signature = manualSupplementSignature(caseNo, command);
    if (unknown && (!pendingCommand.current || manualSupplementSignature(pendingCommand.current.caseNo, pendingCommand.current.command) !== signature)) {
      setError('原操作結果尚未確認，請先查回原操作，不能改成另一筆補登。');
      setBusy(false);
      return;
    }
    inFlight.current = true;
    let attempted = false;
    let updatedCase: CaseAccounting | undefined;
    try {
      // getUser() can be a cached browser projection. Bind to the existing
      // server-authenticated /me result before persisting or replaying a command.
      const user = await sessionClient.fetchCurrentUser();
      if (user.id === null || !Number.isSafeInteger(user.id) || user.id <= 0
        || sessionClient.getUser()?.id !== user.id || !sessionClient.getToken()) {
        throw new ManualSupplementStorageError('無法確認目前登入的管理員，請重新登入後讀取補登狀態。');
      }
      const previous = pendingCommand.current;
      if (previous && previous.actorId !== user.id) {
        throw new ManualSupplementStorageError('此案有另一位管理員尚未確認的補登操作，請由原管理員登入查回。');
      }
      const submitted = previous && manualSupplementSignature(previous.caseNo, previous.command) === signature
        ? previous : { version: 1 as const, caseNo, command: { ...command, allow_overage_disposition: command.allow_overage_disposition ?? false }, key: crypto.randomUUID(), actorId: user.id };
      savePendingManualSupplement(submitted, previous);
      pendingCommand.current = submitted;
      attempted = true;
      updatedCase = await financeAccountingClient.manualSupplement(submitted.caseNo, submitted.command, submitted.key);
      clearPendingManualSupplement(submitted);
      pendingCommand.current = null;
      setUnknown(false);
    } catch (err: unknown) {
      updatedCase = undefined;
      if (!attempted || err instanceof ManualSupplementStorageError) {
        setStorageError(err instanceof ManualSupplementStorageError ? err.message : '無法確認目前登入的管理員，請重新登入後讀取補登狀態。');
        return;
      }
      const rejected = err instanceof ApiHttpError && [400, 401, 403, 404, 409, 422].includes(err.status);
      setUnknown(!rejected);
      const message = err instanceof Error ? err.message : '補登失敗，請確認資料後重試。';
      const missingAccount = err instanceof ApiHttpError && err.code === 'client_refund_recipient_snapshot_missing';
      setError(rejected ? missingAccount
        ? '報名資料缺少客戶退款帳戶，本次未核銷。請先補齊退款帳戶資料，再回本案補登。'
        : message : '尚未確認原操作結果；已保留原操作，請確認原操作結果後再新增補登。');
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
    if (updatedCase && alive.current && activeCase.current === caseNo) { onSuccess(updatedCase); onClose(); }
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
          disabled={disabled}
          aria-label="關閉補登表單"
        >
          取消關閉
        </button>
      </div>

      {error && <div className="case-accounting-warning" role="alert"><p>{error}</p></div>}
      {restoring && <p role="status">正在查回原補登操作…</p>}
      {storageError && <div className="case-accounting-warning" role="alert">
        <p>{storageError}</p>
        <button type="button" className="finance-btn-secondary" disabled={busy || restoring}
          onClick={() => setRecoveryRevision(value => value + 1)}>重新讀取補登狀態</button>
      </div>}

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
                disabled={disabled}
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
                disabled={disabled}
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
                disabled={disabled}
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
                disabled={disabled}
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
                disabled={disabled}
              />
              <span>客戶退款（出款）</span>
            </label>
          </div>
          <p>政府補助入款請從「銀行對帳」選取原政府流水，進入政府整期核對。</p>
        </div>

        {(direction === 'client_receipt' || direction === 'client_refund') && <div className="supplement-form-row">
          <label>
            <input type="checkbox" checked={allowOverageDisposition}
              onChange={event => setAllowOverageDisposition(event.target.checked)} disabled={disabled} />
            {direction === 'client_receipt' ? '將超收差額列為客戶退款' : '將超付差額列為客戶追償'}
          </label>
          <p>{direction === 'client_receipt'
            ? '實收金額全額保留，僅核銷所選期款的待收額，超收差額另列應退客戶款項；不會直接退款。'
            : '實付金額全額保留，僅核銷所選退款的待退額，超付差額另列客戶追償；不會自動追回或再次付款。'}</p>
        </div>}

        <div className="supplement-form-grid">
          <div className="supplement-form-field">
            <label htmlFor="supplement-target">沖銷對象／期款</label>
            {candidateItems.length > 0 ? (
              <select
                id="supplement-target"
                className="finance-select"
                value={targetItem}
                onChange={e => handleTargetChange(e.target.value)}
                disabled={disabled}
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
              disabled={disabled}
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
              disabled={disabled}
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
              disabled={disabled}
            />
          </div>
        </div>

        <div className="supplement-form-actions">
          <button
            type="submit"
            className="finance-btn-primary"
            disabled={busy || restoring || Boolean(storageError) || (!unknown && (!targetItem || candidateItems.length === 0))}
          >
            {busy ? '正在自動銷帳...' : unknown ? '確認原操作結果' : '確認補登並自動銷帳'}
          </button>
        </div>
      </form>
    </section>
  );
}
