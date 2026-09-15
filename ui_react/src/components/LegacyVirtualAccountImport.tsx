import React, { useState } from 'react';

import {
  LegacyVirtualAccountWorkbookSnapshot,
  legacyVirtualAccountImportClient,
  type LegacyVirtualAccountPreview,
  type LegacyVirtualAccountReceipt,
} from '../api/client_finance/legacy_virtual_account_import';


export const LegacyVirtualAccountImport: React.FC = () => {
  const [file, setFile] = useState<File | null>(null);
  const [snapshot, setSnapshot] = useState<LegacyVirtualAccountWorkbookSnapshot | null>(null);
  const [preview, setPreview] = useState<LegacyVirtualAccountPreview | null>(null);
  const [receipt, setReceipt] = useState<LegacyVirtualAccountReceipt | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('請選擇包含「虛擬帳號」與「市府訂單號碼」欄位的 .xlsx 檔案。');
  const [applyKey, setApplyKey] = useState<string | null>(null);

  const selectFile = (next: File | null) => {
    setFile(next);
    setSnapshot(null);
    setPreview(null);
    setReceipt(null);
    setConfirmed(false);
    setApplyKey(null);
    setMessage(next ? '檔案已選擇，請先預覽。' : '請選擇包含「虛擬帳號」與「市府訂單號碼」欄位的 .xlsx 檔案。');
  };

  const runPreview = async () => {
    if (!file) return;
    setBusy(true);
    setMessage('正在產生匯入預覽…');
    try {
      const nextSnapshot = await LegacyVirtualAccountWorkbookSnapshot.fromFile(file);
      const nextPreview = await legacyVirtualAccountImportClient.preview(nextSnapshot);
      setSnapshot(nextSnapshot);
      setPreview(nextPreview);
      setReceipt(null);
      setConfirmed(false);
      setApplyKey(`legacy-va-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`);
      setMessage('預覽完成。空白案件編號、查無訂單及格式不符的資料已略過。');
    } catch (error) {
      setSnapshot(null);
      setPreview(null);
      setMessage(error instanceof Error ? error.message : '預覽失敗。');
    } finally {
      setBusy(false);
    }
  };

  const runApply = async () => {
    if (!snapshot || !preview || !confirmed || !applyKey) return;
    setBusy(true);
    setMessage('正在匯入虛擬帳號…');
    try {
      const result = await legacyVirtualAccountImportClient.apply(snapshot, preview.preview_fingerprint, applyKey);
      setReceipt(result);
      setMessage(result.replayed_workbook ? '此檔案已匯入過，顯示原處理結果。' : '虛擬帳號匯入完成。');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '匯入失敗。');
    } finally {
      setBusy(false);
    }
  };

  return <section className="registry-editor legacy-va-import">
    <h2>匯入舊流程虛擬帳號</h2>
    <p>只匯入能依市府訂單號碼找到既有案件的標準虛擬帳號；其餘資料直接略過。</p>
    <label className="legacy-va-file">選擇虛擬帳號對照表
      <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" disabled={busy} onChange={(event) => selectFile(event.target.files?.[0] ?? null)} />
    </label>
    <div className="registry-actions">
      <button type="button" disabled={busy || !file} onClick={() => void runPreview()}>{busy && !preview ? '預覽中…' : '預覽檔案'}</button>
    </div>
    {preview && <div className="registry-preview legacy-va-metrics">
      <strong>預覽結果</strong>
      <dl>
        <div><dt>來源資料</dt><dd>{preview.source_row_count}</dd></div>
        <div><dt>可處理</dt><dd>{preview.candidate_count}</dd></div>
        <div><dt>將新增</dt><dd>{preview.import_count}</dd></div>
        <div><dt>已存在</dt><dd>{preview.existing_count}</dd></div>
        <div><dt>略過</dt><dd>{preview.skipped_count}</dd></div>
      </dl>
      <label className="legacy-va-confirm"><input type="checkbox" disabled={busy || !!receipt} checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />我已核對預覽筆數</label>
      <div className="registry-actions"><button type="button" disabled={busy || !confirmed || !!receipt} onClick={() => void runApply()}>{busy ? '匯入中…' : '確認匯入'}</button></div>
    </div>}
    {receipt && <div className="registry-preview" role="status">新增 {receipt.inserted_count} 筆、已存在 {receipt.existing_count} 筆、略過 {receipt.skipped_count} 筆。</div>}
    {message && <p role="status" className="registry-message">{message}</p>}
  </section>;
};


export default LegacyVirtualAccountImport;
