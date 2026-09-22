import React, { useEffect, useMemo, useState } from 'react';
import { clientRegistryClient } from '../api/client_registry/client_registry_client';
import type { BeClassChanges, ClientProfileChanges, ClientRegistryChangeHistoryItem, ClientRegistryDetail, ClientRegistryPage as ClientRegistryPageData, RegistryMutationPreview } from '../api/client_registry/client_registry_schemas';
import { ApiHttpError } from '../api/shared/typed_errors';
import { OrderTermsMutationPanel } from '../components/OrderTermsMutationPanel';
import { CaseArchitectureBootstrapRepairPanel } from '../components/CaseArchitectureBootstrapRepairPanel';
import { LegacyVirtualAccountImport } from '../components/LegacyVirtualAccountImport';
import { ClientRosterPage } from './ClientRosterPage';
import './ClientRegistryPage.css';

const profileLabels: Record<string, string> = { name: '姓名', gender: '性別', phone: '手機', city: '縣市', address: '地址', residence_type: '住宅型態', delivery_type: '生產方式', baby_info: '寶寶資訊', notes: '行政註記' };
const beclassLabels: Record<string, string> = { name: '報名姓名', email: 'Email', phone: '手機', tel: '市話', ext: '分機', city: '縣市', zip_code: '郵遞區號', address: '報名地址', admin_notes: '報名註記', multi_birth_count: '胎數（單胞胎／雙胞胎）' };
const orderInformationLabels = {
  dietary_habits: '飲食習慣與中藥接受度',
  vegetarian_preference: '可否接受蛋奶素餐食',
  alcohol_ratio: '餐飲含酒比例',
  cooking_oil_type: '料理用油',
  maternal_allergy: '過敏體質',
  special_care_notes: '特殊照護注意事項',
  meal_preferences: '餐點喜忌',
  cooking_tools: '現有烹煮工具',
  bath_water_prep: '洗澡水準備',
  breastfeeding_method: '哺乳方式',
  holiday_pricing_terms: '三節計費約定',
  stair_floor_fee_mode: '服務樓層方式',
  parking_space_provided: '停車位',
  other_babies_present: '服務時間內的其他寶寶',
} as const;

