import { useEffect, useState } from 'react';
import { contractExternalSigningClient, type ContractExternalSigningQuery } from '../api/orders/contract_external_signing_client';
import { previewContractFields, type ContractFullPreview } from '../api/orders/contract_full_preview_client';

const FIELDS = {
  client: [['F1', '案件編號'], ['B8', '客戶姓名'], ['A9', '預產期'], ['C10', '服務人員'], ['B24', '預定開始日'], ['D24', '預定結束日'], ['F24', '服務天數'], ['E28', '每日服務時段'], ['B25', '雇主單價'], ['projected.subsidy_hours', '預估補助時數'], ['B34', '預估訂金'], ['projected.deposit_due_date', '預計訂金繳款日'], ['B35', '預估第一期款'], ['projected.first_payment_due_date', '預計第一期繳款日'], ['B36', '預估第二期款'], ['projected.second_payment_due_date', '預計第二期繳款日'], ['D36', '本案專屬虛擬帳號'], ['B37', '樓層費'], ['B38', '預估雇主自費合計'], ['projected.projected_subsidy_amount', '預估市府補助金額'], ['B43', '服務地址'], ['F41', '其他備註']],
  staff: [['F1', '案件編號'], ['C4', '服務人員姓名'], ['B5', '客戶姓名'], ['B7', '服務開始日'], ['D7', '服務結束日'], ['G7', '服務天數'], ['B8', '服務時段'], ['B9', '休假方式'], ['projected.service_unit_price', '預估服務單價'], ['projected.staff_payable_total', '預估整筆應付報酬'], ['projected.staff_payable_due_date', '預估發薪日'], ['B24', '服務地址'], ['A97', '契約日期']],
} as const;

export function OrderContractPreview({ caseNo }: { caseNo: string }) {
  const [scope, setScope] = useState<'client' | 'staff'>('client');
  const [targets, setTargets] = useState<ContractExternalSigningQuery['staff_targets']>([]);
  const [segmentId, setSegmentId] = useState<number | null>(null);
  const [result, setResult] = useState<ContractFullPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(null); setResult(null);
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
    })().catch((reason: unknown) => {
      if (!controller.signal.aborted) {
        setError(reason instanceof Error && reason.message.trim()
          ? reason.message
          : '目前無法取得本案契約資料，原因尚無法辨識。');
      }
    })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [caseNo, scope, segmentId, revision]);
  return <section aria-label="契約套值欄位預覽">
    <div className="order-information-choice"><button type="button" aria-pressed={scope === 'client'} onClick={() => { setScope('client'); setResult(null); setError(null); }}><strong>客戶服務契約</strong><span>服務約定、費用與付款安排</span></button><button type="button" aria-pressed={scope === 'staff'} onClick={() => { setScope('staff'); setResult(null); setError(null); }}><strong>服務人員委任契約</strong><span>月嫂服務區段、報酬與責任</span></button></div>
    <p className="order-case-review-note">此處僅預覽主要套值欄位，不是完整契約或簽署完成證明。契約顯示預計繳款日；實際入帳日由帳務核銷紀錄。完整 PDF 請至「下載與簽回」。</p>
    <button type="button" disabled={loading} onClick={() => setRevision((value) => value + 1)}>{loading ? '讀取契約資料中…' : '重新讀取契約資料'}</button>
    {scope === 'staff' && targets.length > 1 && <label>選擇月嫂契約<select value={segmentId ?? ''} onChange={(event) => { setResult(null); setSegmentId(event.target.value ? Number(event.target.value) : null); }}><option value="">請選擇</option>{targets.map((target, index) => <option key={target.matching_segment_id} value={target.matching_segment_id}>月嫂 {target.staff_subject_reference} · 第 {index + 1} 份契約</option>)}</select></label>}
    {error && <p role="alert">無法取得本案契約資料：{error} 下方僅為版面，不能視為已產生文件。</p>}
    {result && result.warnings.length > 0 && <p role="status">目前資料仍有缺漏；已有內容可繼續預覽與下載，系統不會猜測或補造缺少的值。</p>}
    {result && !result.ready_to_print && <p role="alert">契約模板或文件產生發生技術問題，暫時無法產生文件。</p>}
    {result?.blockers.includes('contract_pdf_external_reference_unresolved') && <p role="alert">契約模板缺少舊版引用內容，暫不能產生可簽署 PDF。</p>}
    <article className="order-information-paper"><header><small>案件 {caseNo} · 套值欄位預覽</small><h3>{scope === 'client' ? '坐月子到府服務契約' : '到宅坐月子服務人員委任契約'}</h3></header><dl>{FIELDS[scope].map(([cell, label]) => {
      const value = result?.field_values[cell];
      const isEmpty = value == null || value === '';
      const fieldState = result?.field_states[cell];
      const isOptionalEmpty = isEmpty && (fieldState === 'optional_empty' || fieldState === 'not_applicable');
      const isMissing = !!result && isEmpty && fieldState === 'missing';
      return <div key={cell}><dt>{label}</dt><dd className={isMissing ? 'is-missing' : ''}>{isEmpty ? result ? isOptionalEmpty ? '未填（可留白）' : fieldState === 'unresolved' ? '模板欄位尚未設定' : '尚未提供／待核對' : '尚未讀取本案資料' : Array.isArray(value) ? value.join('、') : String(value)}</dd></div>;
    })}</dl></article>
  </section>;
}
