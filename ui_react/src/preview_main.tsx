/**
 * File: preview_main.tsx
 * Description: 供瀏覽器驗證與展示用的合成資料頁面，展示核對交易抽屜頁面全部狀態統一為標準版之成果。
 */
import { useState } from 'react';
import ReactDOM from 'react-dom/client';
import './styles/design-tokens.css';
import './components/FinanceCompactCase.css';
import './components/FinanceCaseAccounting.css';
import './components/FinanceBankReconciliationWorkspace.css';
import { ClientReceiptReconciliationPanel } from './components/ClientReceiptReconciliationPanel';
import { clientReceiptQueryClient } from './api/client_finance/client_receipt_query_client';
import { clientReceiptReconciliationClient } from './api/client_finance/client_receipt_reconciliation_client';
import { financeAccountingClient } from './api/finance_import/finance_accounting_client';

const syntheticCaseNo = '115000103';
const syntheticReceiptFacts = {
  case_no: syntheticCaseNo,
  account_version: 1,
  bank_facts: [
    {
      finance_import_row_id: 241,
      amount_ntd: 6000,
      transaction_date: '2026-06-29',
      dedup_fingerprint: 'a'.repeat(64),
    },
    {
      finance_import_row_id: 365,
      amount_ntd: 12000,
      transaction_date: '2026-10-20',
      dedup_fingerprint: 'b'.repeat(64),
    },
  ],
  obligations: [
    {
      obligation_identity: 'historical-service:115000103:revision:1:client:receivable_from_client',
      payment_stage: 'adjustment' as const,
      amount_due_ntd: 18000,
      due_date: null,
    },
    {
      obligation_identity: 'client-obligation:115000103:deposit',
      payment_stage: 'deposit' as const,
      amount_due_ntd: 6000,
      due_date: '2026-06-26',
    },
    {
      obligation_identity: 'client-obligation:115000103:first',
      payment_stage: 'first' as const,
      amount_due_ntd: 12000,
      due_date: '2026-10-19',
    },
  ],
};

clientReceiptQueryClient.query = async () => syntheticReceiptFacts;
financeAccountingClient.query = async () => ({
  case_no: syntheticCaseNo,
  client_name: '柯雅玲',
  receivable_ntd: 18000,
  received_ntd: 0,
  payable_ntd: null,
  paid_ntd: null,
  pending_warning_count: 0,
  customer_amount_ntd: 18000,
  customer_fully_received: false,
  client_items: syntheticReceiptFacts.obligations.map((item) => ({
    identity: item.obligation_identity,
    direction: 'receivable' as const,
    label: item.payment_stage,
    party: '柯雅玲',
    expected_ntd: item.amount_due_ntd,
    actual_ntd: 0,
    has_payment: false,
    version: `1:1:0`,
    due_date: item.due_date,
    remaining_ntd: item.amount_due_ntd,
  })),
  staff_items: [],
  transactions: [],
  warnings: [],
});
clientReceiptReconciliationClient.preview = async (_caseNo, selection, action) => {
  const bankTotal = syntheticReceiptFacts.bank_facts
    .filter((b) => selection.finance_import_row_ids.includes(b.finance_import_row_id))
    .reduce((s, b) => s + b.amount_ntd, 0);
  const selectedObligations = syntheticReceiptFacts.obligations.filter((o) =>
    selection.obligation_identities.includes(o.obligation_identity)
  );
  const obligationTotal = selectedObligations.reduce((s, o) => s + o.amount_due_ntd, 0);
  const status =
    bankTotal === obligationTotal
      ? 'exact'
      : action === 'partial'
      ? 'partial'
      : action === 'overage'
      ? 'overage'
      : 'review_required';
  let remainingBank = bankTotal;
  const allocations = selectedObligations.map((o) => {
    const allocated = Math.min(remainingBank, o.amount_due_ntd);
    remainingBank -= allocated;
    return {
      bank_fact_identity: String(selection.finance_import_row_ids[0] ?? 365),
      obligation_identity: o.obligation_identity,
      amount: { amount: allocated },
    };
  });
  return {
    account_version: 1,
    preview_fingerprint: 'c'.repeat(64),
    candidate: {
      status,
      payment_stage: null,
      bank_total: { amount: bankTotal },
      obligation_total: { amount: obligationTotal },
      overage_amount: { amount: Math.max(0, bankTotal - obligationTotal) },
      allocations,
      blockers: status === 'review_required' ? ['amount_mismatch'] : [],
      settlement_identity: 'd'.repeat(64),
    },
  };
};
clientReceiptReconciliationClient.apply = async (caseNo) => ({
  case_no: caseNo,
  account_version: 1,
  status: 'exact',
  settlement_identity: 'd'.repeat(64),
  ledger_entry_count: 1,
  allocation_count: 1,
  blockers: [],
});

// 狀況 1：客戶入款（標準版範本，直接掛載真實 ClientReceiptReconciliationPanel 與合成測試資料）
function ClientReceiptReconciliationPreview() {
  return (
    <ClientReceiptReconciliationPanel
      caseNo={syntheticCaseNo}
      requiredBankRowId={365}
      initialObligationId="client-obligation:115000103:first"
      onChanged={() => {}}
    />
  );
}

