import { useEffect, useRef, useState } from 'react';
import {
  registrationApplicationsClient as client,
  type ManualNonCitizenCaseInput,
  type RegistrationApplication,
  type VirtualAccountCheckResult,
} from '../api/registration_applications/client';
import type { RegistryEditState } from './ClientRegistryDetailEditor';
import './RegistrationApplications.css';

const fieldLabels: Record<string, string> = {
  notes: '備註', line_id: 'LINE ID', baby_info: '寶寶資訊', service_time: '服務時段',
  service_type: '服務方式', delivery_type: '生產方式', residence_type: '居住型態',
  identity_status: '身分類別', service_start_date: '預計服務開始日',
};

const defaultForm: ManualNonCitizenCaseInput = {
  case_no: '',
  virtual_account: '',
  name: '',
  phone: '',
  gender: '女',
  identity_status: '非市民',
  service_start_date: '',
  service_end_date: '',
  service_days: 10,
  service_time: '09:00-18:00 (8小時)',
  service_type: '連續服務',
  delivery_type: '自然產',
  residence_type: '電梯大樓',
  baby_info: '單胞胎',
  city: '',
  address: '',
  due_month: '',
  birth_date: '',
  email: '',
  line_id: '',
  notes: '',
  admin_notes: '手動新增非市民案件（補齊歷史案件）',
  requires_cooking: false,
  refund_bank_code: '',
  refund_account_no: '',
};

