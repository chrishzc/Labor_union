import { useEffect, useState } from 'react';
import { contractExternalSigningClient, type ContractExternalSigningQuery } from '../api/orders/contract_external_signing_client';
import { previewContractFields, type ContractFullPreview } from '../api/orders/contract_full_preview_client';

const FIELDS = {
  client: [['F1', '案件編號'], ['B8', '客戶姓名'], ['A9', '預產期'], ['C10', '服務人員'], ['B24', '預定開始日'], ['D24', '預定結束日'], ['F24', '服務天數'], ['E28', '每日服務時段'], ['B25', '雇主單價'], ['B28', '補助時數'], ['B34', '訂金'], ['C34', '訂金實際入帳日'], ['B35', '第一期款'], ['C35', '第一期實際入帳日'], ['B36', '第二期款'], ['C36', '第二期實際入帳日'], ['B37', '樓層費'], ['B38', '雇主自費合計'], ['B40', '市府補助金額'], ['B43', '服務地址'], ['F41', '其他備註']],
  staff: [['F1', '案件編號'], ['C4', '服務人員姓名'], ['B5', '客戶姓名'], ['B7', '服務開始日'], ['D7', '服務結束日'], ['G7', '服務天數'], ['B8', '服務時段'], ['B9', '休假方式'], ['B10', '服務單價'], ['B13', '補助費用'], ['C13', '補助付款日'], ['B15', '自費金額'], ['C15', '自費付款日'], ['B19', '費用總計'], ['B24', '服務地址'], ['A97', '契約日期']],
} as const;

export function OrderContractPreview({ caseNo }: { caseNo: string }) {
  const [scope, setScope] = useState<'client' | 'staff'>('client');
  const [targets, setTargets] = useState<ContractExternalSigningQuery['staff_targets']>([]);
  const [segmentId, setSegmentId] = useState<number | null>(null);
  const [result, setResult] = useState<ContractFullPreview | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  const [requested, setRequested] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!requested) return;
    const controller = new AbortController();
    setLoading(true); setError(false); setResult(null);
    void (async () => {
      if (scope === 'staff' && segmentId === null) {
        const query = await contractExternalSigningClient.query(caseNo, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setTargets(query.staff_targets);
        // Never substitute a different segment for a user's choice.
        if (query.staff_targets.length === 1) setSegmentId(query.staff_targets[0]!.matching_segment_id);
        return;
      }
      const data = await previewContractFields(caseNo, scope, segmentId, controller.signal);
      if (!controller.signal.aborted) setResult(data);
    })().catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [caseNo, scope, segmentId, requested, revision]);
  return <section aria-label="契約套值欄位預覽">
    <div className="order-information-choice"><button type="button" aria-pressed={scope === 'client'} onClick={() => { setScope('client'); setRequested(false); setResult(null); setError(false); }}><strong>客戶服務契約</strong><span>服務約定、費用與付款安排</span></button><button type="button" aria-pressed={scope === 'staff'} onClick={() => { setScope('staff'); setRequested(false); setResult(null); setError(false); }}><strong>服務人員委任契約</strong><span>月嫂服務區段、報酬與責任</span></button></div>
    <p className="order-case-review-note">此處僅預覽主要套值欄位，不是完整契約或簽署完成證明。收付日期以實際紀錄為準，未收付留白。完整 PDF 請至「下載與簽回」。</p>
    <button type="button" disabled={loading} onClick={() => { setRequested(true); setRevision((value) => value + 1); }}>{loading ? '讀取契約資料中…' : '讀取本案契約資料'}</button>
    {scope === 'staff' && targets.length > 1 && <label>選擇月嫂契約<select value={segmentId ?? ''} onChange={(event) => { setResult(null); setSegmentId(event.target.value ? Number(event.target.value) : null); }}><option value="">請選擇</option>{targets.map((target, index) => <option key={target.matching_segment_id} value={target.matching_segment_id}>月嫂 {target.staff_subject_reference} · 第 {index + 1} 份契約</option>)}</select></label>}
    {error && <p role="alert">目前無法取得本案契約資料。請確認推薦方案與契約準備情況；下方僅為版面，不能視為可簽署文件。</p>}
    {result && !result.ready_to_print && <p role="status">契約尚有未完成條件，請核對資料後再準備文件。</p>}
    {result?.blockers.includes('contract_pdf_external_reference_unresolved') && <p role="alert">契約模板缺少舊版引用內容，暫不能產生可簽署 PDF。</p>}
    <article className="order-information-paper"><header><small>案件 {caseNo} · 套值欄位預覽</small><h3>{scope === 'client' ? '坐月子到府服務契約' : '到宅坐月子服務人員委任契約'}</h3></header><dl>{FIELDS[scope].map(([cell, label]) => {
      const value = result?.field_values[cell];
      return <div key={cell}><dt>{label}</dt><dd className={value == null ? 'is-missing' : ''}>{value == null ? result ? '尚未提供／待核對' : '尚未讀取本案資料' : Array.isArray(value) ? value.join('、') : String(value)}</dd></div>;
    })}</dl></article>
  </section>;
}
