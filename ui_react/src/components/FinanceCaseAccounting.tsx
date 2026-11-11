/**
 * File: FinanceCaseAccounting.tsx
 * Description: 案件帳務精簡抽屜與警示清單，提供各期核銷、補助方案、銀行對帳虛擬帳號與退款帳戶核對。
 */
import { CancellationSettlementAccounting } from './CancellationSettlementAccounting';
import { OrderTermsMutationPanel } from './OrderTermsMutationPanel';
import { CasePricingAdjustmentPanel } from './CasePricingAdjustmentPanel';
import { financeImportQueryClient } from '../api/finance_import/finance_import_query_client';
import { subscribeCaseAccountingChanges } from '../api/shared/case_accounting_changes';
import { ClientRefundReturnReconciliationPanel } from './ClientRefundReturnReconciliationPanel';
import {useCallback,useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {financeAccountingClient,type CaseAccounting,type AccountingWarning} from '../api/finance_import/finance_accounting_client';
import {paymentOverdueReminderClient,type CasePaymentReminder} from '../api/line_order_groups/payment_overdue_reminder_client';
import {ordersQueryClient} from '../api/orders/order_query_client';
import type {OrderDetail} from '../api/orders/order_query_schemas';
import {clientRegistryClient} from '../api/client_registry/client_registry_client';
import type {ClientRegistryDetail} from '../api/client_registry/client_registry_schemas';
import {caseVirtualAccountClient,type CaseVirtualAccountView} from '../api/client_finance/case_virtual_account_client';
import {financeMoney} from './FinanceReceiptsWorkspace';
import {useUnsavedChanges,useUnsavedNavigation} from './UnsavedChanges';
import {ApiHttpError} from '../api/shared/typed_errors';
import {FinanceSubsidyPlanForm,FinanceCaseBankMemos,subsidyPlanLabels,subsidyPlanTargets} from './FinanceSubsidyPlanForm';
import {FinanceCaseNotice,lastNotification,notificationTime,notificationStatus} from './FinanceCaseNotice';
import {CaseManualSupplementWorkbench} from './CaseManualSupplementWorkbench';
import { HistoricalPayableLookup } from './HistoricalPayableReview';
import type { HistoricalPayableAuditItem } from '../api/accounts_payable/accounts_payable_query_schemas';
import type { FinanceBankTransaction } from '../api/finance_import/finance_import_query_schemas';
import { ClientReceiptReconciliationPanel } from './ClientReceiptReconciliationPanel';
import { StaffPayoutRemediationWorkbench } from './StaffPayoutRemediationWorkbench';
import { FinanceImportCorrectionForm } from './FinanceImportCorrectionForm';
import { AccountingParametersCard } from './AccountingParametersCard';
import { AccountingParametersBar } from './AccountingParametersBar';
import { AccountingParametersDrawer } from './AccountingParametersDrawer';
import { accountingPricingClient, type CasePricing } from '../api/client_finance/accounting_pricing_client';
import './FinanceCaseAccounting.css';
import './FinanceCompactCase.css';

const TAIWAN_BANKS: Record<string, string> = {
  '004': '臺灣銀行', '005': '土地銀行', '006': '合作金庫', '007': '第一銀行', '008': '華南銀行', '009': '彰化銀行',
  '011': '上海商銀', '012': '台北富邦', '013': '國泰世華', '016': '高雄銀行', '017': '兆豐銀行', '050': '臺灣企銀',
  '052': '渣打銀行', '053': '台中銀行', '054': '京城銀行', '102': '華泰銀行', '103': '新光銀行', '108': '陽信銀行',
  '147': '三信商銀', '700': '中華郵政', '803': '聯邦銀行', '805': '遠東銀行', '806': '元大銀行', '807': '永豐銀行',
  '808': '玉山銀行', '809': '凱基銀行', '810': '星展銀行', '812': '台新銀行', '816': '安泰銀行', '822': '中國信託',
};

export function formatBankDisplay(code: string | null | undefined): string {
  if (!code) return '';
  const trimmed = code.trim();
  if (trimmed.length < 3) return trimmed;
  const head = trimmed.slice(0, 3);
  const branch = trimmed.length > 3 ? trimmed.slice(3) : '';
  const bankName = TAIWAN_BANKS[head];
  if (!bankName) return branch ? `${head}（分行 ${branch}）` : head;
  return branch ? `${head} ${bankName}（分行 ${branch}）` : `${head} ${bankName}`;
}

export function buildDefaultVirtualAccount(caseNo: string): string | null {
  if (!caseNo) return null;
  const match = caseNo.match(/^A?(\d{3})(\d{3,6})$/);
  if (!match) return null;
  const prefix = '99781699';
  const year = match[1];
  const rawSeq = parseInt(match[2], 10);
  if (isNaN(rawSeq)) return null;
  const accountSeq = caseNo.startsWith('A') ? rawSeq + 500 : rawSeq;
  if (accountSeq < 1 || accountSeq > 999) return null;
  return `${prefix}${year}${String(accountSeq).padStart(3, '0')}`;
}

const labels={over_received:'客戶超收',over_paid:'付款超付',under_paid:'付款差額超過 100 元'};
const money=(value:number|bigint|null|undefined)=>value==null?'待確認':financeMoney(value);
type Stage='deposit'|'first'|'second';
const stageNames:Record<Stage,string>={deposit:'訂金',first:'第一期',second:'第二期'};
const stages:Stage[]=['deposit','first','second'];
export function AccountingWarningList({ data, onChange }: { data: CaseAccounting; onChange: (data: CaseAccounting) => void }) {
  const [showDismissed, setShowDismissed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useUnsavedChanges('帳務警示解除', [], { busy });
  async function dismiss(row: AccountingWarning) {
    setBusy(true); setError('');
    try { onChange(await financeAccountingClient.dismiss(data.case_no, row)); }
    catch { setError('解除失敗或款項已變更，請重新整理後確認。'); }
    finally { setBusy(false); }
  }
  return <section className="case-accounting-card" aria-label="共用帳務警示">
    <div className="finance-section-heading"><h3>帳務警示 · 待檢查 {data.pending_warning_count}</h3><label><input type="checkbox" checked={showDismissed} onChange={event => setShowDismissed(event.target.checked)} /> 顯示已解除</label></div>
    {error && <p role="alert">{error}</p>}
    {data.warnings.filter(row => showDismissed || !row.dismissed).map(row => <div className="case-accounting-warning" key={`${row.item_identity}:${row.kind}:${row.difference_ntd}`}>
      <div><strong>{labels[row.kind]}</strong><p>{[...data.client_items, ...data.staff_items].find(item => item.identity === row.item_identity)?.label} · {[...data.client_items, ...data.staff_items].find(item => item.identity === row.item_identity)?.party} · 應收／應付 {money(row.expected_ntd)}，實收／實付 {money(row.actual_ntd)}；差額 {money(row.difference_ntd)}</p></div>
      {row.dismissed ? <span>已解除 · {row.dismissed_by} · {row.dismissed_at}</span> : <button className="finance-btn-secondary" disabled={busy} type="button" onClick={() => void dismiss(row)}>解除警示</button>}
    </div>)}
    {!data.warnings.some(row => showDismissed || !row.dismissed) && <p className="finance-state">目前沒有{showDismissed ? '' : '待檢查'}帳務警示。</p>}
  </section>;
}

function CaseRefundReconciliation({
  row,
  data,
  obligations,
  selectedIds,
  onSelectionChange,
  initialKind,
  onPosted,
  reportBusy,
  selectionBusy,
  onViewCase,
}: {
  row: FinanceBankTransaction;
  data: CaseAccounting;
  obligations: CaseAccounting['client_items'];
  selectedIds: string[];
  onSelectionChange: (updater: (prev: string[]) => string[]) => void;
  initialKind: 'client_subsidy_return' | 'client_refund';
  onPosted: () => void;
  reportBusy: (busy: boolean) => void;
  selectionBusy: boolean;
  onViewCase?: () => void;
}) {
  const [showReassign, setShowReassign] = useState(false);
  const bankTotal = row.amount_ntd;
  const dueTotal = obligations.filter(item => selectedIds.includes(item.identity)).reduce((sum, item) => sum + Number(item.remaining_ntd ?? 0), 0);
  const diff = bankTotal - dueTotal;

  return (
    <div className="case-accounting-card finance-advanced-reconciliation-card" aria-label="客戶退款核銷">
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
                      <input type="checkbox" checked disabled readOnly aria-label={`納入銀行退款 ${row.row_id}`} />
                    </td>
                    <td><strong>{row.transaction_date ?? '日期未提供'}</strong></td>
                    <td>
                      <span>{row.bank === 'sinopac' ? '永豐銀行' : row.bank === 'taishin' ? '台新銀行' : '銀行出款'}</span>
                      <small className="finance-mono-sub">{row.reference}</small>
                    </td>
                    <td><strong className="finance-paid">{money(row.amount_ntd)}</strong></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div className="finance-recon-col-summary">
              <span>已勾選退款合計：<strong>{money(row.amount_ntd)}</strong>（共 1 筆）</span>
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
            {!obligations.length ? (
              <div className="finance-reconciliation-empty-box">
                <div className="finance-empty-header">
                  <span className="finance-empty-badge">無可沖銷款項</span>
                  <h5 className="finance-empty-title">本案目前沒有可選待退款項</h5>
                </div>
                <p className="finance-empty-desc">
                  原銀行流水已帶入（{row.bank === 'sinopac' ? '永豐銀行' : '台新銀行'} {money(row.amount_ntd)}），但本案帳務尚未建立待退款或補助退款義務。請先至案件帳務確認正式款項資料後，再進行核對。
                </p>
                {onViewCase && (
                  <div className="finance-empty-action-group">
                    <button
                      type="button"
                      className="finance-btn-action-primary"
                      onClick={onViewCase}
                      disabled={selectionBusy}
                    >
                      查看本案帳務（設定方案／補登款項）
                    </button>
                    <button
                      type="button"
                      className="finance-btn-action-secondary"
                      onClick={() => setShowReassign((prev) => !prev)}
                      disabled={selectionBusy}
                    >
                      {showReassign ? '收合更正表單' : '更正款項用途／重新歸屬'}
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="finance-recon-obligations-list">
                {obligations.map((item) => {
                  const isChecked = selectedIds.includes(item.identity);
                  return (
                    <label
                      key={item.identity}
                      className={`finance-recon-obligation-item ${isChecked ? 'is-selected-item' : ''}`}
                      style={{ cursor: 'pointer' }}
                    >
                      <input
                        type="checkbox"
                        aria-label={`核銷款項 ${item.identity}`}
                        checked={isChecked}
                        disabled={selectionBusy}
                        onChange={() => onSelectionChange((ids) => ids.includes(item.identity) ? ids.filter((id) => id !== item.identity) : [...ids, item.identity])}
                      />
                      <div className="finance-recon-ob-info">
                        <div className="finance-recon-ob-name">
                          <strong>{item.label || '應退款項'}</strong>
                          <small>{item.due_date ? `到期日：${item.due_date}` : '未提供到期日'}</small>
                        </div>
                        <div className="finance-recon-ob-meta">
                          <span>待退 <strong>{money(item.remaining_ntd)}</strong></span>
                          <small className="finance-mono-sub">{item.identity}</small>
                        </div>
                      </div>
                    </label>
                  );
                })}
              </div>
            )}
            <div className="finance-recon-col-summary">
              <span>已勾選待退款：<strong>{money(dueTotal)}</strong>（共 {selectedIds.length} 項）</span>
            </div>
          </div>
        </div>

        {/* 試算與決策條 */}
        <div className="finance-recon-calculation-bar">
          <div className="finance-recon-calc-metrics">
            <div>
              <small>勾選銀行實退</small>
              <strong>{money(bankTotal)}</strong>
            </div>
            <span className="finance-recon-calc-operator">−</span>
            <div>
              <small>對應待退款項</small>
              <strong>{money(dueTotal)}</strong>
            </div>
            <span className="finance-recon-calc-operator">=</span>
            <div>
              <small>沖銷差額</small>
              <strong className={!selectedIds.length ? undefined : diff === 0 ? 'finance-paid' : diff < 0 ? 'finance-diff-under' : 'finance-diff-over'}>
                {!obligations.length || !selectedIds.length ? '尚未核對' : diff === 0 ? '金額相符' : diff < 0 ? `短少 ${money(-diff)}` : `超出 ${money(diff)}`}
              </strong>
            </div>
          </div>

          <div className="finance-recon-calc-explanation">
            {!obligations.length ? (
              <span>本案目前沒有可選款項，請點選「前往本案帳務」確認正式款項資料，或於下方進行流水用途更正。</span>
            ) : !selectedIds.length ? (
              <span>請先選擇本次要核銷的退款款項，再核對金額。</span>
            ) : diff === 0 ? (
              <span>退款金額與本次選取款項相符；請在下方檢查核銷影響並確認核銷。</span>
            ) : (
              <span>退款金額與選取款項存在差額，請在下方核銷表單選擇差額處理方式。</span>
            )}
          </div>
        </div>

        {/* 無款項時提供合規處置指引面板 */}
        {!obligations.length && (
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
              {onViewCase && (
                <button type="button" className="finance-btn-action-primary" onClick={onViewCase} disabled={selectionBusy}>
                  查看本案帳務
                </button>
              )}
              <button type="button" className="finance-btn-action-secondary" onClick={() => setShowReassign((prev) => !prev)} disabled={selectionBusy}>
                {showReassign ? '收合更正表單' : '更正款項用途／重新歸屬'}
              </button>
            </div>
            {showReassign && (
              <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: '1px solid #ebdcd1' }}>
                <FinanceImportCorrectionForm
                  rowIdentity={row.row_identity}
                  sourceLabel={row.reference}
                  bankAmount={row.amount_ntd}
                  initialKind={initialKind}
                  initialCaseNo={data.case_no}
                  staff={[]}
                  onPosted={onPosted}
                  onBusyChange={reportBusy}
                />
              </div>
            )}
          </div>
        )}

        {/* 預覽與確認核銷（當有選取款項時） */}
        {selectedIds.length > 0 && (
          <div className="finance-scope-note finance-recon-preview-box">
            <div className="finance-recon-preview-header">
              <h5>核銷處置與預覽確認</h5>
            </div>
            <FinanceImportCorrectionForm
              key={selectedIds.join('|')}
              rowIdentity={row.row_identity}
              sourceLabel={row.reference}
              staff={[]}
              initialKind={initialKind}
              initialCaseNo={data.case_no}
              lockedObligations={obligations.filter((item) => selectedIds.includes(item.identity)).map((item) => ({
                id: item.identity,
                label: `${item.label || '應退款項'} · 待退 ${money(item.remaining_ntd)}`,
              }))}
              onPosted={onPosted}
              onBusyChange={reportBusy}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function CaseBankReconciliation({ row, data, onPosted, onBusyChange, onViewCase, pricing, multiBirthCount, onOpenParamsEdit, refundAccountNo, refundName }: {
  row: FinanceBankTransaction;
  data: CaseAccounting;
  onPosted: () => void;
  onBusyChange: (busy: boolean) => void;
  onViewCase?: () => void;
  pricing?: CasePricing | null;
  multiBirthCount?: string | null;
  onOpenParamsEdit?: () => void;
  refundAccountNo: string | null;
  refundName: string;
}) {
  const target = row.reconciliation_target;
  const [chosenIds, setChosenIds] = useState<string[]>([]);
  const [selectionBusy, setSelectionBusy] = useState(false);
  const requiresSelection = target?.requires_selection ?? false;
  const selectedIds = requiresSelection ? chosenIds : target?.obligation_identities ?? [];
  const staffTarget = useMemo(() => target?.staff_id && selectedIds.length ? {
    staffId: target.staff_id, obligationIdentity: selectedIds[0],
    obligationIdentities: selectedIds,
  } : null, [target, selectedIds]);
  const reportBusy = useCallback((busy: boolean) => {
    setSelectionBusy(busy);
    onBusyChange(busy);
  }, [onBusyChange]);
  if (!target || target.case_no !== data.case_no) return <p role="alert">對應款項已變更，請返回銀行對帳重新查詢。</p>;
  const isReceipt = row.classification_type === 'client_receipt';
  const isRefundReturn = row.classification_type === 'client_refund_return';
  const isStaff = target.staff_id !== null;
  const items = isStaff ? data.staff_items : data.client_items;
  const direction = isReceipt ? 'receivable' : 'payable';
  const obligations = items.filter(item => item.direction === direction && target.obligation_identities.includes(item.identity));
  if (obligations.length !== target.obligation_identities.length) {
    return <p role="alert">對應款項已變更，請返回銀行對帳重新查詢。</p>;
  }
  const initialKind = row.classification_type === 'client_subsidy_return' ? 'client_subsidy_return' : 'client_refund';
  const stage2 = data.client_items.find(item => item.identity.includes('second'));
  const stage2Due = stage2 ? stage2.remaining_ntd ?? stage2.expected_ntd : undefined;
  return <section className="finance-case-subview" aria-label="案件銀行交易核對">
    <header>
      <h3>{isRefundReturn ? '客戶退匯' : isReceipt ? '客戶繳款' : isStaff ? (row.bank === 'taishin' ? '補助轉交月嫂' : '月嫂薪資') : '客戶退款'} · 核對交易</h3>
      <p>{row.bank === 'sinopac' ? '永豐' : '台新'} · {row.transaction_date ?? '日期未提供'} · {row.reference} · {money(row.amount_ntd)}</p>
      {!isReceipt && !isStaff && <p>名冊退款戶名：{refundName || '待確認'} · 名冊退款帳號：{refundAccountNo || '待補齊'}</p>}
    </header>
    {onOpenParamsEdit && (
      <AccountingParametersBar
        caseNo={data.case_no}
        pricing={pricing}
        multiBirthCount={multiBirthCount}
        customerStage2Due={stage2Due}
        onOpenEdit={onOpenParamsEdit}
      />
    )}
    {isStaff && requiresSelection && <fieldset disabled={selectionBusy}>
      <legend>本次核銷款項</legend>
      {obligations.length ? obligations.map(item=><label key={item.identity}>
        <input type="checkbox" aria-label={`核銷款項 ${item.identity}`} checked={selectedIds.includes(item.identity)}
          onChange={()=>setChosenIds(ids=>ids.includes(item.identity)?ids.filter(id=>id!==item.identity):[...ids,item.identity])}/>
        {item.label || '月嫂應付款'} · 待付 {money(item.remaining_ntd)} · {item.due_date ?? '未定日期'}
      </label>) : <p>本案目前沒有可選款項，請回案件帳務確認正式款項資料。</p>}
    </fieldset>}
    {isRefundReturn ? (
      <ClientRefundReturnReconciliationPanel caseNo={data.case_no} bankRowId={row.row_id} onPosted={onPosted} onBusyChange={onBusyChange} />
    ) : isReceipt ? (
      <ClientReceiptReconciliationPanel caseNo={data.case_no} requiredBankRowId={row.row_id}
        initialObligationId={requiresSelection ? undefined : target.obligation_identities[0]} onChanged={onPosted} onBusyChange={onBusyChange} />
    ) : isStaff && !staffTarget ? (
      <p>請先選擇核銷款項，再檢查核銷影響。</p>
    ) : staffTarget ? (
      <StaffPayoutRemediationWorkbench key={selectedIds.join('|')} target={staffTarget} financeImportRowId={row.row_id} sourceBank={row.bank} bankSource={row}
        requiresFundingSplit={(data.subsidy_plan?.events.at(-1)?.scheme ?? data.scheme) === 'split'} confirmPreview onPosted={onPosted} onBusyChange={reportBusy} />
    ) : (
      <CaseRefundReconciliation
        row={row}
        data={data}
        obligations={obligations}
        selectedIds={selectedIds}
        onSelectionChange={setChosenIds}
        initialKind={initialKind}
        onPosted={onPosted}
        reportBusy={reportBusy}
        selectionBusy={selectionBusy}
        onViewCase={onViewCase}
      />
    )}
  </section>;
}

export function FinanceCaseAccounting({initialCase='',embedded=false,onChanged,initialNoticeStage,onIdentity,bankReconciliation,onPayableReview,reviewObligation}: {initialCase?:string;embedded?:boolean;onChanged?:()=>void;initialNoticeStage?:Stage;onIdentity?:(caseNo:string,name:string)=>void;onBank?:()=>void;onSubsidy?:(caseNo:string)=>void;onLegacy?:(caseNo:string)=>void;bankReconciliation?:{row:FinanceBankTransaction;onPosted:()=>void;onBusyChange:(busy:boolean)=>void};onPayableReview?:(item:HistoricalPayableAuditItem)=>void;reviewObligation?:string}){
 const {requestLeave}=useUnsavedNavigation();
 const[state,setState]=useState<{caseNo:string;data?:CaseAccounting;order?:OrderDetail;notices?:CasePaymentReminder[];registry?:ClientRegistryDetail;accountView?:CaseVirtualAccountView;pricing?:CasePricing;error?:string;noticeError?:boolean;loading?:boolean}>({caseNo:initialCase,loading:true});
 const[paramsDrawerOpen,setParamsDrawerOpen]=useState(false);
 const[revision,setRevision]=useState(0),[view,setView]=useState<Stage|'plan'|null>(initialNoticeStage??null);
 const[showSupplement,setShowSupplement]=useState(false);
 const[reconciliationBusy,setReconciliationBusy]=useState(false);
 const[editingOpen,setEditingOpen]=useState(false);
 const[termsEditState,setTermsEditState]=useState({dirty:false,busy:false});
 const[pricingEditState,setPricingEditState]=useState({dirty:false,busy:false});
 const accountingBusy=reconciliationBusy||termsEditState.busy||pricingEditState.busy;
 const accountingDraft=termsEditState.dirty||pricingEditState.dirty;
 const[pendingAccountingRefresh,setPendingAccountingRefresh]=useState(false);
 const[freshBankRow,setFreshBankRow]=useState<FinanceBankTransaction|null>(null);
 const[bankRefreshError,setBankRefreshError]=useState('');
 const reportReconciliationBusy=useCallback((busy:boolean)=>setReconciliationBusy(busy),[]);
 useEffect(()=>{bankReconciliation?.onBusyChange(accountingBusy);return()=>bankReconciliation?.onBusyChange(false);},[accountingBusy,bankReconciliation?.onBusyChange]);
 useEffect(()=>subscribeCaseAccountingChanges(caseNo=>{if(caseNo===initialCase)setPendingAccountingRefresh(true);}),[initialCase]);
 useEffect(()=>{if(pendingAccountingRefresh&&!accountingBusy&&!accountingDraft){setPendingAccountingRefresh(false);setRevision(v=>v+1);}},[pendingAccountingRefresh,accountingBusy,accountingDraft]);
 useEffect(()=>{
   if(!bankReconciliation)return;
   const controller=new AbortController();setFreshBankRow(null);setBankRefreshError('');
   void financeImportQueryClient.listBankTransactions({transaction_status:'all',row_id:bankReconciliation.row.row_id},{signal:controller.signal}).then(page=>{
     if(controller.signal.aborted)return;
     const row=page.items.find(item=>item.row_id===bankReconciliation.row.row_id);
     if(!row||(row.reconciliation_target?.case_no!==initialCase&&!(row.status==='posted'&&row.cases.includes(initialCase)))){setBankRefreshError('原流水目前沒有本案可核銷款項，請核對最新帳務。');return;}
     setFreshBankRow(row);
   }).catch(()=>{if(!controller.signal.aborted)setBankRefreshError('原流水的最新核銷款項讀取失敗，請重新查詢。');});
   return()=>controller.abort();
 },[initialCase,bankReconciliation?.row.row_id,revision]);
  const [showFullCase, setShowFullCase] = useState(false);
 const[copied,setCopied]=useState(false);
 const section=useRef<HTMLElement>(null),returnScroll=useRef(0),returnFocus=useRef<HTMLElement|null>(null);
 useEffect(()=>{const controller=new AbortController();setState(old=>old.caseNo===initialCase?{...old,loading:true,error:undefined}:{caseNo:initialCase,loading:true});if(!initialCase)return()=>controller.abort();void Promise.allSettled([financeAccountingClient.query(initialCase,controller.signal),ordersQueryClient.getOrderDetail(initialCase,{signal:controller.signal}),paymentOverdueReminderClient.case(initialCase,controller.signal),clientRegistryClient.query(initialCase,controller.signal,true),caseVirtualAccountClient.query(initialCase,controller.signal),accountingPricingClient.queryCase(initialCase)]).then(([accounting,order,notices,registry,accountView,pricing])=>{if(controller.signal.aborted)return;if(accounting.status==='rejected'){const status=accounting.reason instanceof ApiHttpError?accounting.reason.status:0;setState({caseNo:initialCase,error:status===404?'找不到此案件，請確認案件編號。':status===401?'登入已失效，請重新登入後查詢。':status===403?'目前沒有查閱帳務的權限。':'帳務資料暫時無法取得，請稍後重新查詢。'});return;}setState({caseNo:initialCase,data:accounting.value,order:order.status==='fulfilled'?order.value:undefined,notices:notices.status==='fulfilled'?notices.value:undefined,registry:registry.status==='fulfilled'?registry.value:undefined,accountView:accountView.status==='fulfilled'?accountView.value:undefined,pricing:pricing.status==='fulfilled'?pricing.value:undefined,noticeError:notices.status==='rejected',loading:false});});return()=>controller.abort();},[initialCase,revision]);
 useLayoutEffect(()=>{if(view!==null){section.current?.querySelector<HTMLElement>('.finance-case-subview h3')?.focus();return;}if(view===null&&returnFocus.current){const body=section.current?.closest('.drawer-body');if(body)body.scrollTop=returnScroll.current;const trigger=returnFocus.current;const target=trigger.isConnected?trigger:section.current?.querySelector('summary');target?.focus({preventScroll:true});returnFocus.current=null;}},[view,!!state.data]);
 useEffect(()=>{if(state.caseNo===initialCase&&state.data)onIdentity?.(initialCase,state.data.client_name);},[initialCase,state.caseNo,state.data,onIdentity]);
 function refresh(){setRevision(v=>v+1);onChanged?.();}
 function open(next:Stage|'plan'){returnFocus.current=document.activeElement instanceof HTMLElement?document.activeElement:null;returnScroll.current=section.current?.closest('.drawer-body')?.scrollTop??0;requestLeave(()=>setView(next));}
 function back(){requestLeave(()=>setView(null));}
 function copyVirtual(val:string){if(!val)return;if(typeof navigator!=='undefined'&&navigator.clipboard){void navigator.clipboard.writeText(val).then(()=>{setCopied(true);setTimeout(()=>setCopied(false),2000);});}}
 const data=state.caseNo===initialCase?state.data:undefined;
 const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 if(!initialCase)return <p>請從案件清單選擇案件。</p>;
 const selected=data?.subsidy_plan?.events.at(-1)?.scheme;
 const staff=data?[...new Set(data.staff_items.filter(row=>row.direction==='payable').map(row=>row.party))].join('、'):'';
 const staffItems=data?.staff_items.filter(row=>row.direction==='payable')??[];
 const staffTransactions=data?.transactions.filter(row=>row.kind==='payout'||staffItems.some(s=>s.identity===row.item_identity))??[];
 const staffPayableTotal=staffItems.reduce((sum,item)=>sum+item.expected_ntd,0);
 const staffPaidTotal=staffItems.reduce((sum,item)=>sum+item.actual_ntd,0);
 const staffRemainingTotal=staffItems.reduce((sum,item)=>sum+(item.remaining_ntd??Math.max(0,item.expected_ntd-item.actual_ntd)),0);

 const refundClientItems=data?.client_items.filter(row=>row.direction==='payable')??[];
 const refundTransactions=data?.transactions.filter(row=>row.kind==='refund'||refundClientItems.some(r=>r.identity===row.item_identity))??[];
 const refundRemainingTotal=refundClientItems.reduce((sum,item)=>{
  const remaining = item.remaining_ntd == null ? BigInt(item.expected_ntd) - BigInt(item.actual_ntd) : BigInt(item.remaining_ntd);
  return sum + (remaining > 0n ? remaining : 0n);
 },0n);

 const subsidyKnown=data?.subsidy_ntd!=null;
 const subsidyTotal=data?.subsidy_ntd??0;
 const govBankFacts=data?.bank_facts?.filter(b=>b.cash_flow==='G')??[];
 const govReceivedNtd=data?.cash_by_flow?.G??govBankFacts.reduce((s,b)=>s+b.amount_ntd,0);

 const virtualAccount=state.accountView?.imported_virtual_accounts?.[0]??state.registry?.finance?.values?.virtual_account??state.accountView?.built_in_virtual_account??buildDefaultVirtualAccount(initialCase);
 const isImportedVirtual=(state.accountView?.imported_virtual_accounts?.length??0)>0;
 const hasMultipleImported=(state.accountView?.imported_virtual_accounts?.length??0)>1;
 const refundBankCode=state.registry?.beclass?.values?.refund_bank_code??null;
 const refundAccountNo=state.registry?.beclass?.values?.refund_account_no??null;
 const refundAccountStatus=state.registry?.beclass?.values?.refund_account_status??null;
 const refundName=state.registry?.beclass?.values?.name??state.registry?.client?.values?.name??data?.client_name??'';
 const contactPhone=state.registry?.beclass?.values?.phone??state.registry?.client?.values?.phone??null;
 const multiBirthCount=state.registry?.beclass?.values?.multi_birth_count??(state.pricing&&state.pricing.terms.payroll.excess>=450?'雙胞胎':'單胞胎');

 return <section ref={section} className="case-accounting finance-compact-case" aria-label="案件帳務內容">
 {!embedded&&data&&<h2>{data.case_no} · {data.client_name}</h2>}{state.error&&<p role="alert">{state.error}</p>}{state.loading&&<p role="status">正在讀取案件資料…</p>}{state.error&&<button onClick={()=>setRevision(v=>v+1)}>重新讀取案件</button>}
 {data&&<details className="finance-case-block finance-case-edit-tools" onToggle={event=>{if(event.currentTarget.open)setEditingOpen(true);}}>
   <summary>調整本案服務條件／計價</summary>
   {editingOpen&&<div className="finance-case-block-body">
     <p>儲存成功後，本案帳務與原銀行流水的核銷款項會同步更新，請重新核對後核銷。</p>
     <fieldset disabled={reconciliationBusy||pricingEditState.busy}>
       {state.registry?.order_terms.status==='ready'&&state.registry.order_terms.data?
         <OrderTermsMutationPanel caseNo={initialCase} query={state.registry.order_terms.data} fromRegistry onObserved={()=>setPendingAccountingRefresh(true)} onEditStateChange={setTermsEditState}/>:
         <p>目前無法讀取正式服務條件，請重新查詢案件後再更正。</p>}
     </fieldset>
     <CasePricingAdjustmentPanel caseNo={initialCase} revision={revision} disabled={reconciliationBusy||termsEditState.busy}
       onCommitted={async()=>{setPendingAccountingRefresh(true);}} onStateChange={setPricingEditState}/>
   </div>}
 </details>}
 {data&&bankReconciliation&&!showFullCase&&<fieldset style={{border:0,padding:0,margin:0,minWidth:0}} disabled={termsEditState.busy||termsEditState.dirty||pricingEditState.busy||pricingEditState.dirty||(pendingAccountingRefresh&&!reconciliationBusy)}>
   {bankRefreshError?<p role="alert">{bankRefreshError}<button onClick={refresh}>重新查詢原流水</button></p>:!freshBankRow||freshBankRow.row_id!==bankReconciliation.row.row_id||state.loading?<p role="status">正在同步帳務與原流水的核銷款項…</p>:freshBankRow.status==='posted'?<p role="status">原流水已核銷，請查看最新案件帳務。</p>:<CaseBankReconciliation key={`${freshBankRow.row_identity}:${revision}`} data={data} {...bankReconciliation} row={freshBankRow} pricing={state.pricing} multiBirthCount={multiBirthCount} refundAccountNo={refundAccountNo} refundName={refundName} onOpenParamsEdit={()=>setParamsDrawerOpen(true)} onBusyChange={reportReconciliationBusy} onViewCase={()=>setShowFullCase(true)}/>}
 </fieldset>}
 {data&&(!bankReconciliation||showFullCase)&&<><div hidden={view!==null}>
 {showFullCase&&bankReconciliation&&(
   <div className="finance-reconciliation-return-banner">
     <div>
       <span className="finance-empty-badge" style={{marginRight:'8px'}}>正在核對銀行流水</span>
       <span style={{fontSize:'0.88rem',fontWeight:600,color:'var(--md-sys-color-on-surface,#1e1b19)'}}>
         {bankReconciliation.row.bank==='sinopac'?'永豐銀行':'台新銀行'} · {bankReconciliation.row.transaction_date??'日期未提供'} · {bankReconciliation.row.reference} · {money(bankReconciliation.row.amount_ntd)}
       </span>
     </div>
     <button type="button" className="finance-btn-action-primary" onClick={()=>{setShowFullCase(false);refresh();}}>
       返回對核交易
     </button>
   </div>
 )}
 <CancellationSettlementAccounting key={revision} data={data} />
 <AccountingParametersCard
   caseNo={initialCase}
   pricing={state.pricing}
   multiBirthCount={multiBirthCount}
   customerAmountNtd={data.customer_amount_ntd ?? data.receivable_ntd}
   staffAmountNtd={data.staff_receivable_ntd}
   onOpenEdit={() => setParamsDrawerOpen(true)}
 />
 <dl className="finance-compact-facts" aria-label="案件精簡摘要"><div><dt>相關月嫂</dt><dd>{staff||state.order?.staff_name||'待確認'}</dd></div><div><dt>實際開始</dt><dd>{state.order?.actual_start_date??'待確認'}</dd></div><div><dt>實際結束</dt><dd>{state.order?.actual_end_date??'待確認'}</dd></div><div><dt>案件總額 T</dt><dd>{money(data.staff_receivable_ntd)}</dd></div></dl>
 <section className="finance-reconciliation-card" aria-label="銀行對帳與帳戶資訊">
   <div className="finance-reconciliation-header">
     <div className="finance-reconciliation-title">
       <h4>銀行對帳與帳戶核對資訊</h4>
       <span className="finance-reconciliation-hint">核對永豐銷帳編號與台新退款／出款流水</span>
     </div>
     <div className="finance-reconciliation-actions">
       {contactPhone && <span className="finance-reconciliation-phone">聯絡電話：{contactPhone}</span>}
       <button
         type="button"
         className="finance-btn-secondary"
         onClick={() => setShowSupplement(!showSupplement)}
         aria-expanded={showSupplement}
       >
         {showSupplement ? '收合補登' : '手動補登款項'}
       </button>
     </div>
   </div>
   <dl className="finance-reconciliation-grid">
     <div className="finance-reconciliation-item">
       <dt>永豐專屬虛擬帳號</dt>
       <dd>
         {virtualAccount ? (
           <div className="finance-account-mono-group">
             <strong className="finance-mono-text" data-testid="virtual-account-display">{virtualAccount}</strong>
             <button type="button" className="finance-copy-chip" onClick={()=>copyVirtual(virtualAccount)} aria-label="複製虛擬帳號">{copied ? '已複製' : '複製'}</button>
             {isImportedVirtual && <span className="finance-tag-imported" title="人工匯入指定之虛擬帳號">匯入</span>}
             {hasMultipleImported && <span className="finance-tag-warn" title="名冊存在多筆匯入虛擬帳號，請確認">多筆衝突</span>}
           </div>
         ) : (
           <span className="finance-missing-text" data-testid="virtual-account-missing">尚未設定 / 無虛擬帳號</span>
         )}
       </dd>
     </div>
     <div className="finance-reconciliation-item">
       <dt>退款銀行與分行</dt>
       <dd>
         {refundBankCode ? (
           <span className="finance-bank-text" data-testid="refund-bank-display">{formatBankDisplay(refundBankCode)}</span>
         ) : (
           <span className="finance-missing-text" data-testid="refund-bank-missing">待補齊 / 未填寫銀行代碼</span>
         )}
       </dd>
     </div>
     <div className="finance-reconciliation-item">
       <dt>退款帳號</dt>
       <dd>
         {refundAccountNo ? (
           <strong className="finance-mono-text" data-testid="refund-account-display">{refundAccountNo}</strong>
         ) : (
           <span className="finance-missing-text" data-testid="refund-account-missing">待補齊 / 未填寫帳號</span>
         )}
       </dd>
     </div>
     <div className="finance-reconciliation-item">
       <dt>退款戶名／登錄狀態</dt>
       <dd>
         <div className="finance-status-group">
           <span>{refundName || '待確認'}</span>
           {refundAccountStatus === 'complete' ? (
             <span className="finance-badge-complete">已登錄完整</span>
           ) : (refundBankCode || refundAccountNo) ? (
             <span className="finance-badge-partial">資料未齊全</span>
           ) : (
             <span className="finance-badge-incomplete">未填寫</span>
           )}
         </div>
       </dd>
     </div>
   </dl>
   <div className="finance-reconciliation-footer">
     <small>銀行對帳單未配對時，可比對永豐入帳銷帳編號與本案虛擬帳號，或核對退款帳號與戶名。缺少帳號時可至客戶名冊補齊。</small>
   </div>
 </section>
 {showSupplement && (
   <CaseManualSupplementWorkbench
     caseNo={initialCase}
     clientItems={data.client_items}
     staffItems={data.staff_items}
     initialStaffObligation={reviewObligation}
     subsidyNtd={data.subsidy_ntd ?? 0}
     onSuccess={updated => {
       setState(old => ({ ...old, data: updated }));
       refresh();
     }}
     onClose={() => setShowSupplement(false)}
   />
 )}
 <details className="finance-case-block" open><summary>01　客戶繳款</summary><div className="finance-case-block-body"><div className="finance-table-container" tabIndex={0} role="region" aria-label="各期繳款與通知，可左右捲動"><table className="finance-table finance-case-periods"><thead><tr><th>期款</th><th>原到期日</th><th>應繳</th><th>已收／待收</th><th>入帳資訊</th><th>通知時間</th><th>通知</th></tr></thead><tbody>{stages.map(stage=>{
 const sources=data.client_items.filter(row=>row.direction==='receivable'&&row.payment_stage===stage),item=sources.length===1?sources[0]:undefined;
 const exempt=data.customer_fully_received===true&&data.customer_amount_ntd===0;
 const expected=item?.expected_ntd??(exempt?0:null),actual=item?.actual_ntd??(exempt?0:null),remaining=item?.remaining_ntd??(exempt?0:null);
 const notice=state.notices?.find(row=>row.payment_stage===stage),last=lastNotification(notice);
 const receipts=item?data.transactions.filter(row=>row.item_identity===item.identity&&row.kind==='receipt'&&row.amount_ntd>0).slice().sort((a,b)=>b.occurred_on.localeCompare(a.occurred_on)):[];
  return <tr key={stage} data-payment-stage={stage} className={data.collection_progress?.stage===stage?'is-current':''}><td><strong>{stageNames[stage]}</strong>{stage==='deposit'&&<small>含樓層／其他費用</small>}</td><td>{expected===0?'不需繳納':item?.due_date??'日期待確認'}{remaining!=null&&remaining>0&&item?.due_date&&<small>{item.due_date>today?'未到期':item.due_date===today?'今日到期':'逾期'}</small>}</td><td>{money(expected)}</td><td><span>已收 {money(actual)}</span>{remaining===0?<small className="finance-paid">{expected===0?'免繳':'已繳齊'}</small>:<small>待收 {money(remaining)}</small>}</td><td>{receipts.length?<><span>{receipts[0].occurred_on} · {receipts[0].bank==='manual'?'人工補登':receipts[0].bank==='sinopac'?'永豐':receipts[0].bank==='taishin'?'台新':receipts[0].bank==='legacy'?'歷史來源':'原來源'}</span>{receipts.length>1&&<details><summary>{receipts.length} 筆入帳</summary>{receipts.map(row=><p key={row.identity}>{row.occurred_on} · {row.bank==='manual'?'人工補登':'入帳'} · {money(row.amount_ntd)}</p>)}</details>}</>:<span>{item||exempt?'尚無已核銷入帳':'來源待確認'}</span>}</td><td>{last?notificationTime(last):notice?(notice.history.length?'尚無成功通知':'尚未通知'):'待確認'}{notice&&notificationStatus(notice)&&<small>{notificationStatus(notice)}</small>}</td><td><div className="finance-case-period-actions"><button type="button" className="finance-btn-primary finance-case-notice-button" aria-label={'通知'+stageNames[stage]} disabled={remaining==null||remaining<=0||!notice?.can_send||!!state.loading} title={remaining===0?(expected===0?'本期免繳':'本期已繳齊'):notice?.unavailable_reason??(notice?'查看本期通知內容與紀錄':'通知來源待確認')} onClick={()=>open(stage)}>通知</button></div></td></tr>;
  })}</tbody></table></div>{state.noticeError&&<p role="status">通知資料暫時無法取得，時間保留待確認。<button className="finance-btn-link" onClick={()=>setRevision(v=>v+1)}>重新讀取通知</button></p>}
</div></details>
 <details className="finance-case-block" open><summary>02　補助退款方案</summary><div className="finance-case-block-body"><div className="finance-compact-plan"><div><small>本案補助 {data.subsidy_ntd==null?'金額待確認':money(data.subsidy_ntd)}</small><strong>{selected?subsidyPlanLabels[selected]:'尚未設定'}</strong><p>{selected?subsidyPlanTargets[selected]:'補助金額先計算，對象可由人工或符合條件的銀行明細確認。'}</p></div><button type="button" className="finance-btn-primary" disabled={!data.subsidy_plan||!!state.loading} onClick={()=>open('plan')}>{selected?'修改補助退款方案':'設定補助退款方案'}</button></div><FinanceCaseBankMemos notes={data.bank_memos??[]}/><p>可提前確認方案，不改各期應繳；成立條件具備時，先預檢並承接款項。</p>{data.subsidy_plan?.events.at(-1)?.source==='bank'&&<p>依銀行明細確認方案</p>}{selected&&<p role="status">{data.ongoing_completed?'客戶款已齊且方案已保存，已移出進行中案件。':'方案已保存，客戶款未齊時仍保留在進行中案件。'}</p>}</div></details>
 <details className="finance-case-block" open><summary>03　月嫂薪資</summary><div className="finance-case-block-body">
  {onPayableReview && state.order?.order_status.startsWith('歷史訂單－') &&
    <HistoricalPayableLookup caseNo={initialCase} month={today.slice(0, 7)} revision={revision} onCase={onPayableReview} />}
  <div className="finance-staff-summary-cards" aria-label="月嫂薪資匯總">
    <div className="finance-staff-summary-card">
      <small>應付月嫂總額</small>
      <strong>{money(staffItems.length ? staffPayableTotal : null)}</strong>
    </div>
    <div className="finance-staff-summary-card">
      <small>已核銷金額（含內扣手續費）</small>
      <strong>{money(staffItems.length ? staffPaidTotal : null)}</strong>
    </div>
    <div className="finance-staff-summary-card">
      <small>尚待出款</small>
      <strong className={staffItems.length > 0 && staffRemainingTotal === 0 ? 'finance-paid' : ''}>
        {staffItems.length === 0 ? '待確認' : staffRemainingTotal === 0 ? '已付齊' : money(staffRemainingTotal)}
      </strong>
    </div>
  </div>

  <div className="finance-table-container" tabIndex={0} role="region" aria-label="月嫂薪資與核銷明細，可左右捲動">
    <table className="finance-table finance-case-periods">
      <thead>
        <tr>
          <th>服務項目</th>
          <th>預計撥款日</th>
          <th>應付</th>
          <th>已核銷／待付</th>
          <th>銀行手續費</th>
          <th>出款資訊</th>
          <th>核銷狀態</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {staffItems.length > 0 ? (
          staffItems.map(item => {
            const diff = item.expected_ntd - item.actual_ntd;
            const itemTransactions = staffTransactions.filter(t => t.item_identity === item.identity);
            const hasConfirmedFee = itemTransactions.some(t => (t.transfer_fee_ntd ?? 0) > 0);
            const isSettled = item.settled || item.remaining_ntd === 0 || (item.actual_ntd >= item.expected_ntd && item.has_payment);
            const isFeeSettled = isSettled && hasConfirmedFee;
            return (
              <tr key={item.identity}>
                <td>
                  <strong>{item.party}</strong>
                  <small>{item.label || '月嫂服務費'}</small>
                  {(selected ?? data.scheme) === 'split' && !item.funding_portions?.length && <small>自備款／補助款分配待確認，可由原永豐流水選擇「補助方案一：核銷自備款，補助款保留待付」預覽確認。</small>}
                  {item.funding_portions?.map(p => <small key={p.funding_kind}>
                    {p.funding_kind === 'client' ? '自備款（永豐）' : '補助款（台新）'}：應付 {money(p.amount_ntd)} · 待付 {money(p.remaining_ntd)} · {p.due_date ?? '撥款日未設定'}
                  </small>)}
                  {item.funding_portions?.some(p => p.funding_kind === 'subsidy' && p.remaining_ntd !== null && p.remaining_ntd > 0) &&
                    <small>方案一剩餘補助待付，由台新補助款轉付月嫂。</small>}
                </td>
                <td>
                  <span>{item.due_date ?? '服務結束次月15日'}</span>
                  {item.due_date && (
                    <small>{item.due_date > today ? '未到期' : item.due_date === today ? '今日到期' : '已屆撥款日'}</small>
                  )}
                </td>
                <td>{money(item.expected_ntd)}</td>
                <td>
                  <span>已核銷 {money(item.actual_ntd)}</span>
                  {isFeeSettled ? (
                    <small className="finance-paid">手續費內扣結清</small>
                  ) : isSettled ? (
                    <small className="finance-paid">已結清</small>
                  ) : item.remaining_ntd != null && item.remaining_ntd > 0 ? (
                    <small>待付 {money(item.remaining_ntd)}</small>
                  ) : diff < 0 ? (
                    <small className="finance-diff-over">超付 {money(Math.abs(diff))}</small>
                  ) : (
                    <small>{money(item.remaining_ntd)}</small>
                  )}
                </td>
                <td>
                  {itemTransactions.length ? itemTransactions.map(t => <small key={t.identity}>
                    {t.transfer_fee_ntd == null ? '手續費未留存' : `${t.occurred_on} · ${money(t.transfer_fee_ntd)}（本筆銀行出款，含合併款）`}
                  </small>) : '尚無已核銷出款'}
                </td>
                <td>
                  {itemTransactions.length > 0 ? (
                    <>
                      <span>{itemTransactions[0].bank_amount_ntd != null && `銀行實付 ${money(itemTransactions[0].bank_amount_ntd)} · `}{itemTransactions[0].occurred_on} · {itemTransactions[0].bank === 'manual' ? '人工補登' : itemTransactions[0].bank === 'taishin' ? '台新銀行' : itemTransactions[0].bank === 'sinopac' ? '永豐銀行' : (itemTransactions[0].bank ?? '銀行出款')}</span>
                      {itemTransactions.length > 1 && (
                        <details>
                          <summary>{itemTransactions.length} 筆出款</summary>
                          {itemTransactions.map(t => (
                            <p key={t.identity}>{t.occurred_on} · {t.bank === 'manual' ? '人工補登' : t.bank === 'taishin' ? '台新' : '銀行'} · {money(t.amount_ntd)}</p>
                          ))}
                        </details>
                      )}
                    </>
                  ) : (
                    <span>尚無已核銷出款</span>
                  )}
                </td>
                <td>
                  {isFeeSettled ? (
                    <span className="finance-tag-imported" title="跨行轉帳 100 元以內手續費由收款方負擔並結清">手續費內扣結清</span>
                  ) : diff < 0 ? (
                    <span className="finance-tag-warn">超付款待核對</span>
                  ) : isSettled ? (
                    <span className="finance-paid">出款已結清</span>
                  ) : item.has_payment ? (
                    <span>部分出款</span>
                  ) : (
                    <span>待排程出款</span>
                  )}
                </td>
                <td>
                  <div className="finance-case-period-actions">
                    {diff !== 0 && !isFeeSettled && (
                      <button
                        type="button"
                        className="finance-btn-secondary finance-case-diff-button"
                        title="處置月嫂薪資差額"
                        onClick={() => alert(`月嫂款項差額 ${money(Math.abs(diff))}，請核對銀行出款流水。`) }
                      >
                        處置差額
                      </button>
                    )}
                    <button
                      type="button"
                      className="finance-btn-primary finance-case-notice-button"
                      disabled
                      title="月嫂撥款通知由系統排程批次發送"
                    >
                      通知
                    </button>
                  </div>
                </td>
              </tr>
            );
          })
        ) : (
          <tr>
            <td colSpan={8} className="finance-state">本案目前無月嫂應付項目。</td>
          </tr>
        )}
      </tbody>
    </table>
  </div>
 </div></details>

 <details className="finance-case-block" open><summary>04　補助退款與核銷</summary><div className="finance-case-block-body">
  <div className="finance-refund-summary-bar"><span>客戶退款待結：<strong>{refundRemainingTotal > 0n ? money(refundRemainingTotal) : !selected && (!subsidyKnown || subsidyTotal > 0) ? '補助歸屬待確認' : selected === 'advance' && subsidyTotal > 0 && !refundClientItems.length ? '補助退款待成立' : refundClientItems.length ? '已結清' : '無已成立退款'}</strong></span><span>政府款待入：<strong>{selected==='direct'?'不適用':!subsidyKnown?'金額待確認':subsidyTotal > 0 ? (govReceivedNtd >= subsidyTotal ? '已全額入帳' : money(Math.max(0, subsidyTotal - govReceivedNtd))) : '無補助'}</strong></span></div>
  <div className="finance-table-container" tabIndex={0} role="region" aria-label="補助退款與政府核銷明細，可左右捲動">
    <table className="finance-table finance-case-periods">
      <thead>
        <tr>
          <th>項目</th>
          <th>預計退款日</th>
          <th>應退／應收</th>
          <th>已退(收)／待退(收)</th>
          <th>出款／入帳資訊</th>
          <th>核銷狀態</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {refundClientItems.length > 0 ? (
          refundClientItems.map(row => {
            const isRefundSettled = row.settled || row.remaining_ntd === 0 || (row.actual_ntd >= row.expected_ntd && row.has_payment);
            return (
              <tr key={row.identity}>
                <td>
                  <strong>客戶退款</strong>
                  <small>{row.party || refundName} · {row.label}</small>
                </td>
                <td>
                  <span>{row.due_date ?? '市府核撥後退款'}</span>
                  <small>{isRefundSettled ? '已結算' : '案件結束結算'}</small>
                </td>
                <td>{money(row.expected_ntd)}</td>
                <td>
                  <span>已退 {money(row.actual_ntd)}</span>
                  {isRefundSettled ? (
                    <small className="finance-paid">已結清</small>
                  ) : (
                    <small>待退 {money(row.remaining_ntd)}</small>
                  )}
                </td>
                <td>
                  {refundTransactions.length > 0 ? (
                    <>
                      <span>{refundTransactions[0].occurred_on} · {refundTransactions[0].bank === 'manual' ? '人工補登' : refundTransactions[0].bank === 'taishin' ? '台新銀行' : refundTransactions[0].bank === 'sinopac' ? '永豐銀行' : (refundTransactions[0].bank ?? '銀行退款')}</span>
                      {refundTransactions[0].bank_amount_ntd != null && <small>整筆銀行實付 {money(refundTransactions[0].bank_amount_ntd)}；內扣手續費 {money(refundTransactions[0].transfer_fee_ntd)}</small>}
                      {refundTransactions.length > 1 && (
                        <details>
                          <summary>{refundTransactions.length} 筆退款</summary>
                          {refundTransactions.map(t => (
                            <p key={t.identity}>{t.occurred_on} · {t.bank === 'manual' ? '人工補登' : '退款'} · 已核銷 {money(t.amount_ntd)}{t.bank_amount_ntd != null && <>；整筆銀行實付 {money(t.bank_amount_ntd)}；內扣手續費 {money(t.transfer_fee_ntd)}</>}</p>
                          ))}
                        </details>
                      )}
                    </>
                  ) : (
                    <div>
                      <span>{refundBankCode ? formatBankDisplay(refundBankCode) : '未登記退款銀行'}</span>
                      <small className="finance-mono-text">{refundAccountNo || '待補齊帳號'}</small>
                    </div>
                  )}
                </td>
                <td>
                  {isRefundSettled ? (
                    <span className="finance-paid">已完成退款</span>
                  ) : refundAccountStatus === 'complete' ? (
                    <span>待出款（帳戶齊全）</span>
                  ) : (
                    <span className="finance-diff-under">帳戶待補齊</span>
                  )}
                </td>
                <td>
                  <div className="finance-case-period-actions">
                    <button
                      type="button"
                      className="finance-btn-primary finance-case-notice-button"
                      disabled={isRefundSettled}
                      title={isRefundSettled ? '退款已結清' : '退款進度通知'}
                    >
                      通知
                    </button>
                  </div>
                </td>
              </tr>
            );
          })
        ) : (
          <tr>
            <td>
              <strong>客戶退款</strong>
              <small>正常履約無扣減</small>
            </td>
            <td>不需退款</td>
            <td>NT$ 0</td>
            <td>
              <span>已退 NT$ 0</span>
              <small className="finance-paid">無退款義務</small>
            </td>
            <td>
              <span>預先登記備查</span>
              <small>{refundBankCode ? formatBankDisplay(refundBankCode) : '未填銀行'} {refundAccountNo ? `(${refundAccountNo})` : ''}</small>
            </td>
            <td>
              <span className="finance-paid">免退款</span>
            </td>
            <td>
              <div className="finance-case-period-actions">
                <button type="button" className="finance-btn-secondary" disabled>免操作</button>
              </div>
            </td>
          </tr>
        )}

        <tr>
          <td>
            <strong>政府補助款</strong>
            <small>{selected ? subsidyPlanLabels[selected] : '補助歸屬待確認'}</small>
          </td>
          <td>
            <span>依市府審查期程</span>
            <small>{subsidyTotal > 0 && govReceivedNtd >= subsidyTotal ? '款項已撥入' : '審核撥付中'}</small>
          </td>
          <td>{money(subsidyTotal)}</td>
          <td>
            <span>實撥 {money(govReceivedNtd)}</span>
            {!subsidyKnown ? <span>補助金額待確認</span> : selected==='direct' ? <span>政府直接付客戶，不追蹤實收</span> : subsidyTotal === 0 ? (
              <small className="finance-paid">自費案免請領</small>
            ) : govReceivedNtd >= subsidyTotal ? (
              <small className="finance-paid">已全額撥入</small>
            ) : (
              <small>待撥入 {money(Math.max(0, subsidyTotal - govReceivedNtd))}</small>
            )}
          </td>
          <td>
            {govBankFacts.length > 0 ? (
              <>
                <span>{govBankFacts[0].occurred_on} · 永豐 (G)</span>
                {govBankFacts.length > 1 && (
                  <details>
                    <summary>{govBankFacts.length} 筆公款</summary>
                    {govBankFacts.map((b, i) => (
                      <p key={i}>{b.occurred_on} · {money(b.amount_ntd)}</p>
                    ))}
                  </details>
                )}
              </>
            ) : (
              <span>{!subsidyKnown?'補助金額待確認':selected==='direct'?'不適用':subsidyTotal === 0 ? '自費案無公款' : '待市府公款撥入'}</span>
            )}
          </td>
          <td>
            {!subsidyKnown ? <span>補助金額待確認</span> : selected==='direct' ? <span>政府直接付客戶，不追蹤實收</span> : subsidyTotal === 0 ? (
              <span className="finance-paid">自費案免核銷</span>
            ) : govReceivedNtd >= subsidyTotal ? (
              <span className="finance-paid">已全額沖正</span>
            ) : govReceivedNtd > 0 ? (
              <span>部分撥入沖正</span>
            ) : (
              <span>待撥入沖正</span>
            )}
          </td>
          <td>
            <div className="finance-case-period-actions">
              <button
                type="button"
                className="finance-btn-secondary"
                onClick={() => open('plan')}
                title="修改補助款歸屬方案"
              >
                {selected ? '修改方案' : '設定方案'}
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div className="finance-subsidy-flow-note">
    <small><strong>金流規則說明：</strong>
      {selected === 'advance'
        ? '客戶先墊後退（方案二）：依客戶合法先墊及正式退款來源，由工會自台新退還客戶；政府補助入款另依原期間核對。'
        : selected === 'split'
        ? '分拆撥付（方案一）：永豐支付自備款部分，政府補助入工會後由台新轉付月嫂；分別核銷，剩餘補助款保留待付。'
        : selected === 'direct'
        ? '政府直撥（方案三）：政府款直接付客戶；工會不經手本補助、不追蹤客戶實收。'
        : '由人員設定補助款歸屬方案，結算時依方案進行金流沖正與核銷。'}
    </small>
  </div>
 </div></details>
 </div>{view==='plan'&&data.subsidy_plan&&<FinanceSubsidyPlanForm key={initialCase} caseNo={initialCase} source={data.subsidy_plan} subsidyAmount={data.subsidy_ntd} bankMemos={data.bank_memos??[]} onBack={back} onSaved={()=>{setView(null);refresh();}}/>}{view&&view!=='plan'&&(state.notices?.find(row=>row.payment_stage===view)?<FinanceCaseNotice key={initialCase+view} item={state.notices.find(row=>row.payment_stage===view)!} onBack={back} onChanged={refresh}/>:<div><p>本期通知來源待確認。</p><button onClick={back}>返回案件</button></div>)}</>}
 {data && (
   <AccountingParametersDrawer
     caseNo={initialCase}
     isOpen={paramsDrawerOpen}
     onClose={() => setParamsDrawerOpen(false)}
     initialPricing={state.pricing}
     initialMultiBirthCount={multiBirthCount}
     onCommitted={() => {
       setPendingAccountingRefresh(true);
       refresh();
     }}
   />
 )}
 </section>;
}
export function FinanceAccountingWarnings({ onCase }: { onCase: (caseNo: string) => void }) {
  const [data, setData] = useState<CaseAccounting[] | null>(null);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => { const controller = new AbortController(); setData(null); setError(false); void financeAccountingClient.warnings(controller.signal).then(value => { if (!controller.signal.aborted) setData(value); }).catch(() => { if (!controller.signal.aborted) setError(true); }); return () => controller.abort(); }, [revision]);
  return <section><h2>共用帳務警示</h2>{error ? <p role="alert">帳務警示暫時無法取得，請重新整理。</p> : !data ? <p role="status">正在載入帳務警示…</p> : !data.length ? <p className="finance-state">目前沒有帳務警示。</p> : data.map(row => <div key={row.case_no}><button className="finance-btn-secondary" type="button" onClick={() => onCase(row.case_no)}>{row.case_no} · {row.client_name} · 查看案件</button><AccountingWarningList data={row} onChange={() => setRevision(value => value + 1)} /></div>)}</section>;
}
