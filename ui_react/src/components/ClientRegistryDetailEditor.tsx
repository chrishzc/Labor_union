import React, { useEffect, useMemo, useRef, useState } from 'react';
import { clientRegistryClient } from '../api/client_registry/client_registry_client';
import type { BeClassChanges, ClientProfileChanges, ClientRegistryChangeHistoryItem, ClientRegistryDetail, RegistryMutationPreview } from '../api/client_registry/client_registry_schemas';
import { ApiHttpError } from '../api/shared/typed_errors';
import { OrderTermsMutationPanel } from './OrderTermsMutationPanel';
import { OrderIntakeRepairPanel } from './OrderIntakeRepairPanel';
import { OrderTermsUnavailableNote } from './OrderTermsUnavailableNote';
import { CaseArchitectureBootstrapRepairPanel } from './CaseArchitectureBootstrapRepairPanel';
import { ClientRegistryServiceStaff } from './ClientRegistryServiceStaff';
import { ClientRegistryVirtualAccount } from './ClientRegistryVirtualAccount';
import '../pages/ClientRegistryPage.css';

const profileLabels: Record<string, string> = { name: '姓名', gender: '性別', phone: '電話（手機／市話）', email: 'HCM Email', city: '縣市', address: '地址', due_month: '預產期／預計服務開始月份', reject_reason: '不符合原因', residence_type: '住宅型態', delivery_type: '生產方式', baby_info: '寶寶資訊', notes: '行政註記', service_type: '服務方式（排班參考）' };
const beclassLabels: Record<string, string> = { name: '報名姓名', email: 'BeClass Email', phone: '手機', tel: '市話', ext: '分機', city: '縣市', zip_code: '郵遞區號', address: '報名地址', admin_notes: '報名註記', multi_birth_count: '胎數（單胞胎／雙胞胎）' };
const careLabels: Record<string, string> = {
  dietary_habits: '飲食習慣與中藥接受度', vegetarian_preference: '可否接受蛋奶素餐食', alcohol_ratio: '餐飲含酒比例',
  cooking_oil_type: '料理用油', maternal_allergy: '過敏體質', special_care_notes: '特殊照護注意事項',
  meal_preferences: '餐點喜忌', cooking_tools: '現有烹煮工具', bath_water_prep: '洗澡水準備', breastfeeding_method: '哺乳方式',
  holiday_pricing_terms: '三節獎金協調結果', stair_floor_fee_mode: '服務樓層方式', parking_space_provided: '停車位', other_babies_present: '服務時間內的其他寶寶',
};
const financeLabels: Record<string, string> = {
  virtual_account: '本案專屬虛擬帳號', service_unit_price_ntd: '服務單價', service_hours: '服務總時數',
  customer_payable_total_ntd: '客戶應付總額', deposit_amount_ntd: '定金金額', first_payment_amount_ntd: '第一期金額',
  second_payment_amount_ntd: '第二期金額', received_total_ntd: '已入帳金額', customer_balance_ntd: '客戶待繳／應退差額',
  subsidy_return_amount_ntd: '補助退款金額', subsidy_return_due_date: '補助退款日期', subsidy_return_status: '補助退款狀態',
};
type Section = 'profile' | 'beclass' | 'care';
type Scalar = string | boolean | number | null;
type Draft = Record<string, Scalar>;
type Action = { preview: RegistryMutationPreview | null; changes: Draft; message: string; loading: boolean; key: string | null; applied: boolean; unknown: boolean };
const idle = (): Action => ({ preview: null, changes: {}, message: '', loading: false, key: null, applied: false, unknown: false });
const labels = { profile: profileLabels, beclass: beclassLabels, care: careLabels };
const title = { profile: '客戶主檔', beclass: '報名問卷資料（BeClass）', care: 'BeClass 照護與特殊計費' };
const owner = (section: Section) => section === 'profile' ? 'profile' : 'beclass';
const source = (detail: ClientRegistryDetail, section: Section): Draft => section === 'profile'
  ? detail.client.values : section === 'beclass' ? detail.beclass.values ?? {} : detail.order_information.values ?? {};
const display = (value: Scalar | undefined) => value === null || value === undefined || value === '' ? '未登錄' : typeof value === 'boolean' ? value ? '是' : '否' : String(value);
const diff = (draft: Draft, values: Draft, section: Section): Draft => Object.fromEntries(Object.keys(labels[section])
  .filter((field) => (draft[field] === '' ? null : draft[field] ?? null) !== (values[field] === '' ? null : values[field] ?? null))
  .map((field) => [field, draft[field] === '' ? null : draft[field] ?? null]));
