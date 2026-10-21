import { useUnsavedChanges, useUnsavedDraft } from './UnsavedChanges';
import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { StaffProfile } from '../api/staff_profile/staff_profile_schemas';
import { staffRegistryClient } from '../api/staff_registry/staff_registry_client';
import type { StaffBankCommand, StaffBankPreview, StaffProfileMutationPreview } from '../api/staff_registry/staff_registry_schemas';
import { fileSizeLabel, staffResumeClient, type FileTransferSettings, type StaffResume } from '../api/staff_profile/staff_resume_client';
import { adaptStaffProfile } from '../adapters/staff/staff_profile_adapter';

const fields: Array<[keyof StaffProfile, string]> = [['union_no', '公會編號'], ['name', '姓名'], ['identity_card', '身分證'], ['phone', '手機'], ['telephone', '市話'], ['telephone_extension', '分機'], ['email', 'Email'], ['birthday', '生日'], ['city', '縣市'], ['zip_code', '郵遞區號'], ['address', '地址'], ['education', '學歷'], ['emergency_contact_name', '緊急聯絡人'], ['emergency_contact_phone', '緊急聯絡電話'], ['admin_notes', '行政註記']];
const apiField = (field: keyof StaffProfile) => field === 'telephone' ? 'tel' : field === 'telephone_extension' ? 'tel_ext' : field;
type Props = { profile: StaffProfile; onUpdated: () => Promise<void> | void; showResume?: boolean; resumeContainer?: HTMLElement | null };

