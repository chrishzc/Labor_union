import { useUnsavedDraft } from './UnsavedChanges';
import React, { useState } from 'react';
import { ApiHttpError } from '../api/shared/typed_errors';

import {
  LegacyVirtualAccountWorkbookSnapshot,
  legacyVirtualAccountImportClient,
  type LegacyVirtualAccountPreview,
  type LegacyVirtualAccountReceipt,
} from '../api/client_finance/legacy_virtual_account_import';

const selectionPrompt = '請選擇包含「虛擬帳號」與「市府訂單號碼」欄位的 .xlsx 檔案。';
const rowStatus = {
  create: '可登錄',
  existing: '已存在',
  transfer: '從取消案轉入',
  conflict: '衝突，略過',
  ineligible_year: '年度不適用',
  missing_order: '查無案件',
  replace_required: '已有其他對照，請至客戶名冊單案更正',
};

export const LegacyVirtualAccountImport: React.FC = () => {
  const [file, setFile] = useState<File | null>(null);
  const [snapshot, setSnapshot] = useState<LegacyVirtualAccountWorkbookSnapshot | null>(null);
  const [preview, setPreview] = useState<LegacyVirtualAccountPreview | null>(null);
  const [receipt, setReceipt] = useState<LegacyVirtualAccountReceipt | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(selectionPrompt);
  const [applyKey, setApplyKey] = useState<string | null>(null);

  const selectFile = (next: File | null) => {
    setFile(next);
    setSnapshot(null);
    setPreview(null);
    setReceipt(null);
    setApplyKey(null);
    setMessage(next ? '檔案已選擇，可以匯入。' : selectionPrompt);
  };

  const runImport = async () => {
    if (!file) return;
    setBusy(true);
    setMessage('正在匯入…');
    try {
      const nextSnapshot = snapshot ?? await LegacyVirtualAccountWorkbookSnapshot.fromFile(file);
      const nextPreview = preview ?? await legacyVirtualAccountImportClient.preview(nextSnapshot);
      setSnapshot(nextSnapshot);
      setPreview(nextPreview);
      setReceipt(null);
      if (!preview && nextPreview.non_citizen_rows?.some(row => row.case_no.startsWith('A'))) {
        setMessage('請核對各列的處理結果。確認後會套用可處理的資料。');
        return;
      }
      const key = applyKey ?? `legacy-va-${globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
      setApplyKey(key);
      const result = await legacyVirtualAccountImportClient.apply(nextSnapshot, nextPreview.preview_fingerprint, key);
      setReceipt(result);
      setMessage(result.non_citizen_rows?.some(row => row.status === 'conflict')
        ? '匯入完成。衝突列未寫入，請查閱相關案號。'
        : '匯入完成。空白案件編號、查無訂單及格式不符的資料已略過。');
    } catch (error) {
      if (error instanceof ApiHttpError && error.code === 'legacy_virtual_account_preview_stale') {
        setPreview(null);
        setApplyKey(null);
        setMessage('案件狀態或帳號對照已變更，請重新匯入工作簿以取得最新預覽。');
      } else {
        setMessage(error instanceof Error ? error.message : '匯入失敗。');
      }
    } finally {
      setBusy(false);
    }
  };

  useUnsavedDraft('虛擬帳號匯入', { '待匯入檔案': file?.name ?? '' }, { baseline: { '待匯入檔案': '' }, enabled: !receipt, busy });

  const needsConfirmation = !!preview?.non_citizen_rows?.some(row => row.case_no.startsWith('A'));
  const rows = receipt?.non_citizen_rows ?? preview?.non_citizen_rows ?? [];

  return <section className="registry-editor legacy-va-import">
    <h2>匯入舊虛擬帳號</h2>
    <p>只匯入能依市府訂單號碼找到既有案件的標準虛擬帳號；其餘資料直接略過。</p>
    <label className="legacy-va-file">選擇虛擬帳號對照表
      <input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" disabled={busy} onChange={(event) => selectFile(event.target.files?.[0] ?? null)} />
    </label>
    <div className="registry-actions">
      <button
        type="button"
        disabled={busy || !file || !!receipt || (needsConfirmation && preview?.candidate_count === 0)}
        onClick={() => void runImport()}
      >
        {busy ? '匯入中…' : needsConfirmation ? '確認套用' : '匯入虛擬帳號'}
      </button>
    </div>
    {preview && <div className="registry-preview legacy-va-metrics">
      <strong>處理筆數</strong>
      <dl>
        <div><dt>來源資料</dt><dd>{preview.source_row_count}</dd></div>
        <div><dt>可處理</dt><dd>{preview.candidate_count}</dd></div>
        <div><dt>{needsConfirmation ? '將新增或轉入' : '將新增'}</dt><dd>{preview.import_count}</dd></div>
        <div><dt>已存在</dt><dd>{preview.existing_count}</dd></div>
        <div><dt>略過</dt><dd>{preview.skipped_count}</dd></div>
      </dl>
      {rows.length > 0 && <table className="legacy-va-results">
        <caption>虛擬帳號匯入明細</caption>
        <thead><tr><th scope="col">Excel 列</th><th scope="col">案件編號</th><th scope="col">處理結果</th><th scope="col">相關案號</th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.source_row}>
          <td>{row.source_row}</td>
          <td>{row.case_no}</td>
          <td>{receipt && row.status === 'create' ? '已新增' : rowStatus[row.status]}</td>
          <td>{row.related_case_nos.join('、') || '—'}</td>
        </tr>)}</tbody>
      </table>}
    </div>}
    {receipt && <div className="registry-preview" role="status">{needsConfirmation ? '新增或轉入' : '新增'} {receipt.inserted_count} 筆、已存在 {receipt.existing_count} 筆、略過 {receipt.skipped_count} 筆。</div>}
    {message && <p role="status" className="registry-message">{message}</p>}
  </section>;
};


export default LegacyVirtualAccountImport;
