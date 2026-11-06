/**
 * File: CaseDifferenceResolutionWorkbench.tsx
 * Description: 案件期款差額處置與通知連動工作台，提供雙軌處置（直接銷帳／認列差額，原因選填）與發送補繳／溢繳通知。
 */
import { useEffect, useState } from 'react';
import { differenceResolutionClient, type ClientDifferenceView } from '../api/client_finance/difference_resolution_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { financeMoney } from './FinanceReceiptsWorkspace';

export interface CaseDifferenceWorkbenchProps {
  caseNo: string;
  stageName: string;
  stageKey: string;
  expectedNtd: number;
  actualNtd: number;
  remainingNtd: number;
  diffNtd: number;
  diffClient?: ClientDifferenceView;
  recipientLabel?: string;
  onOpenNotice: () => void;
  onChanged: () => void;
  onClose: () => void;
}

export function CaseDifferenceResolutionWorkbench({
  caseNo,
  stageName,
  stageKey,
  expectedNtd,
  actualNtd,
  remainingNtd,
  diffNtd,
  diffClient: initialDiffClient,
  recipientLabel,
  onOpenNotice,
  onChanged,
  onClose,
}: CaseDifferenceWorkbenchProps) {
  const [diffClient, setDiffClient] = useState<ClientDifferenceView | undefined>(initialDiffClient);
  const [mode, setMode] = useState<'settle_direct' | 'recognize_diff'>('settle_direct');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    if (initialDiffClient) {
      setDiffClient(initialDiffClient);
      return;
    }
    const controller = new AbortController();
    void differenceResolutionClient.client(caseNo, controller.signal)
      .then(res => setDiffClient(res))
      .catch(() => {});
    return () => controller.abort();
  }, [caseNo, initialDiffClient]);

  const isShort = diffNtd < 0 || remainingNtd > 0;
  const absDiff = Math.abs(diffNtd || remainingNtd);

  async function handleCommit() {
    if (busy) return;
    const targetItem = diffClient?.items.find(i => i.kind === stageKey)
      ?? diffClient?.items.find(i => i.identity === stageKey)
      ?? diffClient?.items[0];
    if (!targetItem) {
      setError('找不到可處置的款項項目，請重新查詢案件。');
      return;
    }
    setBusy(true);
    setError('');
    setSuccess('');
    try {
      await differenceResolutionClient.apply(caseNo, 'client', {
        identity: targetItem.identity,
        action: mode,
        amount_ntd: targetItem.remaining_ntd,
        reason: reason.trim(),
        expected_version: diffClient?.version ?? 0,
        key: crypto.randomUUID(),
      });
      setSuccess(`已成功依「${mode === 'settle_direct' ? '直接銷帳' : '認列差額'}」處置 ${stageName} 差額，本期帳務已結清。`);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiHttpError ? err.message : '差額處置失敗，請重新查詢。');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="finance-diff-workbench" aria-label={`${stageName}差額處置與帳務核對`}>
      <header className="finance-diff-header">
        <div className="finance-diff-title-group">
          <span className="finance-diff-indicator" />
          <div>
            <h4>{stageName} · 差額處置與帳務核對</h4>
            <small>系統已比對虛擬帳號與交易月份，請確認帳務處置方式或發送通知</small>
          </div>
        </div>
        <div className="finance-diff-tag-group">
          <span className="finance-diff-tag-label">客觀事實</span>
          <strong className={isShort ? 'finance-diff-under' : 'finance-diff-over'}>
            {isShort ? `少收 ${financeMoney(absDiff)}` : `多收 ${financeMoney(absDiff)}`}
          </strong>
          <button type="button" className="finance-diff-close" onClick={onClose} title="收合面板">✕</button>
        </div>
      </header>

      {/* 1. Facts Comparison Bar */}
      <div className="finance-diff-facts-bar">
        <div>
          <span>應收／應繳總額</span>
          <strong>{financeMoney(expectedNtd)}</strong>
        </div>
        <div>
          <span>銀行實際入帳</span>
          <strong>{financeMoney(actualNtd)}</strong>
        </div>
        <div>
          <span>差額數值</span>
          <strong className={isShort ? 'finance-diff-under' : 'finance-diff-over'}>
            {isShort ? `- ${financeMoney(absDiff)}` : `+ ${financeMoney(absDiff)}`}
          </strong>
        </div>
      </div>

      {error && <p role="alert" className="finance-diff-error">{error}</p>}

      {/* 2. Dual-Track Actions */}
      <div className="finance-diff-dual-track">
        
        {/* Track 1: 工會內部帳務處置 */}
        <div className="finance-diff-card">
          <div className="finance-diff-card-badge-row">
            <span className="finance-diff-badge-track">途徑 1</span>
            <strong>工會帳務處置（平帳結清）</strong>
          </div>

          <div className="finance-diff-options">
            <label className={`finance-diff-option ${mode === 'settle_direct' ? 'is-selected' : ''}`}>
              <input
                type="radio"
                name={`diff_mode_${stageKey}`}
                value="settle_direct"
                checked={mode === 'settle_direct'}
                disabled={busy}
                onChange={() => setMode('settle_direct')}
              />
              <div>
                <strong>直接銷帳</strong>
                <small>原期款直接標記結清，剩餘差額不再追收／退補，待結餘額歸零。</small>
              </div>
            </label>

            <label className={`finance-diff-option ${mode === 'recognize_diff' ? 'is-selected' : ''}`}>
              <input
                type="radio"
                name={`diff_mode_${stageKey}`}
                value="recognize_diff"
                checked={mode === 'recognize_diff'}
                disabled={busy}
                onChange={() => setMode('recognize_diff')}
              />
              <div>
                <strong>認列差額</strong>
                <small>保留實際收付事實，將差額計入工會差額認列紀錄並結清本期。</small>
              </div>
            </label>
          </div>

          <label className="finance-diff-reason-field">
            <span>處置原因／備註說明 <small>（選填，可留空）</small></span>
            <input
              type="text"
              value={reason}
              disabled={busy}
              placeholder="例：雙方協議折讓、銀行手續費等（選填）"
              onChange={e => setReason(e.target.value)}
            />
          </label>

          <button
            type="button"
            className="finance-btn-primary finance-diff-commit-btn"
            disabled={busy}
            onClick={() => void handleCommit()}
          >
            {busy ? '正在處置…' : '確認處置並結清本期'}
          </button>
        </div>

        {/* Track 2: 通知對方 */}
        <div className="finance-diff-card finance-diff-card-notice">
          <div className="finance-diff-card-badge-row">
            <span className="finance-diff-badge-notice">途徑 2</span>
            <strong>通知對方（要求補繳／退補）</strong>
          </div>

          <p className="finance-diff-notice-desc">
            {isShort
              ? '若不吸收差額，需要請對方補齊款項，可發送官方 LINE 補繳通知帶入 14 碼專屬虛擬帳號。'
              : '客戶此期存在溢收差額，可發送 LINE 通知確認溢收，或告知退款安排。'}
          </p>

          <div className="finance-diff-notice-info">
            <div>
              <span>通知對象：</span>
              <strong>{recipientLabel || '案件專屬 LINE 群組'}</strong>
            </div>
            <div>
              <span>{isShort ? '預計通知補繳：' : '預計通知退款：'}</span>
              <strong className={isShort ? 'finance-diff-under' : 'finance-diff-over'}>
                {financeMoney(absDiff)}
              </strong>
            </div>
          </div>

          <button
            type="button"
            className="finance-btn-secondary finance-diff-notice-btn"
            onClick={onOpenNotice}
          >
            {isShort ? `開啟 LINE 補繳通知草稿（補繳 ${financeMoney(absDiff)}）` : `開啟 LINE 溢繳通知草稿（退款 ${financeMoney(absDiff)}）`}
          </button>
        </div>

      </div>

      {/* Success Feedback Box */}
      {success && (
        <div className="finance-diff-success-box" role="status">
          <div className="finance-diff-success-header">
            <span>✓</span>
            <strong>{success}</strong>
          </div>
          <div className="finance-diff-success-actions">
            <span>後續選項：</span>
            <button
              type="button"
              className="finance-btn-secondary finance-diff-btn-sm"
              onClick={onOpenNotice}
            >
              發送帳務已結清／差額說明通知給客戶
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