export const StaffRegistryEditor: React.FC<Props> = ({ profile, onUpdated, showResume = true, resumeContainer }) => {
  const profileSaveGuidanceId = useId();
  const bankSaveGuidanceId = useId();
  const bankReasonRef = useRef<HTMLInputElement>(null);
  const [profileError, setProfileError] = useState(false);
  const [bankError, setBankError] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [profileReason, setProfileReason] = useState('');
  const [profilePreview, setProfilePreview] = useState<StaffProfileMutationPreview | null>(null);
  const [profileMessage, setProfileMessage] = useState<string | null>(null);
  const [operation, setOperation] = useState<StaffBankCommand['operation']>('add');
  const [accountId, setAccountId] = useState(''); const [successorId, setSuccessorId] = useState('');
  const [bankCode, setBankCode] = useState(''); const [branchCode, setBranchCode] = useState(''); const [accountNo, setAccountNo] = useState(''); const [primary, setPrimary] = useState(false);
  const [bankReason, setBankReason] = useState(''); const [bankPreview, setBankPreview] = useState<StaffBankPreview | null>(null); const [bankMessage, setBankMessage] = useState<string | null>(null);
  const [profileApplyKey, setProfileApplyKey] = useState<string | null>(null); const [bankApplyKey, setBankApplyKey] = useState<string | null>(null);
  const [profileBusy, setProfileBusy] = useState(false); const [bankBusy, setBankBusy] = useState(false);
  const [resume, setResume] = useState<StaffResume | null>(null); const [resumeBusy, setResumeBusy] = useState(false); const [resumeMessage, setResumeMessage] = useState<string | null>(null); const [resumeFile, setResumeFile] = useState<File | null>(null);
  const resumeRequest = useRef(0); const resumeUploadIdentity = useRef<{ signature: string; key: string } | null>(null);
  const [resumeStatus, setResumeStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [resumeError, setResumeError] = useState(false);
  const [resumeSettings, setResumeSettings] = useState<FileTransferSettings | null>(null);
  const [resumePreview, setResumePreview] = useState<Blob | null>(null);
  const [resumePreviewUrl, setResumePreviewUrl] = useState<string | null>(null);
  const resumeInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!resumePreview) { setResumePreviewUrl(null); return; }
    const url = URL.createObjectURL(resumePreview);
    setResumePreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [resumePreview]);
  const loadResume = async () => {
    const request = ++resumeRequest.current;
    setResumeStatus('loading'); setResumeError(false); setResumeMessage('正在讀取目前履歷…');
    try {
      const [value, settings] = await Promise.all([staffResumeClient.current(profile.staff_id), staffResumeClient.settings()]);
      if (resumeRequest.current === request) {
        setResume(value); setResumeSettings(settings); setResumeStatus('ready'); setResumeMessage(null);
      }
    } catch (error) {
      if (resumeRequest.current === request) {
        setResumeStatus('error'); setResumeError(true);
        setResumeMessage(error instanceof Error ? error.message : '履歷查詢失敗，請重試。');
      }
    }
  };

  const mutationKey = (scope: string) => `${scope}-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
  useEffect(() => {
    setDraft(Object.fromEntries(fields.map(([field]) => [String(field), String(profile[field] ?? '')])));
    setProfilePreview(null); setBankPreview(null); setProfileApplyKey(null); setBankApplyKey(null);
    setResume(null); setResumeFile(null); setResumePreview(null); setResumeSettings(null);
    resumeUploadIdentity.current = null;
    if (showResume) void loadResume();
    return () => { resumeRequest.current += 1; };
  }, [profile, showResume]);
  const changes = useMemo(() => Object.fromEntries(fields.filter(([field]) => draft[String(field)] !== String(profile[field] ?? '')).map(([field]) => [apiField(field), draft[String(field)] || null])), [draft, profile]);
  const unsavedRef = useUnsavedChanges('月嫂個人與聯絡資料', fields.filter(([field]) => draft[String(field)] !== undefined && draft[String(field)] !== String(profile[field] ?? '')).map(([field, label]) => ({ label, before: String(profile[field] ?? '') || '未填寫', after: draft[String(field)] || '未填寫' })).concat(profileReason ? [{ label: '備註', before: '未填寫', after: profileReason }] : []), { busy: profileBusy, save: () => applyProfile(true) });
  const bankUnsavedRef = useUnsavedDraft('月嫂銀行帳戶', { '動作': operation, '帳戶': accountId, '接續帳戶': successorId, '銀行代碼': bankCode, '分行代碼': branchCode, '新帳號已輸入（不顯示內容）': !!accountNo, '主要帳戶': primary, '異動原因': bankReason }, { busy: bankBusy, resetKey: profile.bank_accounts_version });
  const resumeUnsavedRef = useUnsavedDraft('月嫂履歷', { '待上傳檔案': resumeFile?.name ?? '' }, { busy: resumeBusy, baseline: { '待上傳檔案': '' } });
  const bankAccountLabels = adaptStaffProfile(profile).bankAccountLabels;
  const missingBankFields = [
    ...(operation !== 'add' && !accountId ? ['帳戶'] : []),
    ...(['add', 'replace'].includes(operation) ? [!bankCode.trim() ? '銀行代碼' : '', !branchCode.trim() ? '分行代碼' : '', !accountNo.trim() ? '完整新帳號' : ''].filter(Boolean) : []),
  ];
  const command = (): StaffBankCommand => ({ operation, ...(operation !== 'add' ? { account_id: Number(accountId) } : {}), ...(['add', 'replace'].includes(operation) ? { bank_code: bankCode, branch_code: branchCode, account_no: accountNo, is_primary: primary } : {}), ...(operation === 'deactivate' && successorId ? { successor_account_id: Number(successorId) } : {}) });
  const applyProfile = async (preparePreview = true) => {
    if (profileBusy || ((!profilePreview || !profileApplyKey) && !preparePreview)) return;
    try {
      setProfileError(false); setProfileBusy(true); setProfileMessage('正在儲存…');
      let approved = profilePreview;
      let key = profileApplyKey;
      if (!approved || !key) {
        approved = await staffRegistryClient.previewProfile(profile.staff_id, changes, profile.profile_version);
        key = mutationKey('staff-profile');
        setProfilePreview(approved); setProfileApplyKey(key);
      }
      await staffRegistryClient.applyProfile(profile.staff_id, changes, approved.current_version, approved.preview_fingerprint, profileReason.trim(), key);
      setProfileReason(''); setProfilePreview(null); setProfileApplyKey(null);
      await onUpdated(); setProfileMessage('個人資料已儲存。');
    } catch (error) {
      setProfileError(true); setProfileMessage(error instanceof Error ? error.message : '儲存結果未確認，請用相同預覽重試或重新查詢。');
    } finally { setProfileBusy(false); }
  };
  const applyBank = async () => {
    if (bankBusy) return;
    if (missingBankFields.length) { setBankError(true); setBankMessage(`請填寫或選擇${missingBankFields.join('、')}。`); return; }
    try {
      setBankError(false); setBankBusy(true); setBankMessage('正在儲存…');
      const approved = bankPreview ?? await staffRegistryClient.previewBank(profile.staff_id, command(), profile.bank_accounts_version);
      const key = bankApplyKey ?? mutationKey('staff-bank');
      setBankPreview(approved); setBankApplyKey(key);
      await staffRegistryClient.applyBank(profile.staff_id, command(), profile.bank_accounts_version, approved.preview_fingerprint, bankReason.trim(), key);
      setAccountNo(''); setBankReason(''); setBankPreview(null); setBankApplyKey(null);
      await onUpdated(); setBankMessage('銀行帳戶已儲存，完整帳號已從輸入欄清除。');
    } catch (error) {
      setBankError(true); setAccountNo(''); setBankPreview(null); setBankApplyKey(null);
      await onUpdated(); setBankMessage(error instanceof Error ? `${error.message}；已重新查詢，完整帳號已清除。` : '儲存結果未確認；已重新查詢，完整帳號已清除。');
    } finally { setBankBusy(false); }
  };
  const selectResume = (file: File | null) => {
    setResumeFile(null); setResumePreview(null); setResumeError(false); setResumeMessage(null);
    resumeUploadIdentity.current = null;
    if (!file) return;
    if (file.type !== 'application/pdf' || !file.name.toLowerCase().endsWith('.pdf')) {
      setResumeError(true); setResumeMessage('請選擇 PDF 履歷檔案。'); return;
    }
    if (resumeSettings && file.size > resumeSettings.resume_max_bytes) {
      setResumeError(true);
      setResumeMessage(`所選履歷 ${fileSizeLabel(file.size)}，超過目前上限 ${fileSizeLabel(resumeSettings.resume_max_bytes)}。本次未上傳，請選擇較小檔案或請管理者調整上限。`);
      return;
    }
    setResumeFile(file); setResumePreview(file);
  };
  const uploadResume = async () => {
    if (resumeBusy || !resumeFile || resumeStatus !== 'ready') return;
    const request = resumeRequest.current;
    const signature = `${profile.staff_id}:${resumeFile.name}:${resumeFile.size}:${resumeFile.lastModified}`;
    if (resumeUploadIdentity.current?.signature !== signature) resumeUploadIdentity.current = { signature, key: mutationKey(`staff-resume-${profile.staff_id}`) };
    try {
      setResumeBusy(true); setResumeError(false); setResumeMessage('正在上傳並保存履歷，請稍候…');
      const saved = await staffResumeClient.upload(profile.staff_id, resumeFile, resumeUploadIdentity.current.key);
      if (resumeRequest.current !== request) return;
      setResume(saved); resumeUploadIdentity.current = null; setResumeFile(null); setResumePreview(null);
      if (resumeInput.current) resumeInput.current.value = '';
      setResumeMessage('月嫂履歷已完成受控上傳。');
    } catch (error) {
      if (resumeRequest.current !== request) return;
      setResumeError(true); setResumeMessage(error instanceof Error ? error.message : '履歷上傳失敗。');
    } finally { setResumeBusy(false); }
  };
  const readResume = async (download: boolean) => {
    if (!resume || resumeBusy) return;
    const request = resumeRequest.current;
    try {
      setResumeBusy(true); setResumeError(false); setResumeMessage(download ? '正在準備履歷下載…' : '正在讀取履歷預覽…');
      if (download) await staffResumeClient.download(resume.file_id, resume.filename);
      else {
        const blob = await staffResumeClient.preview(resume.file_id);
        if (resumeRequest.current !== request) return;
        setResumePreview(blob);
      }
      if (resumeRequest.current === request) setResumeMessage(download ? '已交由瀏覽器下載履歷。' : '履歷已載入，下方可預覽。');
    } catch (error) {
      if (resumeRequest.current !== request) return;
      setResumeError(true); setResumeMessage(error instanceof Error ? error.message : '履歷讀取失敗，請重試。');
    } finally { setResumeBusy(false); }
  };
  const resumeSection = <section ref={resumeUnsavedRef} className="staff-holiday-op-card" aria-busy={resumeBusy || resumeStatus === 'loading'}>
    <h3 className="staff-op-title">月嫂履歷 PDF</h3>
    {resumeStatus === 'ready' && (resume ? <>
      <p>目前履歷：{resume.filename}</p><p>版本：{resume.version}</p>
      <button type="button" className="staff-secondary-btn" disabled={resumeBusy} onClick={() => void readResume(false)}>預覽目前履歷</button>
      <button type="button" className="staff-secondary-btn" disabled={resumeBusy} onClick={() => void readResume(true)}>下載目前履歷</button>
    </> : <p>尚未上傳月嫂履歷 PDF</p>)}
    {resumeStatus === 'error' && <button type="button" className="staff-secondary-btn" onClick={() => void loadResume()}>重新讀取履歷</button>}
    {resumeSettings && <p>PDF 上限：{fileSizeLabel(resumeSettings.resume_max_bytes)}。上傳新版會保留既有版本。</p>}
    <label className="staff-op-field">選擇 PDF<input ref={resumeInput} type="file" accept="application/pdf,.pdf" disabled={resumeBusy || resumeStatus !== 'ready'} onChange={(event) => selectResume(event.target.files?.[0] ?? null)} /></label>
    {resumeFile && <p>已選擇：{resumeFile.name}（{fileSizeLabel(resumeFile.size)}），尚未上傳。</p>}
    {resumePreviewUrl && <div>
      <object aria-label="履歷 PDF 預覽" data={resumePreviewUrl} type="application/pdf" style={{ width: '100%', height: 420 }}><p>瀏覽器無法顯示 PDF 預覽，可使用下載功能查看。</p></object>
      <button type="button" className="staff-secondary-btn" onClick={() => setResumePreview(null)}>關閉履歷預覽</button>
    </div>}
    <button type="button" className="staff-primary-btn" disabled={resumeBusy || !resumeFile || resumeStatus !== 'ready'} onClick={() => void uploadResume()}>{resume ? '上傳新版履歷' : '上傳履歷'}</button>
    {resumeMessage && <p role={resumeError ? 'alert' : 'status'} className={resumeError ? 'staff-op-error' : undefined}>{resumeMessage}</p>}
  </section>;
  return <div className="staff-registry-editors">{showResume && (resumeContainer ? createPortal(resumeSection, resumeContainer) : resumeContainer === undefined ? resumeSection : null)}<section ref={unsavedRef} className="staff-holiday-op-card"><h3 className="staff-op-title">✏️ 編輯個人與聯絡資料</h3><p className="staff-op-hint">修改欄位後按「儲存」；備註可選填。</p><p>登錄日期：{profile.registered_at?.slice(0, 10) ?? '尚未登錄'}</p><div className="staff-op-grid">{fields.map(([field, label]) => <label className="staff-op-field" key={String(field)}>{label}<input disabled={profileBusy} maxLength={field === 'union_no' ? 50 : undefined} placeholder={field === 'union_no' ? '例如 A001，可包含英文與數字' : undefined} value={draft[String(field)] ?? ''} onChange={(event) => { setDraft((value) => ({ ...value, [String(field)]: event.target.value })); setProfilePreview(null); setProfileApplyKey(null); setProfileMessage(null); }} /></label>)}</div><label className="staff-op-field">備註（選填）<input aria-label="個人資料備註（選填）" placeholder="有需要補充的內容再填寫" disabled={profileBusy} value={profileReason} maxLength={500} onChange={(event) => { setProfileReason(event.target.value); if (profileError) { setProfileError(false); setProfileMessage(null); } }} /></label><p id={profileSaveGuidanceId} className="staff-op-hint">{profileBusy ? '正在處理，請稍候。' : !Object.keys(changes).length ? '請先修改要儲存的資料。' : !profilePreview ? '可直接儲存；備註可留白。' : '預覽完成，可直接確認儲存；備註可留白。'}</p><div className="staff-op-actions"><button type="button" className="staff-secondary-btn" disabled={profileBusy} onClick={() => { setDraft(Object.fromEntries(fields.map(([field]) => [String(field), String(profile[field] ?? '')]))); setProfileReason(''); setProfilePreview(null); setProfileApplyKey(null); setProfileMessage(null); }}>取消變更</button><button type="button" className="staff-primary-btn" aria-describedby={profileSaveGuidanceId} disabled={profileBusy || !Object.keys(changes).length} onClick={() => void applyProfile()}>儲存</button></div>{profilePreview && <div aria-label="個資變更預覽">{Object.keys(profilePreview.after).map(field => <p key={field}><strong>{fields.find(([key]) => apiField(key) === field)?.[1] ?? field}</strong>：{String(profilePreview.before[field] ?? '未設定')} → {String(profilePreview.after[field] ?? '未設定')}</p>)}</div>}{profileMessage && <p role={profileError ? "alert" : "status"} className={profileError ? "staff-op-error" : undefined}>{profileMessage}</p>}</section><section ref={bankUnsavedRef} className="staff-holiday-op-card"><h3 className="staff-op-title">🏦 管理銀行帳戶</h3><h4 className="staff-profile-subheading">目前銀行帳戶</h4>{bankAccountLabels.length ? <ul className="staff-bank-list" aria-label="銀行帳戶">{bankAccountLabels.map((account, index) => <li key={profile.bank_accounts[index].account_id}><strong>帳戶 {index + 1}</strong><span>{account}</span></li>)}</ul> : <p className="staff-bank-empty">尚未登錄銀行帳戶</p>}<p>可新增、更換、停用帳戶或設定主要帳戶。帳戶只顯示末四碼；新增或更換時請輸入完整帳號。</p>{(!bankMessage || bankPreview) && <p id={bankSaveGuidanceId} className="staff-op-hint">{missingBankFields.length ? `請先填寫或選擇${missingBankFields.join('、')}；` : bankPreview ? (bankReason.trim() ? '預覽完成，可確認儲存。' : '可直接儲存；備註可留白。') : '資料已填齊，可直接儲存。'}</p>}<div className="staff-op-grid"><label className="staff-op-field">動作<select disabled={bankBusy} value={operation} onChange={(event) => { setOperation(event.target.value as StaffBankCommand['operation']); setBankPreview(null); setBankApplyKey(null); setBankMessage(null); }}><option value="add">新增帳戶</option><option value="replace">更換帳戶</option><option value="set_primary">設為主要帳戶</option><option value="deactivate">停用帳戶</option></select></label>{operation !== 'add' && <label className="staff-op-field">帳戶<select disabled={bankBusy} value={accountId} onChange={(event) => { setAccountId(event.target.value); setBankPreview(null); setBankApplyKey(null); setBankMessage(null); }}><option value="">請選擇</option>{profile.bank_accounts.map((account) => <option key={account.account_id} value={account.account_id}>{account.account_no ? `帳號 ${account.account_no}` : (account.account_last4 ? `末四碼 ${account.account_last4}` : `帳戶 #${account.account_id}`)}{account.is_active ? '' : '（已停用）'}</option>)}</select></label>}{['add', 'replace'].includes(operation) && <><label className="staff-op-field">銀行代碼<input disabled={bankBusy} inputMode="numeric" value={bankCode} onChange={(event) => { setBankCode(event.target.value); setBankPreview(null); setBankApplyKey(null); setBankMessage(null); }} /></label><label className="staff-op-field">分行代碼<input disabled={bankBusy} inputMode="numeric" value={branchCode} onChange={(event) => { setBranchCode(event.target.value); setBankPreview(null); setBankApplyKey(null); setBankMessage(null); }} /></label><label className="staff-op-field">完整新帳號<input disabled={bankBusy} type="password" autoComplete="off" inputMode="numeric" value={accountNo} onChange={(event) => { setAccountNo(event.target.value); setBankPreview(null); setBankApplyKey(null); setBankMessage(null); }} /></label><label className="staff-op-field"><span>主要帳戶</span><input disabled={bankBusy} type="checkbox" checked={primary} onChange={(event) => { setPrimary(event.target.checked); setBankPreview(null); setBankApplyKey(null); setBankMessage(null); }} /></label></>}{operation === 'deactivate' && <label className="staff-op-field">主要帳戶接替者（需要時）<select disabled={bankBusy} value={successorId} onChange={(event) => { setSuccessorId(event.target.value); setBankPreview(null); setBankApplyKey(null); setBankMessage(null); }}><option value="">不指定</option>{profile.bank_accounts.filter((account) => account.is_active && String(account.account_id) !== accountId).map((account) => <option key={account.account_id} value={account.account_id}>{account.account_no ? `帳號 ${account.account_no}` : `末四碼 ${account.account_last4 ?? '未登錄'}`}</option>)}</select></label>}</div><label className="staff-op-field">備註（選填）<input ref={bankReasonRef} disabled={bankBusy} value={bankReason} maxLength={500} onChange={(event) => { setBankReason(event.target.value); if (bankError) { setBankError(false); setBankMessage(null); } }} /></label><div className="staff-op-actions"><button type="button" className="staff-secondary-btn" disabled={bankBusy} onClick={() => { setAccountId(''); setSuccessorId(''); setBankCode(''); setBranchCode(''); setAccountNo(''); setPrimary(false); setBankReason(''); setBankPreview(null); setBankApplyKey(null); setBankMessage(null); }}>取消變更</button><button type="button" className="staff-primary-btn" aria-describedby={bankSaveGuidanceId} disabled={bankBusy || missingBankFields.length > 0} onClick={() => void applyBank()}>儲存</button></div>{bankPreview?.after && <p>預覽：{bankPreview.after.bank_code}／{bankPreview.after.branch_code}／末四碼 {bankPreview.after.account_last4}</p>}{bankMessage && <p role={bankError ? "alert" : "status"} className={bankError ? "staff-op-error" : undefined}>{bankMessage}</p>}</section></div>;
};