// 狀況 2：月嫂薪資（統一後標準版，對照原截圖 1）
function StaffPayoutReconciliationPreview() {
  const [differenceMode, setDifferenceMode] = useState('');
  const [reason, setReason] = useState('');

  return (
    <section className="case-accounting-card finance-advanced-reconciliation-card" aria-label="月嫂付款核銷">
      <div className="finance-section-heading">
        <div className="finance-reconciliation-heading-group">
          <h3>待沖銷銀行出款與月嫂應付款對核</h3>
          <span className="finance-tag-imported">月嫂款項沖銷</span>
        </div>
        <button type="button" className="finance-btn-secondary">重新讀取</button>
      </div>

      <div className="finance-advanced-reconciliation-guide">
        <strong>💡 作用說明：</strong>銀行對帳單已辨識到本案的月嫂款項出款（如下左側）。請確認要將此筆款項<strong>沖抵哪一筆應付款項</strong>（如下右側）。核對確認後，系統將正式記錄實付並更新應付款狀態。
        <span style={{ display: 'block', marginTop: '4px', fontSize: '0.8rem', color: '#6b5f54' }}>
          <strong>解除條件：</strong>只核對既有銀行入帳資料，不會發動銀行匯款。核銷處理完成後，系統仍會重新確認此筆應付款已結清。
        </span>
      </div>

      <div className="finance-recon-deck">
        <div className="finance-recon-deck-grid">
          {/* 左側：銀行出款流水 */}
          <div className="finance-recon-col finance-recon-col-bank">
            <div className="finance-recon-col-header">
              <span className="finance-recon-badge-step">步驟 1</span>
              <h4>銀行已出款項（來源流水）</h4>
            </div>
            <div className="finance-table-container">
              <table className="finance-table finance-recon-table">
                <thead>
                  <tr>
                    <th>納入</th>
                    <th>銀行來源</th>
                    <th>流水編號</th>
                    <th>出款金額</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="is-selected-row">
                    <td>
                      <input type="checkbox" checked disabled readOnly aria-label="納入銀行款" />
                    </td>
                    <td>
                      <span>永豐銀行</span>
                      <small className="finance-mono-sub">永豐3131(虛擬)#3008</small>
                    </td>
                    <td>
                      <span className="finance-mono-sub">bank:3008</span>
                    </td>
                    <td><strong className="finance-paid">NT$ 19,485</strong></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div className="finance-recon-col-summary">
              <span>使用已選取的銀行流水（NT$ 19,485）。</span>
            </div>
          </div>

          {/* 中間箭頭 */}
          <div className="finance-recon-arrow-divider" aria-hidden="true">
            <span className="finance-recon-arrow-icon">➔</span>
            <small>沖抵核銷</small>
          </div>

          {/* 右側：月嫂應付款項 */}
          <div className="finance-recon-col finance-recon-col-target">
            <div className="finance-recon-col-header">
              <span className="finance-recon-badge-step">步驟 2</span>
              <h4>預計沖抵月嫂應付款（核銷目標）</h4>
            </div>
            <div className="finance-recon-obligations-list">
              <div className="finance-recon-obligation-item is-selected-item">
                <input type="checkbox" checked disabled readOnly aria-label="核銷款項 115000107" />
                <div className="finance-recon-ob-info">
                  <div className="finance-recon-ob-name">
                    <strong>案件 115000107 應付款</strong>
                    <small>到期日：2026-10-15 · 狀態 待付款</small>
                  </div>
                  <div className="finance-recon-ob-meta" style={{ display: 'grid', gap: 2, textAlign: 'right' }}>
                    <span>應付 NT$ 18,000</span>
                    <strong>餘額 NT$ 18,000</strong>
                  </div>
                </div>
              </div>
            </div>
            <div className="finance-recon-col-summary">
              <span>應付待付合計：<strong>NT$ 18,000</strong></span>
            </div>
          </div>
        </div>

        {/* 試算與決策條 */}
        <div className="finance-recon-calculation-bar">
          <div className="finance-recon-calc-metrics">
            <div>
              <small>銀行實付</small>
              <strong>NT$ 19,485</strong>
            </div>
            <span className="finance-recon-calc-operator">−</span>
            <div>
              <small>對應應付待付</small>
              <strong>NT$ 18,000</strong>
            </div>
            <span className="finance-recon-calc-operator">=</span>
            <div>
              <small>核銷方式</small>
              <strong className="finance-paid">{differenceMode === 'underpayment' ? '不足額核銷' : differenceMode === 'overpayment' ? '超額另列追收' : '足額核銷剩餘款'}</strong>
            </div>
          </div>

          <fieldset style={{ border: 0, padding: 0, margin: 0, display: 'grid', gap: 10 }}>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              <label style={{ flex: 1, minWidth: 200 }}>
                <span style={{ display: 'block', fontSize: '0.84rem', fontWeight: 600, marginBottom: 4 }}>核銷方式</span>
                <select
                  aria-label="核銷方式"
                  value={differenceMode}
                  onChange={(e) => setDifferenceMode(e.target.value)}
                  style={{ width: '100%', padding: '6px 10px', border: '1px solid #ebdcd1', borderRadius: 6 }}
                >
                  <option value="">足額核銷剩餘款</option>
                  <option value="underpayment">付款不足，先核銷實付</option>
                  <option value="overpayment">付款超額，另列追收</option>
                </select>
              </label>
              <label style={{ flex: 2, minWidth: 260 }}>
                <span style={{ display: 'block', fontSize: '0.84rem', fontWeight: 600, marginBottom: 4 }}>人工核對理由（選填）</span>
                <textarea
                  aria-label="人工核對理由"
                  maxLength={500}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="備註核對原因"
                  style={{ width: '100%', padding: '6px 10px', border: '1px solid #ebdcd1', borderRadius: 6, minHeight: '38px', resize: 'vertical' }}
                />
              </label>
            </div>
            <div className="finance-recon-action-row">
              <button type="button" className="finance-btn-primary finance-btn-lg">
                預覽核銷
              </button>
            </div>
          </fieldset>
        </div>
      </div>
    </section>
  );
}