type Owner = 'profile' | 'beclass';
type Draft = Record<string, string>;
type Action = { preview: RegistryMutationPreview | null; message: string | null; loading: boolean; idempotencyKey: string | null };
const initialAction: Action = { preview: null, message: null, loading: false, idempotencyKey: null };
const toDraft = (values: Record<string, string | null> | null): Draft => Object.fromEntries(Object.entries(values ?? {}).map(([field, value]) => [field, value ?? '']));
const mutationKey = (owner: Owner) => `client-${owner}-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
const auditReason = (owner: Owner) => owner === 'profile' ? '後台客戶名冊主檔更新' : '後台客戶名冊 BeClass 有效資料更新';
const mutationErrorMessage = (error: unknown, fallback: string) => error instanceof ApiHttpError
  ? `${error.message}（${error.code}）`
  : error instanceof Error ? error.message : fallback;
const displayOrderInformationValue = (value: string | boolean | number | null) => {
  if (value === null || value === '') return '未登錄';
  if (typeof value === 'boolean') return value ? '是' : '否';
  return String(value);
};

const OrderInformationSection: React.FC<{ detail: ClientRegistryDetail }> = ({ detail }) => {
  const section = detail.order_information;
  if (section.status !== 'ready' || !section.values) {
    return <section className="registry-editor"><h3>照護與特殊計費資料</h3><p>{section.status === 'duplicate_binding' ? '同一案件綁定多筆 BeClass，無法判定訂單資訊來源。' : '此案件尚未綁定 BeClass 紀錄，沒有可顯示的訂單資訊。'}</p></section>;
  }
  return <section className="registry-editor"><h3>照護與特殊計費資料</h3><small>資料來源：{detail.beclass.source_kind === 'admin_manual' ? '後台人工補登（目前未登錄的欄位顯示為空）' : 'BeClass 原始訂單資訊（唯讀）'}</small><dl className="registry-information-fields">{Object.entries(orderInformationLabels).map(([field, label]) => <div key={field}><dt>{label}</dt><dd className={section.field_issues[field] ? 'source-issue' : undefined}>{section.field_issues[field] ? '來源內容無法判定' : displayOrderInformationValue(section.values?.[field as keyof typeof section.values] ?? null)}</dd></div>)}</dl></section>;
};

const ClientRegistryEditor: React.FC = () => {
  const [query, setQuery] = useState('');
  const [page, setPage] = useState<ClientRegistryPageData | null>(null);
  const [detail, setDetail] = useState<ClientRegistryDetail | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [profileDraft, setProfileDraft] = useState<Draft>({});
  const [beclassDraft, setBeclassDraft] = useState<Draft>({});
  const [actions, setActions] = useState<Record<Owner, Action>>({ profile: initialAction, beclass: initialAction });
  const [message, setMessage] = useState('正在載入客戶名冊…');

  const loadList = async (search = query) => {
    setMessage('正在載入客戶名冊…');
    try {
      const items: ClientRegistryPageData['items'] = [];
      let after: string | undefined;
      do {
        const result = await clientRegistryClient.list({ query: search, sortBy: 'case_no', sortOrder: 'asc', limit: 100, after });
        items.push(...result.items);
        if (result.next_cursor === after) throw new Error('客戶名冊分頁資料異常，請稍後重試。');
        after = result.next_cursor ?? undefined;
      } while (after);
      setPage({ items, next_cursor: null }); setMessage(items.length ? '' : '查無符合條件的案件。');
    } catch (error) { setMessage(error instanceof Error ? error.message : '客戶名冊載入失敗。'); }
  };
  useEffect(() => { void loadList(''); }, []);
  const loadDetail = async (caseNo: string) => {
    setSelected(caseNo); setDetail(null); setMessage('正在載入案件詳情…');
    try {
      const result = await clientRegistryClient.query(caseNo);
      setDetail(result); setProfileDraft(toDraft(result.client.values)); setBeclassDraft(toDraft(result.beclass.values));
      setActions({ profile: initialAction, beclass: initialAction }); setMessage('');
    } catch (error) { setMessage(error instanceof Error ? error.message : '案件詳情載入失敗。'); }
  };
  const changed = useMemo(() => ({
    profile: detail ? Object.fromEntries(Object.entries(profileDraft).filter(([field, value]) => value !== (detail.client.values[field as keyof typeof detail.client.values] ?? '')).map(([field, value]) => [field, value || null])) : {},
    beclass: detail?.beclass.values ? Object.fromEntries(Object.entries(beclassDraft).filter(([field, value]) => value !== (detail.beclass.values?.[field as keyof typeof detail.beclass.values] ?? '')).map(([field, value]) => [field, value || null])) : {},
  }), [detail, profileDraft, beclassDraft]);
  const preview = async (owner: Owner) => {
    if (!detail) return;
    const changes = changed[owner] as ClientProfileChanges | BeClassChanges;
    if (!Object.keys(changes).length) { setActions((value) => ({ ...value, [owner]: { ...initialAction, message: '沒有需要儲存的變更。' } })); return; }
    setActions((value) => ({ ...value, [owner]: { preview: null, message: '正在產生預覽…', loading: true, idempotencyKey: null } }));
    try {
      const version = owner === 'profile' ? detail.client.version : detail.beclass.version ?? 0;
      const result = await clientRegistryClient.preview(detail.case_no, owner, changes, version);
      setActions((value) => ({ ...value, [owner]: { preview: result, message: '預覽完成，請核對後確認儲存。', loading: false, idempotencyKey: mutationKey(owner) } }));
    } catch (error) { setActions((value) => ({ ...value, [owner]: { preview: null, message: mutationErrorMessage(error, '預覽失敗。'), loading: false, idempotencyKey: null } })); }
  };
  const apply = async (owner: Owner) => {
    if (!detail) return;
    const action = actions[owner];
    const approvedPreview = action.preview;
    if (!approvedPreview || !action.idempotencyKey) return;
    setActions((value) => ({ ...value, [owner]: { ...action, message: '正在儲存…', loading: true } }));
    try {
      const version = owner === 'profile' ? detail.client.version : detail.beclass.version ?? 0;
      await clientRegistryClient.apply(detail.case_no, owner, changed[owner] as ClientProfileChanges | BeClassChanges, version, approvedPreview.preview_fingerprint, auditReason(owner), action.idempotencyKey);
      await loadDetail(detail.case_no);
      setMessage(owner === 'profile' ? '客戶主檔已儲存。' : detail.beclass.source_kind === 'admin_manual' ? '案件補登資料已儲存。' : 'BeClass 有效資料已儲存，原始匯入值未被覆寫。');
    } catch (error) { setActions((value) => ({ ...value, [owner]: { ...value[owner], message: mutationErrorMessage(error, '儲存結果未確認，可用相同預覽安全重試。'), loading: false } })); }
  };
  const editor = (owner: Owner, labels: Record<string, string>, draft: Draft, setDraft: React.Dispatch<React.SetStateAction<Draft>>) => {
    const action = actions[owner];
    const source = owner === 'profile' ? detail?.client.values : detail?.beclass.values;
    const capabilities = owner === 'profile' ? detail?.client.field_capabilities : detail?.beclass.field_capabilities;
    const update = (field: string, value: string) => {
      setDraft((current) => ({ ...current, [field]: value }));
      setActions((current) => ({ ...current, [owner]: initialAction }));
    };
    const sourceLabel = owner === 'profile'
      ? 'Client Profile owner'
      : detail?.beclass.source_kind === 'admin_manual'
        ? '後台人工補登（無 BeClass 匯入紀錄）'
        : 'Case Import / BeClass correction owner';
    return <section className="registry-editor"><h3>{owner === 'profile' ? '客戶主檔' : 'BeClass 有效資料'}</h3><small>資料來源：{sourceLabel}</small><div className="registry-fields">{Object.entries(labels).map(([field, label]) => {
      const options = capabilities?.[field]?.options ?? null;
      const editable = capabilities?.[field]?.editable ?? true;
      const lockedReason = capabilities?.[field]?.reason;
      const current = draft[field] ?? '';
      const legacyValue = options && current && !options.includes(current) ? current : null;
      return <label key={field}>{label}{options ? <select value={current} disabled={action.loading || !editable} onChange={(event) => update(field, event.target.value)}><option value="" disabled>請選擇</option>{legacyValue && <option value={legacyValue} disabled>{legacyValue}（既有值，待修正）</option>}{options.map((option) => <option key={option} value={option}>{option}</option>)}</select> : <input value={current} disabled={action.loading || !editable} onChange={(event) => update(field, event.target.value)} />}{!editable && <small>{lockedReason === 'multi_birth_count_locked_after_service_start' ? '服務已開始，胎數會影響費率，不能在此直接修改。' : '此欄位目前不可修改。'}</small>}</label>;
    })}</div><div className="registry-actions"><button type="button" disabled={action.loading} onClick={() => { setDraft(toDraft(source ?? null)); setActions((value) => ({ ...value, [owner]: initialAction })); }}>取消變更</button><button type="button" disabled={action.loading} onClick={() => void preview(owner)}>預覽變更</button><button type="button" disabled={action.loading || !action.preview} onClick={() => void apply(owner)}>確認儲存</button></div>{action.preview && <div className="registry-preview"><strong>即將變更：</strong>{Object.keys(action.preview.after).map((field) => labels[field] ?? field).join('、')}</div>}{action.message && <p role="status">{action.message}</p>}</section>;
  };
  return <div className="client-registry-page"><header><div><h2>名冊資料</h2><p>以案件編號整合客戶主檔、BeClass、照護與特殊計費資料及訂單條件；可編輯區塊分別儲存。</p></div><form onSubmit={(event) => { event.preventDefault(); void loadList(); }}><input aria-label="搜尋客戶名冊" value={query} placeholder="案件編號、姓名或電話" onChange={(event) => setQuery(event.target.value)} /><button>搜尋</button></form></header><div className="client-registry-layout"><aside aria-label="案件清單">{page?.items.map((item) => <button type="button" className={selected === item.case_no ? 'selected' : ''} key={item.case_no} onClick={() => void loadDetail(item.case_no)}><strong>{item.case_no}</strong><span>{item.name ?? '未登錄姓名'} · {item.phone ?? '未登錄電話'}</span><small>{item.city ?? '未登錄地區'}｜{item.order_status ?? '未有訂單狀態'}</small></button>)}</aside><main>{message && <p role="status" className="registry-message">{message}</p>}{detail && <><div className="registry-case-heading"><h2>{detail.case_no}</h2><span>客戶主檔 v{detail.client.version}</span></div>{editor('profile', profileLabels, profileDraft, setProfileDraft)}{detail.beclass.status === 'ready' ? editor('beclass', beclassLabels, beclassDraft, setBeclassDraft) : <section className="registry-editor"><h3>BeClass 有效資料</h3><p>{detail.beclass.status === 'duplicate_binding' ? '同一案件綁定多筆 BeClass，已停止編輯，請先處理綁定異常。' : '此案件尚未綁定 BeClass 紀錄。'}</p></section>}<OrderInformationSection detail={detail} /><section className="registry-editor"><h3>目前訂單條件</h3>{detail.order_terms.status === 'ready' && detail.order_terms.data ? <OrderTermsMutationPanel caseNo={detail.case_no} query={detail.order_terms.data} onObserved={() => void loadDetail(detail.case_no)} /> : <><p>訂單條件目前不可用（{detail.order_terms.code ?? detail.order_terms.status}）。</p>{detail.order_terms.code === 'client_finance_bootstrap_required' && <CaseArchitectureBootstrapRepairPanel caseNo={detail.case_no} onCompleted={() => loadDetail(detail.case_no)} />}</>}</section></>}</main></div></div>;
};

const ClientChangeHistory: React.FC = () => {
  const [caseNo, setCaseNo] = useState('');
  const [items, setItems] = useState<ClientRegistryChangeHistoryItem[] | null>(null);
  const [message, setMessage] = useState('輸入案件編號，即可查看歷次變更原因。');
  const load = async () => {
    const identity = caseNo.trim();
    if (!identity) { setItems(null); setMessage('請輸入案件編號。'); return; }
    setItems(null); setMessage('正在載入變更歷程…');
    try {
      const history = await clientRegistryClient.history(identity);
      setItems(history);
      setMessage(history.length ? '' : '此案件目前沒有已記錄的變更原因。');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '案件變更歷程載入失敗。');
    }
  };
  return <div className="client-registry-page"><header><div><h2>變更歷程</h2><p>依發生順序顯示案件各項確認與修正所保存的原因。</p></div><form onSubmit={(event) => { event.preventDefault(); void load(); }}><input aria-label="變更歷程案件編號" value={caseNo} placeholder="輸入案件編號" onChange={(event) => setCaseNo(event.target.value)} /><button>查詢</button></form></header>{message && <p role="status" className="registry-message">{message}</p>}{items && items.length > 0 && <ol className="registry-history">{items.map((item) => <li key={`${item.event_type}-${item.sequence}`}><div><strong>{item.sequence}. {item.label}</strong><time dateTime={item.occurred_at}>{new Intl.DateTimeFormat('zh-TW', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(item.occurred_at))}</time></div><p>{item.reason}</p><small>操作人員：{item.actor}</small></li>)}</ol>}</div>;
};

type RegistryTab = 'roster' | 'records' | 'history' | 'virtual-accounts';

export const ClientRegistryPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<RegistryTab>('roster');

  return <div className="client-registry-hub">
    <header className="client-registry-hub__header">
      <div><h1>客戶名冊</h1><p>在清單快速瀏覽案件，或切換至名冊資料管理客戶、BeClass 與訂單條件。</p></div>
    </header>
    <div className="client-registry-tabs" role="tablist" aria-label="客戶名冊檢視">
      <button type="button" role="tab" aria-selected={activeTab === 'roster'} onClick={() => setActiveTab('roster')}>客戶清單</button>
      <button type="button" role="tab" aria-selected={activeTab === 'records'} onClick={() => setActiveTab('records')}>名冊資料</button>
      <button type="button" role="tab" aria-selected={activeTab === 'history'} onClick={() => setActiveTab('history')}>變更歷程</button>
      <button type="button" role="tab" aria-selected={activeTab === 'virtual-accounts'} onClick={() => setActiveTab('virtual-accounts')}>虛擬帳號匯入</button>
    </div>
    <section role="tabpanel" aria-label={activeTab === 'roster' ? '客戶清單' : activeTab === 'records' ? '名冊資料' : activeTab === 'history' ? '變更歷程' : '虛擬帳號匯入'}>
      {activeTab === 'roster' ? <ClientRosterPage embedded /> : activeTab === 'records' ? <ClientRegistryEditor /> : activeTab === 'history' ? <ClientChangeHistory /> : <LegacyVirtualAccountImport />}
    </section>
  </div>;
};

export default ClientRegistryPage;