export function RegistrationApplications({ onEditStateChange, initialId, onCommitted }: { onEditStateChange: (state: RegistryEditState) => void; initialId?: number; onCommitted?: () => Promise<void> }) {
  const [items, setItems] = useState<RegistrationApplication[]>([]);
  const [selected, setSelected] = useState<RegistrationApplication | null>(null);
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const selection = useRef(0);

  // Manual creation state
  const [showManualModal, setShowManualModal] = useState(false);
  const [manualForm, setManualForm] = useState<ManualNonCitizenCaseInput>(defaultForm);
  const [manualBusy, setManualBusy] = useState(false);
  const [manualError, setManualError] = useState('');
  const [conflictResult, setConflictResult] = useState<VirtualAccountCheckResult | null>(null);
  const [manualAccountStatus, setManualAccountStatus] = useState<string>('');

  useEffect(() => { onEditStateChange({ dirty: showManualModal, busy }); }, [busy, showManualModal, onEditStateChange]);

  const run = async (operation: () => Promise<void>) => {
    setBusy(true); setError(false); setMessage('');
    try { await operation(); } catch (failure) {
      setError(true); setMessage(failure instanceof Error ? failure.message : '處理結果未確認，請重新查詢同一筆申請。');
    } finally { setBusy(false); }
  };

  const refresh = () => run(async () => { const next = await client.pending(); setItems(next); setHasMore(next.length === 50); });

  const loadDetail = (id: number) => {
    const current = ++selection.current; setSelected(null); setError(false); setMessage('');
    if (!Number.isSafeInteger(id) || id <= 0) { setError(true); setMessage('申請編號無效，請從通知事項重新開啟。'); return; }
    setBusy(true);
    void client.detail(id).then(detail => { if (current === selection.current) { setSelected(detail); setUnknown(false); } })
      .catch(failure => { if (current === selection.current) { setError(true); setMessage(failure instanceof Error ? failure.message : '申請暫時無法讀取，請重新查詢。'); } })
      .finally(() => { if (current === selection.current) setBusy(false); });
  };

  useEffect(() => { void refresh(); }, []);
  useEffect(() => {
    if (initialId === undefined) return;
    loadDetail(initialId);
    return () => { selection.current++; };
  }, [initialId]);

  const approve = () => {
    if (!selected || busy || selected.status !== 'pending') return;
    const submitted = selected;
    void run(async () => {
      setUnknown(true);
      const result = await client.approve(submitted); setSelected(result); setUnknown(false);
      setItems(previous => previous.filter(item => item.registration_id !== result.registration_id));
      setMessage(result.registration_kind === 'non_citizen' ? `非市民需求已核准，案件 ${result.case_no} 已建立。` : '需求申請已核准，正式客戶資料已建立。');
      await onCommitted?.();
    });
  };

  const reject = () => {
    if (!selected || busy || unknown || selected.status !== 'pending') return;
    const original = selected;
    void run(async () => {
      setUnknown(true);
      const result = await client.reject(original); setSelected(result); setUnknown(false);
      setItems(previous => previous.filter(item => item.registration_id !== result.registration_id));
      setMessage(result.status === 'expired' ? '申請已到期，問卷內容已清除。' : '申請已拒絕，問卷內容已清除。');
    });
  };

  // Auto-generate virtual account when case_no changes if it matches standard A{year}{seq}
  const handleCaseNoChange = (value: string) => {
    const trimmed = value.trim();
    const match = /^A([0-9]{3})([0-9]{3})$/.exec(trimmed);
    let va = manualForm.virtual_account;
    if (match) {
      const year = match[1];
      const seq = parseInt(match[2], 10);
      if (seq >= 1 && seq <= 499) {
        va = `99781699${year}${String(seq + 500).padStart(3, '0')}`;
      }
    }
    setManualForm(prev => ({ ...prev, case_no: trimmed, virtual_account: va }));
    setManualAccountStatus('');
    setConflictResult(null);
  };

  // Pre-check virtual account and case number
  const handleCheckAccount = async () => {
    if (!manualForm.virtual_account) {
      setManualAccountStatus('請先輸入虛擬帳號');
      return;
    }
    setManualBusy(true); setManualError('');
    try {
      const result = await client.checkAccount(manualForm.virtual_account, manualForm.case_no);
      if (result.conflict) {
        setConflictResult(result);
        setManualAccountStatus(`⚠️ 此虛擬帳號已被案件【${result.conflict_case_no}】（狀態：${result.conflict_case_status}）使用`);
      } else {
        setConflictResult(null);
        setManualAccountStatus('✅ 虛擬帳號可正常使用（無衝突）');
      }
    } catch (caught) {
      setManualError(caught instanceof Error ? caught.message : '檢查帳號失敗');
    } finally {
      setManualBusy(false);
    }
  };

  // Validate form fields before submitting
  const validateManualForm = (): string | null => {
    if (!manualForm.case_no.trim()) return '請輸入案件編號。';
    if (!manualForm.virtual_account.trim()) return '請輸入虛擬帳號。';
    if (!/^99781699[0-9]{6}$/.test(manualForm.virtual_account.trim())) {
      return '虛擬帳號格式不正確，必須為 99781699 開頭之 14 碼數字。';
    }
    if (!manualForm.name.trim()) return '請輸入客戶姓名。';
    if (!manualForm.phone.trim()) return '請輸入連絡電話。';
    if (!manualForm.service_start_date) return '請選擇預計服務開始日。';
    if (!manualForm.service_days || manualForm.service_days <= 0) return '服務天數必須大於 0。';
    if (!manualForm.service_time.trim()) return '請輸入服務時段。';
    return null;
  };

  // Submit manual creation
  const handleManualSubmit = async (override = false) => {
    const validationError = validateManualForm();
    if (validationError) {
      setManualError(validationError);
      return;
    }
    setManualBusy(true); setManualError('');

    // If not already overriding, pre-check conflict first
    if (!override) {
      try {
        const check = await client.checkAccount(manualForm.virtual_account, manualForm.case_no);
        if (check.conflict) {
          setConflictResult(check);
          setManualBusy(false);
          return;
        }
      } catch (caught) {
        setManualError(caught instanceof Error ? caught.message : '檢查重複失敗');
        setManualBusy(false);
        return;
      }
    }

    try {
      const payload: ManualNonCitizenCaseInput = {
        ...manualForm,
        case_no: manualForm.case_no.trim(),
        virtual_account: manualForm.virtual_account.trim(),
        name: manualForm.name.trim(),
        phone: manualForm.phone.trim(),
        override_conflict: override,
        override_case_no: override && conflictResult ? conflictResult.conflict_case_no : undefined,
      };
      const receipt = await client.createManualNonCitizen(payload);
      setShowManualModal(false);
      setConflictResult(null);
      setManualForm(defaultForm);
      setMessage(receipt.message);
      setError(false);
      try {
        const next = await client.pending();
        setItems(next);
        setHasMore(next.length === 50);
      } catch {
        // background refresh failure
      }
      await onCommitted?.();
    } catch (caught) {
      setManualError(caught instanceof Error ? caught.message : '新增歷史非市民案件失敗');
    } finally {
      setManualBusy(false);
    }
  };

  const statuses = { pending: '待核准', approving: '建檔或清除確認中', approved: '已核准，問卷已清除', rejected: '已拒絕，問卷已清除', expired: '已到期，問卷已清除' };
  const time = (value: string) => new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Taipei' }).format(new Date(value));

  return <section className="registration-applications" aria-label="非市民申請" aria-busy={busy}>
    <header className="registration-applications__header">
      <div>
        <h2>非市民申請</h2>
        <p>查看與核准非市民服務申請，或手動新增歷史非市民案件補齊名冊。</p>
      </div>
      <div className="registration-applications__header-actions">
        <button
          type="button"
          className="registration-applications__manual-btn"
          disabled={busy}
          onClick={() => { setManualError(''); setConflictResult(null); setManualAccountStatus(''); setShowManualModal(true); }}
        >
          手動新增非市民案件
        </button>
        <button type="button" disabled={busy} onClick={() => void refresh()}>重新查詢</button>
      </div>
    </header>

    {message && <p className="registration-applications__message" role={error ? 'alert' : 'status'}>{message}</p>}
    {busy && <p className="registration-applications__loading" role="status">正在處理需求申請…</p>}

    <div className="registration-applications__layout">
      <div className="registration-applications__queue">
        <ul className="registration-applications__list">{items.map(item => <li key={item.registration_id}>
          <button type="button" className="registration-applications__item" aria-pressed={selected?.registration_id === item.registration_id} disabled={busy} onClick={() => loadDetail(item.registration_id)}>
            <span>申請 {item.registration_id}：{item.name}／{item.phone}{item.registration_kind === 'non_citizen' && '（非市民）'}</span>
            <small>查看申請 <span aria-hidden="true">→</span></small>
          </button>
        </li>)}</ul>
        {!busy && !items.length && <p className="registration-applications__empty">目前沒有待核准的需求申請。</p>}
        {hasMore && <button type="button" disabled={busy} onClick={() => void run(async () => {
          const next = await client.pending(items.at(-1)?.registration_id ?? 0);
          setItems(previous => [...previous, ...next]); setHasMore(next.length === 50);
        })}>載入更多</button>}
      </div>

      {selected ? <section className="registration-applications__detail" aria-label={`需求申請 ${selected.registration_id}`}>
        <header className="registration-applications__detail-header">
          <h3>申請 {selected.registration_id}：{selected.name ?? '內容已清除'}</h3>
          <span className="registration-applications__badge">{statuses[selected.status]}</span>
        </header>
        {selected.registration_kind === 'non_citizen' && <p className="registration-applications__kind">非市民服務申請{selected.case_no && ` · 案件編號：${selected.case_no}`}</p>}
        <p>送出：{time(selected.submitted_at_utc)}（台北時間） · 待審到期：{time(selected.expires_at_utc)}（台北時間）</p>
        <dl className="registration-applications__fields">
          {selected.fields.map((field, index) => <div key={`${field.label}-${index}`}>
            <dt>{fieldLabels[field.label] ?? field.label}</dt>
            <dd>{field.value}</dd>
          </div>)}
        </dl>
        <footer className="registration-applications__actions">
          {selected.status === 'pending' && !unknown && <>
            <button type="button" className="registration-applications__approve" disabled={busy} onClick={approve}>
              {selected.registration_kind === 'non_citizen' ? '核准並建立案件' : '核准並建立客戶'}
            </button>
            <button type="button" disabled={busy} onClick={reject}>拒絕並清除問卷</button>
          </>}
          {(unknown || selected.status === 'approving') && <button type="button" disabled={busy} onClick={() => loadDetail(selected.registration_id)}>查詢原申請處理結果</button>}
          {selected.status !== 'pending' && <p>{statuses[selected.status]}</p>}
        </footer>
      </section> : <div className="registration-applications__placeholder">
        <h3>查看申請內容</h3>
        <p>選擇一筆需求申請，確認填寫內容後再核准；或由右上角「手動新增非市民案件」補齊歷史案件。</p>
      </div>}
    </div>

    {/* Manual Creation Modal */}
    {showManualModal && <div className="manual-case-overlay" role="dialog" aria-modal="true" aria-labelledby="manual-case-title">
      <div className="manual-case-modal">
        <header className="manual-case-modal__header">
          <h3 id="manual-case-title">手動新增非市民案件（補齊歷史案件）</h3>
          <button type="button" className="manual-case-modal__close" onClick={() => { if (!manualBusy) setShowManualModal(false); }}>✕</button>
        </header>

        {manualError && <p className="manual-case-modal__error" role="alert">{manualError}</p>}

        <form onSubmit={e => { e.preventDefault(); void handleManualSubmit(false); }} className="manual-case-form">
          <div className="manual-case-section">
            <h4>1. 基本身分與專屬帳號</h4>
            <div className="manual-case-grid">
              <label>
                <span className="required">案件編號</span>
                <input
                  type="text"
                  required
                  placeholder="例如 A113001"
                  value={manualForm.case_no}
                  onChange={e => handleCaseNoChange(e.target.value)}
                  disabled={manualBusy}
                />
                <small className="hint">非市民格式通常為 A + 民國年3碼 + 序號3碼</small>
              </label>

              <label>
                <span className="required">專屬虛擬帳號（14碼）</span>
                <div className="virtual-account-input-group">
                  <input
                    type="text"
                    required
                    maxLength={14}
                    placeholder="99781699 開頭之 14 碼"
                    value={manualForm.virtual_account}
                    onChange={e => {
                      setManualForm(prev => ({ ...prev, virtual_account: e.target.value.trim() }));
                      setManualAccountStatus('');
                      setConflictResult(null);
                    }}
                    disabled={manualBusy}
                  />
                  <button type="button" className="small-btn" onClick={() => void handleCheckAccount()} disabled={manualBusy}>
                    檢查重複
                  </button>
                </div>
                {manualAccountStatus && <small className="account-status">{manualAccountStatus}</small>}
              </label>

              <label>
                <span className="required">客戶姓名</span>
                <input
                  type="text"
                  required
                  placeholder="姓名"
                  value={manualForm.name}
                  onChange={e => setManualForm(prev => ({ ...prev, name: e.target.value }))}
                  disabled={manualBusy}
                />
              </label>

              <label>
                <span className="required">連絡電話</span>
                <input
                  type="text"
                  required
                  placeholder="手機或市話"
                  value={manualForm.phone}
                  onChange={e => setManualForm(prev => ({ ...prev, phone: e.target.value }))}
                  disabled={manualBusy}
                />
              </label>

              <label>
                <span>性別</span>
                <select
                  value={manualForm.gender}
                  onChange={e => setManualForm(prev => ({ ...prev, gender: e.target.value }))}
                  disabled={manualBusy}
                >
                  <option value="女">女</option>
                  <option value="男">男</option>
                </select>
              </label>

              <label>
                <span>身分資格</span>
                <input type="text" readOnly value="非市民" disabled className="readonly-input" />
              </label>
            </div>
          </div>

          <div className="manual-case-section">
            <h4>2. 服務條件設定</h4>
            <div className="manual-case-grid">
              <label>
                <span className="required">預計服務開始日</span>
                <input
                  type="date"
                  required
                  value={manualForm.service_start_date}
                  onChange={e => setManualForm(prev => ({ ...prev, service_start_date: e.target.value }))}
                  disabled={manualBusy}
                />
              </label>

              <label>
                <span className="required">服務天數</span>
                <input
                  type="number"
                  required
                  min={1}
                  value={manualForm.service_days}
                  onChange={e => setManualForm(prev => ({ ...prev, service_days: parseInt(e.target.value, 10) || 1 }))}
                  disabled={manualBusy}
                />
              </label>

              <label className="full-width">
                <span className="required">服務時段</span>
                <input
                  type="text"
                  required
                  placeholder="例如 09:00-18:00 (8小時)"
                  value={manualForm.service_time}
                  onChange={e => setManualForm(prev => ({ ...prev, service_time: e.target.value }))}
                  disabled={manualBusy}
                />
                <div className="preset-buttons">
                  <span>常用範本：</span>
                  <button type="button" onClick={() => setManualForm(prev => ({ ...prev, service_time: '09:00-18:00 (8小時)' }))}>8小時 (09-18)</button>
                  <button type="button" onClick={() => setManualForm(prev => ({ ...prev, service_time: '08:00-17:00 (8小時)' }))}>8小時 (08-17)</button>
                  <button type="button" onClick={() => setManualForm(prev => ({ ...prev, service_time: '09:00-13:00 (4小時)' }))}>4小時上午</button>
                  <button type="button" onClick={() => setManualForm(prev => ({ ...prev, service_time: '13:00-17:00 (4小時)' }))}>4小時下午</button>
                  <button type="button" onClick={() => setManualForm(prev => ({ ...prev, service_time: '20:00-08:00 (9小時次日)' }))}>9小時夜間</button>
                </div>
              </label>

              <label>
                <span>預計服務結束日（選填）</span>
                <input
                  type="date"
                  value={manualForm.service_end_date ?? ''}
                  placeholder="留空將自動由天數計算"
                  onChange={e => setManualForm(prev => ({ ...prev, service_end_date: e.target.value || null }))}
                  disabled={manualBusy}
                />
                <small className="hint">若留空，系統將依天數與休假規則自動推算</small>
              </label>

              <label>
                <span>服務方式</span>
                <select
                  value={manualForm.service_type}
                  onChange={e => setManualForm(prev => ({ ...prev, service_type: e.target.value }))}
                  disabled={manualBusy}
                >
                  <option value="連續服務">連續服務</option>
                  <option value="週休1日">週休1日</option>
                  <option value="週休2日">週休2日</option>
                </select>
              </label>

              <label>
                <span>生產方式</span>
                <select
                  value={manualForm.delivery_type}
                  onChange={e => setManualForm(prev => ({ ...prev, delivery_type: e.target.value }))}
                  disabled={manualBusy}
                >
                  <option value="自然產">自然產</option>
                  <option value="剖腹產">剖腹產</option>
                </select>
              </label>

              <label>
                <span>居住型態</span>
                <select
                  value={manualForm.residence_type}
                  onChange={e => setManualForm(prev => ({ ...prev, residence_type: e.target.value }))}
                  disabled={manualBusy}
                >
                  <option value="電梯大樓">電梯大樓</option>
                  <option value="公寓">公寓</option>
                  <option value="透天">透天</option>
                  <option value="其他">其他</option>
                </select>
              </label>

              <label>
                <span>服務縣市</span>
                <input
                  type="text"
                  placeholder="例如 台北市"
                  value={manualForm.city ?? ''}
                  onChange={e => setManualForm(prev => ({ ...prev, city: e.target.value }))}
                  disabled={manualBusy}
                />
              </label>

              <label className="full-width">
                <span>詳細服務地址</span>
                <input
                  type="text"
                  placeholder="地址"
                  value={manualForm.address ?? ''}
                  onChange={e => setManualForm(prev => ({ ...prev, address: e.target.value }))}
                  disabled={manualBusy}
                />
              </label>

              <label className="checkbox-label full-width">
                <input
                  type="checkbox"
                  checked={manualForm.requires_cooking ?? false}
                  onChange={e => setManualForm(prev => ({ ...prev, requires_cooking: e.target.checked }))}
                  disabled={manualBusy}
                />
                <span>是否需要下廚</span>
              </label>
            </div>
          </div>

          <div className="manual-case-section">
            <h4>3. 其他自訂欄位（選填）</h4>
            <div className="manual-case-grid">
              <label>
                <span>寶寶資訊</span>
                <input
                  type="text"
                  placeholder="例如 單胞胎"
                  value={manualForm.baby_info ?? ''}
                  onChange={e => setManualForm(prev => ({ ...prev, baby_info: e.target.value }))}
                  disabled={manualBusy}
                />
              </label>

              <label>
                <span>預產期／月份</span>
                <input
                  type="text"
                  placeholder="例如 2024-05"
                  value={manualForm.due_month ?? ''}
                  onChange={e => setManualForm(prev => ({ ...prev, due_month: e.target.value }))}
                  disabled={manualBusy}
                />
              </label>

              <label>
                <span>客戶生日</span>
                <input
                  type="date"
                  value={manualForm.birth_date ?? ''}
                  onChange={e => setManualForm(prev => ({ ...prev, birth_date: e.target.value }))}
                  disabled={manualBusy}
                />
              </label>

              <label>
                <span>電子郵件</span>
                <input
                  type="email"
                  placeholder="Email"
                  value={manualForm.email ?? ''}
                  onChange={e => setManualForm(prev => ({ ...prev, email: e.target.value }))}
                  disabled={manualBusy}
                />
              </label>

              <label>
                <span>LINE ID</span>
                <input
                  type="text"
                  placeholder="LINE ID"
                  value={manualForm.line_id ?? ''}
                  onChange={e => setManualForm(prev => ({ ...prev, line_id: e.target.value }))}
                  disabled={manualBusy}
                />
              </label>

              <label>
                <span>退款銀行代號（7碼）</span>
                <input
                  type="text"
                  maxLength={7}
                  placeholder="0000000"
                  value={manualForm.refund_bank_code ?? ''}
                  onChange={e => setManualForm(prev => ({ ...prev, refund_bank_code: e.target.value }))}
                  disabled={manualBusy}
                />
              </label>

              <label>
                <span>退款銀行帳號</span>
                <input
                  type="text"
                  placeholder="銀行帳號"
                  value={manualForm.refund_account_no ?? ''}
                  onChange={e => setManualForm(prev => ({ ...prev, refund_account_no: e.target.value }))}
                  disabled={manualBusy}
                />
              </label>

              <label className="full-width">
                <span>案件備註</span>
                <textarea
                  rows={2}
                  placeholder="歷史補登或案件註記"
                  value={manualForm.notes ?? ''}
                  onChange={e => setManualForm(prev => ({ ...prev, notes: e.target.value }))}
                  disabled={manualBusy}
                />
              </label>
            </div>
          </div>

          <footer className="manual-case-modal__footer">
            <button type="button" onClick={() => setShowManualModal(false)} disabled={manualBusy}>
              取消
            </button>
            <button type="submit" className="primary-btn" disabled={manualBusy}>
              {manualBusy ? '處理中…' : '確認建立歷史非市民案件'}
            </button>
          </footer>
        </form>

        {/* Conflict Decision Dialog */}
        {conflictResult && conflictResult.conflict && <div className="conflict-dialog-backdrop">
          <div className="conflict-dialog-box" role="alertdialog" aria-labelledby="conflict-dialog-title">
            <h4 id="conflict-dialog-title">⚠️ 虛擬帳號重複確認</h4>
            <div className="conflict-dialog-content">
              <p>虛擬帳號 <strong>{conflictResult.virtual_account}</strong> 目前已被以下案件使用：</p>
              <ul className="conflict-case-info">
                <li><strong>案件編號：</strong>{conflictResult.conflict_case_no}</li>
                <li><strong>客戶姓名：</strong>{conflictResult.conflict_case_client_name || '未填寫'}</li>
                <li><strong>案件狀態：</strong>{conflictResult.conflict_case_status}</li>
                <li>
                  <strong>帳務狀況：</strong>
                  <span className={conflictResult.has_accounting_details ? 'text-danger' : 'text-safe'}>
                    {conflictResult.accounting_description}
                  </span>
                </li>
                {conflictResult.cancel_reason && <li><strong>取消原因：</strong>{conflictResult.cancel_reason}</li>}
              </ul>
              <div className="conflict-explanation">
                <p><strong>說明：</strong>歷史案件可能會頂替某個被取消、沒有帳務明細的案件。請手動決定誰要覆蓋誰：</p>
              </div>
            </div>
            <div className="conflict-dialog-actions">
              <button
                type="button"
                className="btn-danger"
                disabled={manualBusy}
                onClick={() => void handleManualSubmit(true)}
              >
                【由本案件覆蓋原案件】解除原案件綁定並由本歷史案件使用
              </button>
              <button
                type="button"
                disabled={manualBusy}
                onClick={() => setConflictResult(null)}
              >
                【保留原案件】返回修改本案件虛擬帳號
              </button>
            </div>
          </div>
        </div>}
      </div>
    </div>}
  </section>;
}