// 狀況 3：客戶退款（無款項，統一後標準版，含完整後續處理入口，對照原截圖 3）
function ClientRefundEmptyPreview() {
  const [viewMode, setViewMode] = useState<'reconcile' | 'full_case'>('reconcile');
  const [supplemented, setSupplemented] = useState(false);
  const [showReassign, setShowReassign] = useState(false);
  const [reassignCaseNo, setReassignCaseNo] = useState('');
  const [reassignSuccess, setReassignSuccess] = useState(false);

  // 若使用者切換至「本案完整帳務檢視」
  if (viewMode === 'full_case') {
    return (
      <div className="finance-full-case-mock" style={{ animation: 'fadeIn 0.2s ease' }}>
        {/* 頂部返還提示橫幅 */}
        <div className="finance-reconciliation-return-banner">
          <div>
            <span className="finance-empty-badge" style={{ marginRight: '8px' }}>正在核對銀行流水</span>
            <span style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--md-sys-color-on-surface, #1e1b19)' }}>
              台新銀行 · 2026-10-15 · 序號:2 · <strong>NT$ 12,000</strong>（出款流水）
            </span>
          </div>
          <button
            type="button"
            className="finance-btn-action-primary"
            onClick={() => setViewMode('reconcile')}
          >
            返回對核交易
          </button>
        </div>

        {/* 案件精簡資訊 */}
        <div style={{ background: '#fff', padding: '16px 20px', borderRadius: '10px', border: '1px solid #ebdcd1', marginBottom: '16px' }}>
          <h3 style={{ margin: '0 0 8px 0', color: '#2d2621', fontSize: '1.05rem', fontWeight: 700 }}>115000088 · 吳佩倫 · 完整案件帳務</h3>
          <p style={{ margin: 0, color: '#7d7268', fontSize: '0.84rem' }}>身分：一般市民 ｜ 服務期間：2026-08-10 ~ 2026-08-30 ｜ 服務員：王秋菊</p>
        </div>

        {/* 帳務區塊 01：各期款項 */}
        <details className="finance-case-block" open style={{ background: '#fff', border: '1px solid #ebdcd1', borderRadius: '10px', marginBottom: '14px', padding: '16px' }}>
          <summary style={{ fontWeight: 700, cursor: 'pointer', color: '#2d2621', fontSize: '0.92rem' }}>01　各期款項明細</summary>
          <div style={{ marginTop: '12px' }}>
            <table className="finance-table" style={{ width: '100%', fontSize: '0.84rem' }}>
              <thead>
                <tr>
                  <th>款項名稱</th>
                  <th>應收金額</th>
                  <th>實收金額</th>
                  <th>餘額</th>
                  <th>狀態</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td><strong>訂金</strong></td>
                  <td>NT$ 6,000</td>
                  <td>NT$ 6,000</td>
                  <td>NT$ 0</td>
                  <td><span className="finance-paid">已繳清</span></td>
                </tr>
                <tr>
                  <td><strong>第一期款</strong></td>
                  <td>NT$ 18,000</td>
                  <td>NT$ 18,000</td>
                  <td>NT$ 0</td>
                  <td><span className="finance-paid">已繳清</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>

        {/* 帳務區塊 02：補助退款方案（核心入口） */}
        <details className="finance-case-block" open style={{ background: '#fff', border: '1px solid #ebdcd1', borderRadius: '10px', marginBottom: '14px', padding: '16px' }}>
          <summary style={{ fontWeight: 700, cursor: 'pointer', color: '#2d2621', fontSize: '0.92rem' }}>02　補助退款方案（退款依據設定）</summary>
          <div style={{ marginTop: '12px', background: '#fdfaf7', padding: '16px', borderRadius: '8px', border: '1px solid #f2e8e1' }}>
            <p style={{ margin: '0 0 8px 0', fontSize: '0.85rem', color: '#4a3f37' }}>
              本案政府補助額：<strong>NT$ 12,000</strong> ｜ 目前方案狀態：<strong style={{ color: '#c2410c' }}>尚未設定方案</strong>
            </p>
            <p style={{ margin: '0 0 14px 0', fontSize: '0.82rem', color: '#7d7268', lineHeight: 1.6 }}>
              若工會出款 12,000 是因政府補助已撥入而退給客戶，請設定為<strong>「方案二：客戶先墊後退」</strong>。設定後系統將自動產生待退款項以供核銷。
            </p>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                type="button"
                className="finance-btn-action-primary"
                onClick={() => {
                  setSupplemented(true);
                  setViewMode('reconcile');
                }}
              >
                設為方案二（客戶先墊後退）並回對核抽屜
              </button>
            </div>
          </div>
        </details>

        {/* 帳務區塊 03：手動補登款項 */}
        <details className="finance-case-block" open style={{ background: '#fff', border: '1px solid #ebdcd1', borderRadius: '10px', padding: '16px' }}>
          <summary style={{ fontWeight: 700, cursor: 'pointer', color: '#2d2621', fontSize: '0.92rem' }}>03　手動補登款項（離線退款協議）</summary>
          <div style={{ marginTop: '12px' }}>
            <p style={{ margin: '0 0 12px 0', fontSize: '0.84rem', color: '#6b5f54', lineHeight: 1.6 }}>
              若此退款為特殊個案折讓、解約離線協議退款，可直接手動補登應退款項：
            </p>
            <button
              type="button"
              className="finance-btn-action-secondary"
              onClick={() => {
                setSupplemented(true);
                setViewMode('reconcile');
              }}
            >
              手動補登「解約協議退款 NT$ 12,000」並返回核對
            </button>
          </div>
        </details>
      </div>
    );
  }

  // 正常核對畫面（已融入完整處置入口）
  const bankTotal = 12000;
  const dueTotal = supplemented ? 12000 : 0;
  const diff = bankTotal - dueTotal;

  return (
    <section className="case-accounting-card finance-advanced-reconciliation-card" aria-label="客戶退款核銷">
      <div className="finance-section-heading">
        <div className="finance-reconciliation-heading-group">
          <h3>待沖銷銀行退款與案件待退款對核</h3>
          <span className="finance-tag-imported">客戶退款沖銷</span>
        </div>
      </div>

      <div className="finance-advanced-reconciliation-guide">
        <strong>作用說明：</strong>銀行對帳單已辨識到本案的退款流水（如下左側）。請確認要將此筆款項<strong>沖抵哪一項待退款項</strong>（如下右側）。核對確認後，系統將正式記錄實退並更新退款狀態。
      </div>

      <div className="finance-recon-deck">
        <div className="finance-recon-deck-grid">
          {/* 左側：銀行退款出款 */}
          <div className="finance-recon-col finance-recon-col-bank">
            <div className="finance-recon-col-header">
              <span className="finance-recon-badge-step">步驟 1</span>
              <h4>銀行已退款項（來源流水）</h4>
            </div>
            <div className="finance-table-container">
              <table className="finance-table finance-recon-table">
                <thead>
                  <tr>
                    <th>納入</th>
                    <th>退款日期</th>
                    <th>銀行來源</th>
                    <th>退款金額</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="is-selected-row">
                    <td>
                      <input type="checkbox" checked disabled readOnly aria-label="納入銀行退款 102" />
                    </td>
                    <td><strong>2026-10-15</strong></td>
                    <td>
                      <span>台新銀行</span>
                      <small className="finance-mono-sub">2</small>
                    </td>
                    <td><strong className="finance-paid">NT$ 12,000</strong></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div className="finance-recon-col-summary">
              <span>已勾選退款合計：<strong>NT$ 12,000</strong>（共 1 筆）</span>
            </div>
          </div>

          {/* 中間箭頭 */}
          <div className="finance-recon-arrow-divider" aria-hidden="true">
            <span className="finance-recon-arrow-icon">➔</span>
            <small>沖抵核銷</small>
          </div>

          {/* 右側：案件待退款項 */}
          <div className="finance-recon-col finance-recon-col-target">
            <div className="finance-recon-col-header">
              <span className="finance-recon-badge-step">步驟 2</span>
              <h4>預計沖抵待退款項（核銷目標）</h4>
            </div>

            {!supplemented ? (
              /* 空狀態：顯示警示與美化後的處置按鈕 */
              <div className="finance-reconciliation-empty-box">
                <div className="finance-empty-header">
                  <span className="finance-empty-badge">無可沖銷款項</span>
                  <h5 className="finance-empty-title">本案目前沒有可選待退款項</h5>
                </div>
                <p className="finance-empty-desc">
                  原銀行流水已帶入（台新銀行 NT$ 12,000），但本案帳務尚未建立待退款或補助退款義務。請先至案件帳務確認正式款項資料後，再進行核對。
                </p>
                <div className="finance-empty-action-group">
                  <button
                    type="button"
                    className="finance-btn-action-primary"
                    onClick={() => setViewMode('full_case')}
                  >
                    查看本案帳務（設定方案／補登款項）
                  </button>
                  <button
                    type="button"
                    className="finance-btn-action-secondary"
                    onClick={() => setShowReassign((prev) => !prev)}
                  >
                    {showReassign ? '收合更正表單' : '更正款項用途／重新歸屬'}
                  </button>
                  <button
                    type="button"
                    className="finance-btn-action-secondary"
                    style={{ borderStyle: 'dashed', color: '#74593f' }}
                    onClick={() => setSupplemented(true)}
                  >
                    [測試展示] 模擬補登退款 NT$ 12,000
                  </button>
                </div>
              </div>
            ) : (
              /* 補登後狀態：出現已建立款項 */
              <div className="finance-recon-obligations-list">
                <label
                  className="finance-recon-obligation-item is-selected-item"
                  style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', padding: '12px', border: '2px solid var(--md-sys-color-primary, #c2410c)', borderRadius: '8px', background: '#fff' }}
                >
                  <input
                    type="checkbox"
                    checked
                    readOnly
                    aria-label="核銷款項 client-refund:115000088:mock"
                  />
                  <div className="finance-recon-ob-info" style={{ marginLeft: '10px', flex: 1 }}>
                    <div className="finance-recon-ob-name" style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <strong>補助退款方案二 / 協議應退款</strong>
                      <span className="finance-tag-imported" style={{ fontSize: '0.72rem', background: '#dcfce7', color: '#166534', padding: '2px 6px', borderRadius: '4px', fontWeight: 700 }}>剛建立</span>
                    </div>
                    <small style={{ color: '#7d7268' }}>到期日：2026-10-15</small>
                    <div className="finance-recon-ob-meta" style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px' }}>
                      <span>待退 <strong>NT$ 12,000</strong></span>
                      <small className="finance-mono-sub">client-refund:115000088:manual</small>
                    </div>
                  </div>
                </label>
                <div style={{ marginTop: '8px', textAlign: 'right' }}>
                  <button
                    type="button"
                    className="finance-btn-link"
                    style={{ fontSize: '0.8rem', color: '#7d7268', textDecoration: 'underline' }}
                    onClick={() => setSupplemented(false)}
                  >
                    [重置為無款項狀態]
                  </button>
                </div>
              </div>
            )}

            <div className="finance-recon-col-summary">
              <span>已勾選待退款：<strong>NT$ {dueTotal.toLocaleString()}</strong>（共 {supplemented ? 1 : 0} 項）</span>
            </div>
          </div>
        </div>

        {/* 試算與決策條 */}
        <div className="finance-recon-calculation-bar">
          <div className="finance-recon-calc-metrics">
            <div>
              <small>勾選銀行實退</small>
              <strong>NT$ 12,000</strong>
            </div>
            <span className="finance-recon-calc-operator">−</span>
            <div>
              <small>對應待退款項</small>
              <strong>NT$ {dueTotal.toLocaleString()}</strong>
            </div>
            <span className="finance-recon-calc-operator">=</span>
            <div>
              <small>沖銷差額</small>
              <strong className={supplemented ? 'finance-paid' : ''} style={{ color: supplemented ? '#16a34a' : '#888' }}>
                {supplemented ? (diff === 0 ? '金額相符' : `差額 NT$ ${diff.toLocaleString()}`) : '尚未核對'}
              </strong>
            </div>
          </div>

          <div className="finance-recon-calc-explanation">
            {!supplemented ? (
              <span>本案尚未建立待沖銷款項；請由上方按鈕前往本案帳務確認補助退款方案或補登，或更正流水用途。</span>
            ) : (
              <span style={{ color: '#16a34a', fontWeight: 600 }}>退款金額與本次選取款項相符；請在下方檢查核銷影響並確認核銷。</span>
            )}
          </div>

          {supplemented && (
            <div className="finance-recon-action-row" style={{ marginTop: '14px' }}>
              <button
                type="button"
                className="finance-btn-action-primary"
                style={{ padding: '10px 24px', fontSize: '0.9rem' }}
                onClick={() => alert('已模擬成功提交退款核銷！實退 NT$ 12,000 已沖銷完成。')}
              >
                確認核銷本案退款（NT$ 12,000）
              </button>
            </div>
          )}
        </div>

        {/* 無款項時顯示美化後的合規處置指引面板 */}
        {!supplemented && (
          <div className="finance-recon-action-guidance">
            <h5>異常處置與業務指引</h5>
            <ul className="finance-recon-guidance-list">
              <li>
                <strong>本案確有退款但尚未建立款項：</strong>
                請點擊「查看本案帳務」，確認【02 補助退款方案】是否已選定為「方案二（客戶先墊後退）」或執行【手動補登款項】。設定完成後返回此抽屜即可核對。
              </li>
              <li>
                <strong>銀行出款非本案退款（流水誤判）：</strong>
                請點擊「更正款項用途／重新歸屬」，重新指定受款案件或將用途變更為月嫂薪資、整期補助退款等其他款項性質。
              </li>
            </ul>

            <div className="finance-empty-action-group">
              <button
                type="button"
                className="finance-btn-action-primary"
                onClick={() => setViewMode('full_case')}
              >
                查看本案帳務
              </button>
              <button
                type="button"
                className="finance-btn-action-secondary"
                onClick={() => setShowReassign((prev) => !prev)}
              >
                {showReassign ? '收合更正表單' : '更正款項用途／重新歸屬'}
              </button>
            </div>

            {/* 展開之更正表單 */}
            {showReassign && (
              <div
                style={{
                  marginTop: '16px',
                  paddingTop: '16px',
                  borderTop: '1px solid #ebdcd1',
                  background: '#fdfaf7',
                  padding: '16px',
                  borderRadius: '8px'
                }}
              >
                <h5 style={{ margin: '0 0 10px 0', color: '#2d2621', fontSize: '0.88rem', fontWeight: 700 }}>更正銀行流水歸屬或款項用途</h5>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', marginBottom: '12px' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#7d7268', marginBottom: '4px' }}>款項用途</label>
                    <select className="finance-select" defaultValue="client_refund" style={{ width: '100%', padding: '6px' }}>
                      <option value="client_refund">客戶退款（重新指定案件）</option>
                      <option value="staff_payout">月嫂薪資出款</option>
                      <option value="government_subsidy">政府整期退款</option>
                      <option value="other">其他費用支出</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#7d7268', marginBottom: '4px' }}>重新指定受款案件編號</label>
                    <input
                      type="text"
                      className="finance-input"
                      placeholder="輸入其他案件編號，例如 115000103"
                      value={reassignCaseNo}
                      onChange={(e) => setReassignCaseNo(e.target.value)}
                      style={{ width: '100%', padding: '6px' }}
                    />
                  </div>
                </div>
                <button
                  type="button"
                  className="finance-btn-action-primary"
                  onClick={() => {
                    setReassignSuccess(true);
                    setTimeout(() => setReassignSuccess(false), 3000);
                  }}
                >
                  確認更正歸屬
                </button>
                {reassignSuccess && (
                  <span style={{ marginLeft: '12px', color: '#166534', fontWeight: 600, fontSize: '0.84rem' }}>
                    已成功模擬更正為新案件歸屬！
                  </span>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function ClientRefundActivePreview() {
  const [selectedIds, setSelectedIds] = useState<string[]>(['deposit-refund']);
  const bankTotal = 12000;
  const dueTotal = selectedIds.includes('deposit-refund') ? 12000 : 0;
  const diff = bankTotal - dueTotal;

  return (
    <section className="case-accounting-card finance-advanced-reconciliation-card" aria-label="客戶退款核銷">
      <div className="finance-section-heading">
        <div className="finance-reconciliation-heading-group">
          <h3>待沖銷銀行退款與案件待退款對核</h3>
          <span className="finance-tag-imported">客戶退款沖銷</span>
        </div>
      </div>

      <div className="finance-advanced-reconciliation-guide">
        <strong>💡 作用說明：</strong>銀行對帳單已辨識到本案的退款流水（如下左側）。請確認要將此筆款項<strong>沖抵哪一項待退款項</strong>（如下右側）。核對確認後，系統將正式記錄實退並更新退款狀態。
      </div>

      <div className="finance-recon-deck">
        <div className="finance-recon-deck-grid">
          {/* 左側：銀行退款流水 */}
          <div className="finance-recon-col finance-recon-col-bank">
            <div className="finance-recon-col-header">
              <span className="finance-recon-badge-step">步驟 1</span>
              <h4>銀行已退款項（來源流水）</h4>
            </div>
            <div className="finance-table-container">
              <table className="finance-table finance-recon-table">
                <thead>
                  <tr>
                    <th>納入</th>
                    <th>退款日期</th>
                    <th>銀行來源</th>
                    <th>退款金額</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="is-selected-row">
                    <td>
                      <input type="checkbox" checked disabled readOnly aria-label="納入銀行退款 103" />
                    </td>
                    <td><strong>2026-10-18</strong></td>
                    <td>
                      <span>台新銀行</span>
                      <small className="finance-mono-sub">3</small>
                    </td>
                    <td><strong className="finance-paid">NT$ 12,000</strong></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div className="finance-recon-col-summary">
              <span>已勾選退款合計：<strong>NT$ 12,000</strong>（共 1 筆）</span>
            </div>
          </div>

          {/* 中間箭頭 */}
          <div className="finance-recon-arrow-divider" aria-hidden="true">
            <span className="finance-recon-arrow-icon">➔</span>
            <small>沖抵核銷</small>
          </div>

          {/* 右側：案件待退款項 - 待選列表 */}
          <div className="finance-recon-col finance-recon-col-target">
            <div className="finance-recon-col-header">
              <span className="finance-recon-badge-step">步驟 2</span>
              <h4>預計沖抵待退款項（核銷目標）</h4>
            </div>
            <div className="finance-recon-obligations-list">
              <label className={`finance-recon-obligation-item ${selectedIds.includes('deposit-refund') ? 'is-selected-item' : ''}`} style={{ cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={selectedIds.includes('deposit-refund')}
                  onChange={(e) => setSelectedIds(e.target.checked ? [...selectedIds, 'deposit-refund'] : selectedIds.filter(id => id !== 'deposit-refund'))}
                />
                <div className="finance-recon-ob-info">
                  <div className="finance-recon-ob-name">
                    <strong>退訂金餘額</strong>
                    <small>到期日：2026-10-18</small>
                  </div>
                  <div className="finance-recon-ob-meta">
                    <span>待退 <strong>NT$ 12,000</strong></span>
                    <small className="finance-mono-sub">client-refund:115000099:deposit</small>
                  </div>
                </div>
              </label>
            </div>
            <div className="finance-recon-col-summary">
              <span>已勾選待退款：<strong>NT$ {dueTotal.toLocaleString()}</strong>（共 {selectedIds.length} 項）</span>
            </div>
          </div>
        </div>

        {/* 試算與決策條 */}
        <div className="finance-recon-calculation-bar">
          <div className="finance-recon-calc-metrics">
            <div>
              <small>勾選銀行實退</small>
              <strong>NT$ {bankTotal.toLocaleString()}</strong>
            </div>
            <span className="finance-recon-calc-operator">−</span>
            <div>
              <small>對應待退款項</small>
              <strong>NT$ {dueTotal.toLocaleString()}</strong>
            </div>
            <span className="finance-recon-calc-operator">=</span>
            <div>
              <small>沖銷差額</small>
              <strong className={diff === 0 ? 'finance-paid' : 'finance-diff-under'}>
                {diff === 0 ? '金額相符' : `差額 NT$ ${diff.toLocaleString()}`}
              </strong>
            </div>
          </div>

          <div className="finance-recon-calc-explanation">
            {diff === 0 ? (
              <span>退款金額與本次選取款項相符；請在下方檢查核銷影響並確認核銷。</span>
            ) : (
              <span>請勾選要核銷的待退款項。</span>
            )}
          </div>

          <div className="finance-recon-action-row">
            <button type="button" className="finance-btn-primary finance-btn-lg" disabled={!selectedIds.length}>
              預覽退款核銷
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

// 狀況 5：客戶退匯（統一後標準版）
function ClientRefundReturnPreview() {
  const [selected, setSelected] = useState('51');

  return (
    <section className="case-accounting-card finance-advanced-reconciliation-card" aria-label="客戶退匯核對">
      <div className="finance-section-heading">
        <div className="finance-reconciliation-heading-group">
          <h3>待沖銷銀行退匯與原客戶退款對核</h3>
          <span className="finance-tag-imported">客戶退匯沖正</span>
        </div>
        <button type="button" className="finance-btn-secondary">重新查詢原退款</button>
      </div>

      <div className="finance-advanced-reconciliation-guide">
        <strong>💡 作用說明：</strong>銀行對帳單已辨識到本案的退匯入款流水（如下左側）。請選擇對應的原退款紀錄（如下右側）。核銷確認後，系統將正式沖正該筆退款並重開原退款應付款項。
      </div>

      <div className="finance-recon-deck">
        <div className="finance-recon-deck-grid">
          {/* 左側：銀行退匯入款 */}
          <div className="finance-recon-col finance-recon-col-bank">
            <div className="finance-recon-col-header">
              <span className="finance-recon-badge-step">步驟 1</span>
              <h4>銀行退匯款項（來源流水）</h4>
            </div>
            <div className="finance-table-container">
              <table className="finance-table finance-recon-table">
                <thead>
                  <tr>
                    <th>納入</th>
                    <th>銀行來源</th>
                    <th>流水編號</th>
                    <th>退匯金額</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="is-selected-row">
                    <td>
                      <input type="checkbox" checked disabled readOnly aria-label="納入銀行款" />
                    </td>
                    <td>
                      <span>台新銀行退匯入款</span>
                    </td>
                    <td>
                      <small className="finance-mono-sub">bank:2088</small>
                    </td>
                    <td><strong className="finance-paid">NT$ 15,000</strong></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div className="finance-recon-col-summary">
              <span>使用已辨識之銀行退匯流水（NT$ 15,000）。</span>
            </div>
          </div>

          {/* 中間箭頭 */}
          <div className="finance-recon-arrow-divider" aria-hidden="true">
            <span className="finance-recon-arrow-icon">➔</span>
            <small>沖抵沖正</small>
          </div>

          {/* 右側：原退款紀錄 */}
          <div className="finance-recon-col finance-recon-col-target">
            <div className="finance-recon-col-header">
              <span className="finance-recon-badge-step">步驟 2</span>
              <h4>原客戶退款紀錄（核銷目標）</h4>
            </div>

            <label style={{ display: 'grid', gap: 4, marginBottom: 12 }}>
              <span style={{ fontSize: '0.84rem', fontWeight: 600 }}>原退款下拉選單</span>
              <select
                aria-label="原退款"
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                style={{ padding: '6px 10px', border: '1px solid #ebdcd1', borderRadius: 6 }}
              >
                <option value="51">退款 1 · 2026-10-01 · NT$ 15,000</option>
              </select>
            </label>

            <div className="finance-recon-obligations-list">
              <label className="finance-recon-obligation-item is-selected-item" style={{ cursor: 'pointer' }}>
                <input type="radio" checked readOnly aria-label="原退款 1" />
                <div className="finance-recon-ob-info">
                  <div className="finance-recon-ob-name">
                    <strong>退款紀錄 #1</strong>
                    <small>退款日：2026-10-01</small>
                  </div>
                  <div className="finance-recon-ob-meta">
                    <span>原退款金額 <strong>NT$ 15,000</strong></span>
                  </div>
                </div>
              </label>
            </div>
            <div className="finance-recon-col-summary">
              <span>已選取原退款：<strong>NT$ 15,000</strong></span>
            </div>
          </div>
        </div>

        {/* 試算與決策條 */}
        <div className="finance-recon-calculation-bar">
          <div className="finance-recon-calc-metrics">
            <div>
              <small>銀行退匯流水</small>
              <strong>bank:2088</strong>
            </div>
            <span className="finance-recon-calc-operator">➔</span>
            <div>
              <small>對應原退款金額</small>
              <strong>NT$ 15,000</strong>
            </div>
            <span className="finance-recon-calc-operator">=</span>
            <div>
              <small>沖銷結果</small>
              <strong className="finance-paid">金額相符（沖正重開）</strong>
            </div>
          </div>

          <div className="finance-recon-calc-explanation">
            <span>已選取原退款。點擊預覽確認後，將依正式規則沖正原退款並重新開立對應退款應付款項。</span>
          </div>

          <div className="finance-recon-action-row">
            <button type="button" className="finance-btn-primary finance-btn-lg">
              預覽退匯核銷
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

// 主預覽頁面
function PreviewApp() {
  const hashTab = window.location.hash.replace('#', '') as 'receipt' | 'staff' | 'refund-empty' | 'refund-active' | 'refund-return';
  const validTabs = ['receipt', 'staff', 'refund-empty', 'refund-active', 'refund-return'];
  const [activeTab, setActiveTab] = useState<'receipt' | 'staff' | 'refund-empty' | 'refund-active' | 'refund-return'>(validTabs.includes(hashTab) ? hashTab : 'staff');

  const setTab = (tab: typeof activeTab) => {
    setActiveTab(tab);
    window.location.hash = `#${tab}`;
  };

  const cases = {
    receipt: {
      caseNo: '115000103',
      name: '柯雅玲',
      title: '客戶繳款 · 核對交易',
      sub: '永豐 · 2026-10-20 · 永豐3131(虛擬)#3022 · NT$ 12,000',
      badge: '狀況一：客戶入款對核（標準版範本，如截圖 2）',
      component: <ClientReceiptReconciliationPreview />
    },
    staff: {
      caseNo: '115000107',
      name: '蘇家妤',
      title: '月嫂薪資 · 核對交易',
      sub: '永豐 · 2026-10-15 · 永豐3131(虛擬)#3008 · NT$ 19,485',
      badge: '狀況二：月嫂薪資對核（統一標準版，對照原截圖 1）',
      component: <StaffPayoutReconciliationPreview />
    },
    'refund-empty': {
      caseNo: '115000088',
      name: '吳佩倫',
      title: '客戶退款 · 核對交易',
      sub: '台新 · 2026-10-15 · 2 · NT$ 12,000',
      badge: '狀況三：客戶退款對核 - 無待退款項（統一標準版，對照原截圖 3）',
      component: <ClientRefundEmptyPreview />
    },
    'refund-active': {
      caseNo: '115000099',
      name: '林美惠',
      title: '客戶退款 · 核對交易',
      sub: '台新 · 2026-10-18 · 3 · NT$ 12,000',
      badge: '狀況四：客戶退款對核 - 有可選款項（統一標準版）',
      component: <ClientRefundActivePreview />
    },
    'refund-return': {
      caseNo: '115000055',
      name: '陳淑華',
      title: '客戶退匯 · 核對交易',
      sub: '台新 · 2026-10-15 · bank:2088 · NT$ 15,000',
      badge: '狀況五：客戶退匯對核（統一標準版）',
      component: <ClientRefundReturnPreview />
    }
  };

  const current = cases[activeTab];

  return (
    <div style={{ padding: '24px', maxWidth: '1280px', margin: '0 auto' }}>
      <header style={{ marginBottom: '20px', background: '#fff', padding: '16px 20px', borderRadius: '12px', border: '1px solid #ebdcd1', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
        <h2 style={{ margin: '0 0 8px 0', color: '#2d2621' }}>核對交易抽屜頁面 · 全部狀態統一標準版展示驗證</h2>
        <p style={{ margin: 0, color: '#7d7268', fontSize: '0.9rem' }}>
          驗證依據：所有待核對狀態均統一為「步驟 1 銀行流水 ➔ 沖抵核銷 ➔ 步驟 2 目標款項 ＋ 下方差額決策條」標準雙欄對核版型。
        </p>

        {/* 狀態切換導覽 */}
        <div style={{ display: 'flex', gap: '8px', marginTop: '16px', flexWrap: 'wrap' }}>
          {(Object.keys(cases) as Array<keyof typeof cases>).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              style={{
                padding: '8px 14px',
                borderRadius: '8px',
                border: '1px solid',
                borderColor: activeTab === key ? '#c25e2e' : '#dec0b6',
                background: activeTab === key ? '#c25e2e' : '#fff',
                color: activeTab === key ? '#fff' : '#4a3f37',
                fontWeight: activeTab === key ? 700 : 500,
                cursor: 'pointer',
                fontSize: '0.85rem',
                transition: 'all 0.15s ease'
              }}
            >
              {cases[key].badge}
            </button>
          ))}
        </div>
      </header>

      {/* 模擬 Drawer 外框 */}
      <div
        className="drawer-container drawer-open"
        style={{
          background: '#fff',
          borderRadius: '12px',
          border: '1px solid #ebdcd1',
          boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
          overflow: 'hidden'
        }}
      >
        {/* Drawer 頁首 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 24px', borderBottom: '1px solid #f2e8e1', background: '#fff' }}>
          <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 800, color: '#2d2621' }}>
            {current.caseNo} · {current.name}
          </h2>
          <span style={{ fontSize: '0.85rem', color: '#c25e2e', background: '#ffeedb', padding: '3px 10px', borderRadius: '6px', fontWeight: 700 }}>
            {current.badge.split('（')[0]}
          </span>
        </div>

        {/* 抽屜內部畫面 */}
        <div style={{ padding: '24px' }}>
          <header style={{ marginBottom: '16px' }}>
            <h3 style={{ margin: '0 0 4px 0', fontSize: '1.1rem', fontWeight: 700, color: '#2d2621' }}>{current.title}</h3>
            <p style={{ margin: 0, color: '#7d7268', fontSize: '0.9rem' }}>{current.sub}</p>
          </header>

          {current.component}
        </div>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(<PreviewApp />);