const reason = (section: Section) => section === 'profile' ? '後台客戶名冊主檔更新' : section === 'care' ? '後台客戶名冊照護與獎金協調紀錄更新' : '後台客戶名冊 報名問卷資料（BeClass）更新';
const errorText = (error: unknown) => error instanceof ApiHttpError ? `${error.message}（${error.code}）` : error instanceof Error ? error.message : '操作失敗，請重新確認。';

const ClientChangeHistory: React.FC<{ detail: ClientRegistryDetail }> = ({ detail }) => {
  const [items, setItems] = useState<ClientRegistryChangeHistoryItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    let active = true;
    setItems(null); setLoading(true); setError('');
    void clientRegistryClient.history(detail.case_no).then((history) => {
      if (active) setItems(history);
    }).catch((caught) => {
      if (active) setError(errorText(caught));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [detail, retry]);
  return <section className="registry-editor registry-history-panel" aria-label="變更歷程">
    <details onToggle={(event) => setExpanded(event.currentTarget.open)}>
      <summary className="registry-history-toggle" tabIndex={0}><h3>變更歷程<small>{loading ? '載入中' : error ? '讀取失敗' : `共 ${items?.length ?? 0} 筆`}</small></h3></summary>
      <div className="registry-history-scroll" role="region" aria-label="變更歷程紀錄" tabIndex={expanded ? 0 : -1}>
    {loading && <p role="status">正在載入變更歷程…</p>}
    {error && <div role="alert"><p>變更歷程讀取失敗：{error}</p><button type="button" disabled={!expanded} onClick={() => setRetry((value) => value + 1)}>重新讀取變更歷程</button></div>}
    {!loading && !error && items?.length === 0 && <p role="status">此案件目前沒有已記錄的變更原因。</p>}
    {items && items.length > 0 && <ol className="registry-history">{items.map((item) => <li key={`${item.event_type}-${item.sequence}`}>
      <div><strong>{item.sequence}. {item.label}</strong><time dateTime={item.occurred_at}>{new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Taipei' }).format(new Date(item.occurred_at))}</time></div>
      <p>{item.reason}</p><small>操作人員：{item.actor}</small>
    </li>)}</ol>}
      </div>
    </details>
  </section>;
};

export interface RegistryEditState { dirty: boolean; busy: boolean }
interface Props {
  detail: ClientRegistryDetail;
  focusField?: string;
  onRefresh: () => Promise<ClientRegistryDetail>;
  onStateChange: (state: RegistryEditState) => void;
  onOpenServiceArrangement?: (recalculateDates: boolean) => void;
}

export const ClientRegistryDetailEditor: React.FC<Props> = ({ detail, focusField = '', onRefresh, onStateChange, onOpenServiceArrangement }) => {
  const [drafts, setDrafts] = useState<Record<Section, Draft>>(() => ({ profile: { ...source(detail, 'profile') }, beclass: { ...source(detail, 'beclass') }, care: { ...source(detail, 'care') } }));
  const [actions, setActions] = useState<Record<Section, Action>>({ profile: idle(), beclass: idle(), care: idle() });
  const [termsState, setTermsState] = useState<RegistryEditState>({ dirty: false, busy: false });
  const [intakeNeeded, setIntakeNeeded] = useState(true);
  const [intakeState, setIntakeState] = useState<RegistryEditState>({ dirty: false, busy: false });
  const [intakeOpened, setIntakeOpened] = useState(() => focusField === 'intake' || ['order_terms_service_hours_per_day_required', 'order_terms_start_date_required', 'order_terms_service_days_required'].includes(detail.order_terms.code ?? ''));
  const [repairState, setRepairState] = useState<RegistryEditState>({ dirty: false, busy: false });
  const [staffState, setStaffState] = useState<RegistryEditState>({ dirty: false, busy: false });
  const [accountState, setAccountState] = useState<RegistryEditState>({ dirty: false, busy: false });
  const [refreshError, setRefreshError] = useState('');
  const previous = useRef(detail);
  const alive = useRef(true);
  const request = useRef(0);
  useEffect(() => { alive.current = true; return () => { alive.current = false; ++request.current; }; }, []);
  useEffect(() => {
    const old = previous.current;
    previous.current = detail;
    setDrafts((current) => Object.fromEntries((['profile', 'beclass', 'care'] as const).map((section) => {
      const oldValues = source(old, section);
      const nextValues = source(detail, section);
      return [section, { ...nextValues, ...Object.fromEntries(Object.keys(labels[section]).filter((field) =>
        (current[section][field] ?? null) !== (oldValues[field] ?? null)).map((field) => [field, current[section][field]])) }];
    })) as Record<Section, Draft>);
    const invalidate = (action: Action): Action => ({
      ...action, preview: null, changes: {}, key: null,
      message: action.preview && !action.loading && !action.applied && !action.unknown ? '資料版本已更新，請重新預覽。' : action.message,
    });
    setActions((current) => ({
      profile: old.client.version === detail.client.version ? current.profile : invalidate(current.profile),
      beclass: old.beclass.version === detail.beclass.version ? current.beclass : invalidate(current.beclass),
      care: old.beclass.version === detail.beclass.version ? current.care : invalidate(current.care),
    }));
  }, [detail]);
  useEffect(() => {
    if (focusField) (document.getElementById(`registry-profile-${focusField}`) ?? document.getElementById(`registry-beclass-${focusField}`) ?? document.getElementById(`registry-care-${focusField}`))?.focus();
  }, [detail.case_no, focusField]);
  const changes = useMemo(() => ({ profile: diff(drafts.profile, source(detail, 'profile'), 'profile'), beclass: diff(drafts.beclass, source(detail, 'beclass'), 'beclass'), care: diff(drafts.care, source(detail, 'care'), 'care') }), [drafts, detail]);
  const pending = Object.values(actions).some((action) => action.loading || action.applied || action.unknown) || repairState.busy || staffState.busy || intakeState.busy || accountState.busy;
  const dirty = Object.values(changes).some((value) => Object.keys(value).length > 0) || termsState.dirty || repairState.dirty || staffState.dirty || intakeState.dirty || accountState.dirty;
  useEffect(() => { onStateChange({ dirty, busy: pending || termsState.busy }); }, [dirty, pending, termsState.busy, onStateChange]);
  const update = (section: Section, field: string, value: Scalar) => {
    setDrafts((current) => ({ ...current, [section]: { ...current[section], [field]: value } }));
    setActions((current) => ({ ...current, [section]: idle() }));
  };
  const refresh = async (section: Section, sequence: number) => {
    try {
      const result = await onRefresh();
      if (!alive.current || sequence !== request.current) return;
      setDrafts((current) => ({ ...current, [section]: { ...source(result, section) } }));
      setActions((current) => ({ ...current, [section]: { ...idle(), message: `${title[section]}已儲存。` } }));
    } catch (error) {
      if (alive.current && sequence === request.current) setActions((current) => ({ ...current, [section]: { ...current[section], applied: true, loading: false, message: `已儲存，但最新資料讀取失敗：${errorText(error)}` } }));
    }
  };
  const preview = async (section: Section) => {
    if (!Object.keys(changes[section]).length) {
      setActions((current) => ({ ...current, [section]: { ...idle(), message: '沒有需要儲存的變更。' } })); return;
    }
    const sequence = ++request.current;
    const submitted = changes[section];
    setActions((current) => ({ ...current, [section]: { ...idle(), loading: true, message: '正在產生預覽…' } }));
    try {
      const result = await clientRegistryClient.preview(detail.case_no, owner(section), submitted as ClientProfileChanges | BeClassChanges, section === 'profile' ? detail.client.version : detail.beclass.version ?? 0);
      if (!alive.current || sequence !== request.current) return;
      setActions((current) => ({ ...current, [section]: { ...idle(), preview: result, changes: submitted, key: `client-${owner(section)}-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`, message: '請核對修改前後的資料，再確認儲存。' } }));
    } catch (error) {
      if (alive.current && sequence === request.current) setActions((current) => ({ ...current, [section]: { ...idle(), message: errorText(error) } }));
    }
  };
  const apply = async (section: Section) => {
    const approved = actions[section];
    if (!approved.preview || !approved.key) return;
    const sequence = ++request.current;
    setActions((current) => ({ ...current, [section]: { ...approved, loading: true, message: '正在儲存…' } }));
    try {
      await clientRegistryClient.apply(detail.case_no, owner(section), approved.changes as ClientProfileChanges | BeClassChanges, approved.preview.current_version, approved.preview.preview_fingerprint, reason(section), approved.key);
      if (!alive.current || sequence !== request.current) return;
      setActions((current) => ({ ...current, [section]: { ...current[section], applied: true, unknown: false, message: '已儲存，正在讀取最新資料…' } }));
      await refresh(section, sequence);
    } catch (error) {
      if (alive.current && sequence === request.current) setActions((current) => ({ ...current, [section]: { ...approved, loading: false, unknown: !(error instanceof ApiHttpError) || error.status >= 500, message: `${errorText(error)} 請核對結果；重試使用同一筆操作識別。` } }));
    }
  };
  const renderSection = (section: Section) => {
    const action = actions[section];
    const capabilities = section === 'profile' ? detail.client.field_capabilities : detail.beclass.field_capabilities;
    const unavailable = section !== 'profile' && detail.beclass.status !== 'ready';
    return <section className="registry-editor" aria-label={title[section]}>
      <h3>{title[section]}</h3>
      <small>資料來源：{section === 'profile' ? '客戶主檔' : detail.beclass.source_kind === 'admin_manual' ? '後台人工補登（無 BeClass 匯入紀錄）' : 'BeClass 有效修正資料；保留原始匯入內容'}</small>
      {unavailable ? <p>{detail.beclass.status === 'duplicate_binding' ? '同一案件綁定多筆 BeClass，請先處理綁定異常。' : '此案件尚無可編輯的 BeClass 資料。'}</p> : <>
        {section === 'care' && <p className="registry-section-note">三節欄位記錄客戶給月嫂的獎金協調結果；樓層費總額請在下方訂單條件登錄。</p>}
        <div className="registry-fields">{Object.entries(labels[section]).map(([field, label]) => {
          const value = drafts[section][field] ?? '';
          const capability = capabilities[field];
          const options = capability?.options;
          const disabled = pending || termsState.busy || capability?.editable === false;
          const id = `registry-${section === 'care' ? 'care' : owner(section)}-${field}`;
          const textAgreement = field === 'holiday_pricing_terms' || field === 'stair_floor_fee_mode';
          const control = options ? <select id={id} disabled={disabled} value={String(value)} onChange={(event) => update(section, field, event.target.value)}>
            <option value="" disabled>請選擇</option>{value && !options.includes(String(value)) && <option value={String(value)} disabled>{String(value)}（既有值，待修正）</option>}{options.map((option) => <option key={option}>{option}</option>)}
          </select> : typeof source(detail, section)[field] === 'boolean' && !textAgreement ? <select id={id} value={value === '' || value === null ? '' : String(value)} disabled={disabled} onChange={(event) => update(section, field, event.target.value === '' ? null : event.target.value === 'true')}><option value="">未登錄</option><option value="true">是</option><option value="false">否</option></select>
            : typeof source(detail, section)[field] === 'number' && !textAgreement ? <input id={id} type="number" disabled={disabled} value={String(value)} onChange={(event) => update(section, field, event.target.value === '' ? null : Number(event.target.value))} />
            : section === 'care' || ['notes', 'baby_info', 'admin_notes', 'reject_reason'].includes(field)
              ? <textarea id={id} disabled={disabled} rows={2} maxLength={field === 'reject_reason' ? 500 : 2000} value={textAgreement && typeof value !== 'string' ? display(value) : String(value)} onChange={(event) => update(section, field, event.target.value)} />
              : <input id={id} disabled={disabled} type={field === 'email' ? 'email' : field === 'due_month' ? 'date' : 'text'} maxLength={field === 'email' || field === 'service_type' ? 100 : undefined} value={String(value)} onChange={(event) => update(section, field, event.target.value)} />;
          return <label key={field} htmlFor={id}>{label}{control}{capability?.editable === false && <small>{capability.reason === 'multi_birth_count_locked_after_service_start' ? '服務已開始，胎數會影響費率，不能在此直接修改。' : '此欄位目前不可修改。'}</small>}{section === 'care' && detail.order_information.field_issues[field] && <small className="source-issue">來源內容無法判定，請核對後補登。</small>}</label>;
        })}</div>
        <div className="registry-actions">
          <button type="button" disabled={pending || termsState.busy} onClick={() => { setDrafts((current) => ({ ...current, [section]: { ...source(detail, section) } })); setActions((current) => ({ ...current, [section]: idle() })); }}>取消變更</button>
          <button type="button" disabled={pending || termsState.busy} onClick={() => void preview(section)}>預覽變更</button>
          <button type="button" disabled={pending || termsState.busy || !action.preview} onClick={() => void apply(section)}>確認儲存</button>
          {action.applied && !action.loading && <button type="button" onClick={() => { const sequence = ++request.current; setActions((current) => ({ ...current, [section]: { ...current[section], loading: true } })); void refresh(section, sequence); }}>重新讀取已儲存資料</button>}
          {action.unknown && !action.loading && <button type="button" onClick={() => void apply(section)}>確認同一筆儲存結果</button>}
        </div>
        {action.preview && <div className="registry-preview"><strong>即將變更：</strong><dl>{Object.keys(action.preview.after).map((field) => <div key={field}><dt>{labels[section][field] ?? field}</dt><dd>{display(action.preview!.before[field])} → {display(action.preview!.after[field])}</dd></div>)}</dl></div>}
        {action.message && <p role="status">{action.message}</p>}
      </>}
    </section>;
  };
  const bootstrapRequired = ['client_finance_bootstrap_required', 'order_terms_start_date_required', 'order_terms_service_days_required'].includes(detail.order_terms.code ?? '') || detail.finance.code === 'client_finance_bootstrap_required';
  const refreshRelated = async () => {
    try { await onRefresh(); setRefreshError(''); }
    catch (error) { setRefreshError(`最新案件資料讀取失敗：${errorText(error)}`); }
  };
  const refreshIntake = async () => {
    await onRefresh();
    setRefreshError('');
  };
  return <div className="client-registry-page client-registry-detail-editor" aria-label={`${detail.case_no} 案件資料編輯`}>
    {refreshError && <p role="alert">{refreshError}<button type="button" onClick={() => void refreshRelated()}>重新讀取案件資料</button></p>}
    {renderSection('profile')}
    {renderSection('beclass')}{renderSection('care')}
    <section id="registry-order-terms" className="registry-editor"><h3>目前訂單條件</h3><p>服務方式（排班參考）：{detail.service_type ?? '尚未登錄'}</p>
      <fieldset disabled={pending && !intakeState.busy} className="registry-terms-fieldset">{intakeOpened ? <OrderIntakeRepairPanel caseNo={detail.case_no} repairServiceTime registry focusMissing={focusField === 'intake'} onChanged={refreshIntake} onEditStateChange={setIntakeState} onNeedsRepair={setIntakeNeeded} /> : detail.order_terms.status === 'ready' && detail.order_terms.data
        ? <OrderTermsMutationPanel caseNo={detail.case_no} query={detail.order_terms.data} onObserved={() => { void refreshRelated(); }} onEditStateChange={setTermsState} />
        : <OrderTermsUnavailableNote caseNo={detail.case_no} code={detail.order_terms.code} />}
      </fieldset>{bootstrapRequired && (!intakeOpened || !intakeNeeded) && <fieldset disabled={Object.values(actions).some((action) => action.loading || action.applied || action.unknown) || termsState.busy || intakeState.busy || accountState.busy} className="registry-terms-fieldset"><CaseArchitectureBootstrapRepairPanel caseNo={detail.case_no} onCompleted={async () => { await onRefresh(); }} onEditStateChange={setRepairState} /></fieldset>}
      {intakeOpened && !intakeNeeded && detail.order_terms.status === 'ready' && <button type="button" disabled={pending || intakeState.dirty} onClick={() => setIntakeOpened(false)}>編輯完整服務條件</button>}
    </section>
    <ClientRegistryVirtualAccount caseNo={detail.case_no} disabled={Object.values(actions).some(action => action.loading || action.applied || action.unknown) || termsState.busy || repairState.busy || staffState.busy || intakeState.busy} onRefresh={onRefresh} onStateChange={setAccountState} />
    <section className="registry-editor"><h3>客戶帳務（唯讀）</h3>{detail.finance.status === 'ready' && detail.finance.values
      ? <dl className="registry-information-fields">{Object.entries(financeLabels).map(([field, label]) => <div key={field}><dt>{label}</dt><dd>{display(detail.finance.values![field as keyof typeof detail.finance.values])}</dd></div>)}</dl>
      : <><p>{detail.finance.code === 'client_finance_bootstrap_required' ? '尚未建立客戶帳務資料。' : '客戶帳務暫時無法讀取，請重新整理。'}</p>{detail.finance.code && <details><summary>技術資訊</summary><code>{detail.finance.code}</code></details>}</>}</section>
    <ClientRegistryServiceStaff key={detail.case_no} caseNo={detail.case_no} revision={detail} disabled={Object.values(actions).some((action) => action.loading || action.applied || action.unknown) || termsState.busy || repairState.busy || intakeState.busy || accountState.busy} onCommitted={refreshRelated} onStateChange={setStaffState} onOpenServiceArrangement={onOpenServiceArrangement} />
    <ClientChangeHistory detail={detail} />
  </div>;
};
