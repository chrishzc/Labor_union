import React, { useEffect, useMemo, useState } from 'react';
import { clientRegistryClient } from '../api/client_registry/client_registry_client';
import type { BeClassChanges, ClientProfileChanges, ClientRegistryDetail, ClientRegistryPage as ClientRegistryPageData, RegistryMutationPreview } from '../api/client_registry/client_registry_schemas';
import { OrderTermsMutationPanel } from '../components/OrderTermsMutationPanel';
import './ClientRegistryPage.css';

const profileLabels: Record<string, string> = { name: '姓名', gender: '性別', phone: '手機', city: '縣市', address: '地址', residence_type: '住宅型態', delivery_type: '生產方式', baby_info: '寶寶資訊', notes: '行政註記' };
const beclassLabels: Record<string, string> = { name: '報名姓名', email: 'Email', phone: '手機', tel: '市話', ext: '分機', city: '縣市', zip_code: '郵遞區號', address: '報名地址', admin_notes: '報名註記' };

type Owner = 'profile' | 'beclass';
type Draft = Record<string, string>;
type Action = { preview: RegistryMutationPreview | null; message: string | null; loading: boolean; idempotencyKey: string | null };
const initialAction: Action = { preview: null, message: null, loading: false, idempotencyKey: null };
const toDraft = (values: Record<string, string | null> | null): Draft => Object.fromEntries(Object.entries(values ?? {}).map(([field, value]) => [field, value ?? '']));
const mutationKey = (owner: Owner) => `client-${owner}-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;

export const ClientRegistryPage: React.FC = () => {
  const [query, setQuery] = useState('');
  const [page, setPage] = useState<ClientRegistryPageData | null>(null);
  const [detail, setDetail] = useState<ClientRegistryDetail | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [profileDraft, setProfileDraft] = useState<Draft>({});
  const [beclassDraft, setBeclassDraft] = useState<Draft>({});
  const [reason, setReason] = useState<Record<Owner, string>>({ profile: '', beclass: '' });
  const [actions, setActions] = useState<Record<Owner, Action>>({ profile: initialAction, beclass: initialAction });
  const [message, setMessage] = useState('正在載入客戶名冊…');

  const loadList = async (search = query) => {
    setMessage('正在載入客戶名冊…');
    try {
      const result = await clientRegistryClient.list(search);
      setPage(result); setMessage(result.items.length ? '' : '查無符合條件的案件。');
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
    } catch (error) { setActions((value) => ({ ...value, [owner]: { preview: null, message: error instanceof Error ? error.message : '預覽失敗。', loading: false, idempotencyKey: null } })); }
  };
  const apply = async (owner: Owner) => {
    if (!detail || !reason[owner].trim()) return;
    const action = actions[owner];
    const approvedPreview = action.preview;
    if (!approvedPreview || !action.idempotencyKey) return;
    setActions((value) => ({ ...value, [owner]: { ...action, message: '正在儲存…', loading: true } }));
    try {
      const version = owner === 'profile' ? detail.client.version : detail.beclass.version ?? 0;
      await clientRegistryClient.apply(detail.case_no, owner, changed[owner] as ClientProfileChanges | BeClassChanges, version, approvedPreview.preview_fingerprint, reason[owner].trim(), action.idempotencyKey);
      setReason((value) => ({ ...value, [owner]: '' })); await loadDetail(detail.case_no);
      setMessage(owner === 'profile' ? '客戶主檔已儲存。' : 'BeClass 有效資料已儲存，原始匯入值未被覆寫。');
    } catch (error) { setActions((value) => ({ ...value, [owner]: { ...value[owner], message: error instanceof Error ? error.message : '儲存結果未確認，可用相同預覽安全重試。', loading: false } })); }
  };
  const editor = (owner: Owner, labels: Record<string, string>, draft: Draft, setDraft: React.Dispatch<React.SetStateAction<Draft>>) => {
    const action = actions[owner];
    const source = owner === 'profile' ? detail?.client.values : detail?.beclass.values;
    return <section className="registry-editor"><h3>{owner === 'profile' ? '客戶主檔' : 'BeClass 有效資料'}</h3><small>資料來源：{owner === 'profile' ? 'Client Profile owner' : 'Case Import / BeClass correction owner'}</small><div className="registry-fields">{Object.entries(labels).map(([field, label]) => <label key={field}>{label}<input value={draft[field] ?? ''} disabled={action.loading} onChange={(event) => { setDraft((value) => ({ ...value, [field]: event.target.value })); setActions((value) => ({ ...value, [owner]: initialAction })); }} /></label>)}</div><label className="registry-reason">異動原因<input value={reason[owner]} maxLength={500} onChange={(event) => setReason((value) => ({ ...value, [owner]: event.target.value }))} /></label><div className="registry-actions"><button type="button" disabled={action.loading} onClick={() => { setDraft(toDraft(source ?? null)); setReason((value) => ({ ...value, [owner]: '' })); setActions((value) => ({ ...value, [owner]: initialAction })); }}>取消變更</button><button type="button" disabled={action.loading} onClick={() => void preview(owner)}>預覽變更</button><button type="button" disabled={action.loading || !action.preview || !reason[owner].trim()} onClick={() => void apply(owner)}>確認儲存</button></div>{action.preview && <div className="registry-preview"><strong>即將變更：</strong>{Object.keys(action.preview.after).map((field) => labels[field] ?? field).join('、')}</div>}{action.message && <p role="status">{action.message}</p>}</section>;
  };
  return <div className="client-registry-page"><header><div><h1>客戶名冊</h1><p>以案件編號整合客戶主檔、BeClass 有效資料與訂單條件；各區塊分別儲存。</p></div><form onSubmit={(event) => { event.preventDefault(); void loadList(); }}><input aria-label="搜尋客戶名冊" value={query} placeholder="案件編號、姓名或電話" onChange={(event) => setQuery(event.target.value)} /><button>搜尋</button></form></header><div className="client-registry-layout"><aside aria-label="案件清單">{page?.items.map((item) => <button type="button" className={selected === item.case_no ? 'selected' : ''} key={item.case_no} onClick={() => void loadDetail(item.case_no)}><strong>{item.case_no}</strong><span>{item.name ?? '未登錄姓名'} · {item.phone ?? '未登錄電話'}</span><small>{item.city ?? '未登錄地區'}｜{item.order_status ?? '未有訂單狀態'}</small></button>)}</aside><main>{message && <p role="status" className="registry-message">{message}</p>}{detail && <><div className="registry-case-heading"><h2>{detail.case_no}</h2><span>客戶主檔 v{detail.client.version}</span></div>{editor('profile', profileLabels, profileDraft, setProfileDraft)}{detail.beclass.status === 'ready' ? editor('beclass', beclassLabels, beclassDraft, setBeclassDraft) : <section className="registry-editor"><h3>BeClass 有效資料</h3><p>{detail.beclass.status === 'duplicate_binding' ? '同一案件綁定多筆 BeClass，已停止編輯，請先處理綁定異常。' : '此案件尚未綁定 BeClass 紀錄。'}</p></section>}<section className="registry-editor"><h3>目前訂單條件</h3>{detail.order_terms.status === 'ready' && detail.order_terms.data ? <OrderTermsMutationPanel caseNo={detail.case_no} query={detail.order_terms.data} onObserved={() => void loadDetail(detail.case_no)} /> : <p>訂單條件目前不可用（{detail.order_terms.code ?? detail.order_terms.status}）。</p>}</section></>}</main></div></div>;
};

export default ClientRegistryPage;
