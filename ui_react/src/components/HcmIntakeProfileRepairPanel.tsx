import { useEffect, useRef, useState } from 'react';
import { clientRegistryClient } from '../api/client_registry/client_registry_client';
import type { ClientProfileChanges, ClientRegistryDetail, RegistryMutationPreview } from '../api/client_registry/client_registry_schemas';
import { ApiHttpError } from '../api/shared/typed_errors';

const PROFILE_FIELDS: Record<string, keyof ClientProfileChanges> = {
  姓名: 'name', 性別: 'gender', 行動電話: 'phone', email: 'email', 縣市: 'city',
  '預產期/預計服務開始月份': 'due_month', 不符合原因: 'reject_reason',
  居住型態: 'residence_type', 生產方式: 'delivery_type', 寶寶資訊: 'baby_info',
  服務方式: 'service_type',
};

export function canRepairHcmProfileField(field: string): boolean {
  return Object.hasOwn(PROFILE_FIELDS, field);
}

type ApprovedChange = {
  preview: RegistryMutationPreview;
  changes: ClientProfileChanges;
  key: string;
};

export function HcmIntakeProfileRepairPanel({ caseNo, fields, disabled, onSaved, onBusyChange }: {
  caseNo: string;
  fields: readonly string[];
  disabled: boolean;
  onSaved: () => Promise<void>;
  onBusyChange: (busy: boolean) => void;
}) {
  const [detail, setDetail] = useState<ClientRegistryDetail | null>(null);
  const [draft, setDraft] = useState<ClientProfileChanges>({});
  const [approved, setApproved] = useState<ApprovedChange | null>(null);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [unconfirmed, setUnconfirmed] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const mounted = useRef(false);
  const profileFields = fields.filter(canRepairHcmProfileField);
  const fieldsKey = profileFields.join('|');

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; onBusyChange(false); };
  }, [onBusyChange]);

  useEffect(() => {
    if (!fieldsKey) return;
    let active = true;
    setDetail(null);
    setDraft({});
    setApproved(null);
    setMessage(null);
    void clientRegistryClient.query(caseNo).then((value) => {
      if (!active) return;
      if (value.case_no !== caseNo) throw new Error('補件資料與案件不一致，請重新讀取。');
      setDetail(value);
    }).catch((error) => {
      if (active) setMessage(error instanceof Error ? error.message : '缺件資料讀取失敗，請重新讀取案件。');
    });
    return () => { active = false; };
  }, [caseNo, fieldsKey]);

  const editableFields = profileFields.filter((source) => {
    const capability = detail?.client.field_capabilities[PROFILE_FIELDS[source]];
    return capability?.owner === 'client_profile' && capability.editable;
  });
  const changes: ClientProfileChanges = Object.fromEntries(editableFields.flatMap((source) => {
    const field = PROFILE_FIELDS[source];
    const value = draft[field];
    return value !== undefined && value !== detail?.client.values[field] ? [[field, value]] : [];
  }));
  const locked = disabled || busy || unconfirmed;

  const preview = async () => {
    if (!detail || locked || Object.keys(changes).length === 0) return;
    setBusy(true); onBusyChange(true); setMessage(null); setApproved(null);
    try {
      const value = await clientRegistryClient.preview(caseNo, 'profile', changes, detail.client.version);
      if (!mounted.current) return;
      if (value.aggregate_identity !== caseNo || value.owner !== 'client_profile'
        || value.current_version !== detail.client.version
        || Object.keys(value.after).length !== Object.keys(changes).length
        || Object.keys(value.after).some((field) => !Object.hasOwn(changes, field))) {
        throw new Error('補件預覽與本次資料不一致，請重新讀取案件。');
      }
      setApproved({ preview: value, changes, key: `hcm-intake-profile-${crypto.randomUUID()}` });
    } catch (error) {
      if (mounted.current) setMessage(error instanceof Error ? error.message : '缺件修正預覽失敗。');
    } finally {
      if (mounted.current) { setBusy(false); onBusyChange(false); }
    }
  };

  const observe = async (change: ApprovedChange, minimumVersion: number) => {
    const value = await clientRegistryClient.query(caseNo);
    if (!mounted.current) return;
    if (value.case_no !== caseNo || value.client.version < minimumVersion
      || Object.entries(change.preview.after).some(([field, expected]) => value.client.values[field as keyof ClientProfileChanges] !== expected)) {
      throw new Error('尚未確認補件資料已保存，請重新讀取修正結果。');
    }
    await onSaved();
    if (mounted.current) {
      setDetail(value); setDraft({}); setApproved(null); setUnconfirmed(false);
      setMessage('缺件資料已儲存並重新確認。');
    }
  };

  const apply = async () => {
    if (!approved || locked) return;
    setBusy(true); onBusyChange(true); setMessage(null);
    let submitted = false;
    try {
      const receipt = await clientRegistryClient.apply(caseNo, 'profile', approved.changes,
        approved.preview.current_version, approved.preview.preview_fingerprint, reason.trim(), approved.key);
      submitted = true;
      if (!mounted.current) return;
      if (receipt.aggregate_identity !== caseNo || receipt.owner !== 'client_profile'
        || receipt.preview_fingerprint !== approved.preview.preview_fingerprint || receipt.idempotency_key !== approved.key) {
        throw new Error('補件儲存結果與本次操作不一致，請重新讀取。');
      }
      await observe(approved, receipt.resulting_version);
    } catch (error) {
      if (!mounted.current) return;
      const rejected = !submitted && error instanceof ApiHttpError && [400, 401, 403, 404, 409, 422].includes(error.status);
      setUnconfirmed(!rejected);
      if (rejected) setApproved(null);
      setMessage(rejected ? '修正未套用，請重新讀取案件並核對資料。'
        : '儲存結果尚未確認，請重新讀取修正結果。');
    } finally {
      if (mounted.current) { setBusy(false); onBusyChange(false); }
    }
  };

  const readback = async () => {
    if (!approved || busy) return;
    setBusy(true); onBusyChange(true); setMessage(null);
    try { await observe(approved, approved.preview.current_version + 1); }
    catch (error) { if (mounted.current) setMessage(error instanceof Error ? error.message : '修正結果讀取失敗。'); }
    finally { if (mounted.current) { setBusy(false); onBusyChange(false); } }
  };

  if (!profileFields.length) return null;
  return <section aria-label="修正進件欄位" style={{ borderTop: '1px solid #fed7aa', paddingTop: 10, display: 'grid', gap: 10, minWidth: 0 }}>
    <strong>直接修正缺件資料</strong>
    {!detail && !message && <p role="status">正在讀取目前資料…</p>}
    {detail && <>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(220px, 100%), 1fr))', gap: 10, minWidth: 0 }}>
        {profileFields.map((source) => {
          const field = PROFILE_FIELDS[source];
          const value = draft[field] ?? detail.client.values[field] ?? '';
          const options = detail.client.field_capabilities[field]?.options;
          const editable = editableFields.includes(source);
          const id = `hcm-intake-${caseNo}-${field}`;
          const update = (next: string) => { setDraft((current) => ({ ...current, [field]: next })); setApproved(null); setMessage(null); };
          return <div key={source} style={{ display: 'grid', gap: 4, minWidth: 0 }}><label htmlFor={id}>{field === 'email' ? 'HCM Email' : field === 'phone' ? '電話（手機／市話）' : source}</label>
            {options ? <select id={id} value={value} style={{ width: '100%', minWidth: 0, boxSizing: 'border-box' }} disabled={locked || !editable} onChange={(event) => update(event.target.value)}>
              <option value="" disabled>請選擇</option>
              {value && !options.includes(value) && <option value={value} disabled>{value}（待修正）</option>}
              {options.map((option) => <option key={option}>{option}</option>)}
            </select> : <input id={id} type={field === 'due_month' ? 'date' : field === 'phone' ? 'tel' : field === 'email' ? 'email' : 'text'}
              value={value} style={{ width: '100%', minWidth: 0, boxSizing: 'border-box' }} maxLength={field === 'reject_reason' ? 500 : field === 'email' || field === 'service_type' ? 100 : undefined} disabled={locked || !editable}
              onChange={(event) => update(event.target.value)} />}
            {!editable && <small>目前不可修改此欄位，請重新確認案件資料。</small>}
          </div>;
        })}
      </div>
      <><label style={{ display: 'grid', gap: 4, minWidth: 0 }}>備註（選填）
        <input  value={reason} style={{ width: '100%', minWidth: 0, boxSizing: 'border-box' }} maxLength={500} disabled={locked} onChange={(event) => setReason(event.target.value)} />
      </label></>
      <button type="button" className="btn-secondary-action" disabled={locked || !Object.keys(changes).length} onClick={() => void preview()}>預覽欄位修正</button>
      {approved && <div aria-label="欄位修正前後" style={{ display: 'grid', gap: 6 }}>
        {Object.entries(approved.preview.after).map(([field, value]) => <div key={field}>
          {profileFields.find((source) => PROFILE_FIELDS[source] === field)}：{approved.preview.before[field] || '未填寫'} → {value}
        </div>)}
        <button type="button" className="btn-primary-action" disabled={locked} onClick={() => void apply()}>確認儲存缺件資料</button>
      </div>}
    </>}
    {unconfirmed && <button type="button" disabled={busy} onClick={() => void readback()}>重新讀取修正結果</button>}
    {message && <p role="status">{message}</p>}
  </section>;
}
