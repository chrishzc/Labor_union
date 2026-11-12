/** Monthly, quarterly and annual staff performance presentation. */
import { useEffect, useMemo, useRef, useState } from 'react';
import { X, Download } from 'lucide-react';
import { compareStaffUnionNumbers, staffDisplayLabel } from '../../adapters/staff/staff_directory_adapter';
import { staffPerformanceClient, type PerformanceFilters, type PerformanceMetric, type StaffPerformanceReport, type StaffPerformanceRow } from '../../api/reports/staff_performance_client';
import './StaffPerformancePanel.css';

const labels: Record<PerformanceMetric, string> = { case_count: '接案數', service_hours: '服務工時（含歷史估算）', total_amount_ntd: '本期認列金額' };
const number = (value: number | null) => value === null ? '—' : value.toLocaleString('zh-TW', { maximumFractionDigits: 1 });
const money = (value: number | null) => value === null ? '待確認' : `NT$ ${number(value)}`;
const display = (value: number | null, metric: PerformanceMetric) => metric === 'total_amount_ntd' ? money(value) : number(value);
const units: Record<PerformanceMetric, string> = { case_count: '件', service_hours: '小時', total_amount_ntd: '元' };
const metrics = ['service_hours', 'case_count', 'total_amount_ntd'] as const;
function initialFilters(): PerformanceFilters {
  const parts = new Intl.DateTimeFormat('en', { timeZone: 'Asia/Taipei', year: 'numeric', month: 'numeric' }).formatToParts(new Date());
  const year = Number(parts.find(p => p.type === 'year')?.value);
  const month = Number(parts.find(p => p.type === 'month')?.value);
  return { year, month, quarter: Math.ceil(month / 3), period: 'month' };
}
function rank(row: StaffPerformanceRow, rows: StaffPerformanceRow[], metric: PerformanceMetric) {
  const value = row.totals[metric];
  return value === null || value <= 0 ? null : 1 + rows.filter(item => item.totals[metric] !== null && item.totals[metric]! > value).length;
}
function change(row: StaffPerformanceRow, metric: PerformanceMetric) {
  const current = row.totals[metric], previous = row.previous_totals[metric];
  if (current === null || previous === null || previous === 0) return '—';
  const percent = (current - previous) / previous * 100;
  return `${percent > 0 ? '+' : ''}${percent.toFixed(1)}%`;
}
function MetricButtons({ value, onChange }: { value: PerformanceMetric; onChange: (value: PerformanceMetric) => void }) {
  return <div className="performance-metrics">{metrics.map(metric => <button key={metric} type="button" aria-pressed={value === metric} onClick={() => onChange(metric)}>{labels[metric]}</button>)}</div>;
}
function Trend({ points, metric }: { points: StaffPerformanceReport['trend']; metric: PerformanceMetric }) {
  if (!points.length) return <p className="performance-empty">此期間沒有服務資料。</p>;
  const max = Math.max(1, ...points.map(point => point.totals[metric] ?? 0));
  const x = (i: number) => 48 + (points.length === 1 ? 224 : i * 448 / (points.length - 1));
  const y = (value: number) => 138 - value / max * 112;
  const segments: string[] = []; let current = '';
  points.forEach((point, i) => { const value = point.totals[metric]; if (value === null) { if (current) segments.push(current); current = ''; } else current += `${current ? ' L' : 'M'}${x(i)},${y(value)}`; });
  if (current) segments.push(current);
  return <svg className="performance-trend" viewBox="0 0 520 180" role="img" aria-label={`${labels[metric]}趨勢`}>
    {[0, 1, 2, 3].map(i => <g key={i}><line x1="48" x2="496" y1={26 + i * 112 / 3} y2={26 + i * 112 / 3} className="performance-gridline" /><text x="40" y={30 + i * 112 / 3} textAnchor="end">{metric === 'total_amount_ntd' ? `${number(max * (1 - i / 3) / 10000)}萬` : number(Math.round(max * (1 - i / 3)))}</text></g>)}
    {segments.map((segment, i) => <path key={i} d={segment} fill="none" className="performance-line" />)}
    {points.map((point, i) => <g key={point.start_date}>{point.totals[metric] !== null && <circle cx={x(i)} cy={y(point.totals[metric]!)} r="3"><title>{`${point.start_date}：${display(point.totals[metric], metric)} ${units[metric]}`}</title></circle>}{(points.length <= 12 || i % 5 === 0 || i === points.length - 1) && <text x={x(i)} y="165" textAnchor="middle">{point.label}</text>}</g>)}
  </svg>;
}

function StaffDetail({ row, rows, period, staffOptions, onClose }: { row: StaffPerformanceRow; rows: StaffPerformanceRow[]; period: string; staffOptions: StaffPerformanceReport['staff_options']; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [metric, setMetric] = useState<PerformanceMetric>('service_hours');
  useEffect(() => {
    const element = dialog.current;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element?.showModal();
    return () => { element?.close(); queueMicrotask(() => { if (opener?.isConnected) opener.focus(); }); };
  }, []);
  return <dialog ref={dialog} className="performance-drawer" aria-labelledby="performance-detail-title" onCancel={event => { event.preventDefault(); onClose(); }} onClick={event => { if (event.target === event.currentTarget) { const bounds = event.currentTarget.getBoundingClientRect(); if (event.clientX < bounds.left || event.clientX > bounds.right) onClose(); } }}>
    <header className="performance-drawer-header"><div><span className="performance-pill">個人表現分析</span><h2 id="performance-detail-title">{staffDisplayLabel(row.union_no, row.staff_name)}</h2><p>{period}</p></div><button type="button" className="performance-close" aria-label="關閉個人分析" onClick={onClose}><X size={20} /></button></header>
    <div className="performance-drawer-body"><div className="performance-person-kpis">{(['case_count', 'service_hours', 'total_amount_ntd'] as const).map(key => <article key={key}><span>{labels[key]}</span><strong>{display(row.totals[key], key)}</strong><small>{rank(row, rows, key) === null ? '—' : `第 ${rank(row, rows, key)} 名`}</small></article>)}</div>
      <section className="performance-panel"><h3>個人服務趨勢</h3><MetricButtons value={metric} onChange={setMetric} /><Trend points={row.trend} metric={metric} /></section>
      <section className="performance-panel performance-table-panel"><div className="performance-table-heading"><h3>案件明細 <small>{row.cases.length} 件</small></h3></div><div className="performance-table-scroll" role="region" aria-label="個人服務案件，可左右捲動" tabIndex={0}><table><thead><tr><th>案件／開案主責</th><th>本期服務日期</th><th className="numeric">{labels.service_hours}</th><th className="numeric">整案總額</th><th className="numeric">本期認列金額</th></tr></thead><tbody>{row.cases.map(item => {
        const primary = staffOptions.find(staff => staff.staff_id === item.primary_staff_id);
        return <tr key={item.case_no}><td><a href={`#order-workbench-v2?case=${encodeURIComponent(item.case_no)}`}>{item.case_no}</a><small className="performance-staff-number">開案：{item.actual_start_date ?? '待確認'}</small><small className="performance-staff-number">主責：<span>{primary ? staffDisplayLabel(primary.union_no, primary.staff_name) : '待確認'}</span></small></td><td>{item.service_start ?? '—'}{item.service_end && <small className="performance-staff-number">至 {item.service_end}</small>}</td><td className="numeric">{number(item.service_hours)}</td><td className="numeric">{money(item.total_amount_ntd)}</td><td className="numeric">{money(item.recognized_amount_ntd)}</td></tr>;
      })}</tbody></table>{!row.cases.length && <p className="performance-empty">本期沒有服務或認列案件。</p>}</div></section>
    </div>
  </dialog>;
}

export function StaffPerformancePanel({ initialStaffId }: { initialStaffId?: number }) {
  const [filters, setFilters] = useState<PerformanceFilters>(() => ({ ...initialFilters(), ...(initialStaffId ? { staff_id: initialStaffId } : {}) }));
  const [report, setReport] = useState<StaffPerformanceReport | null>(null);
  const [options, setOptions] = useState<StaffPerformanceReport['staff_options']>([]);
  const [years, setYears] = useState<number[]>([filters.year]);
  const [metric, setMetric] = useState<PerformanceMetric>('service_hours');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState(''); const [reload, setReload] = useState(0);
  const [exporting, setExporting] = useState(false); const [exportMessage, setExportMessage] = useState('');
  const sequence = useRef(0); const exportController = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController(), request = ++sequence.current;
    void staffPerformanceClient.query(filters, controller.signal).then(value => {
      if (!controller.signal.aborted && request === sequence.current) { setReport(value); setOptions(value.staff_options); setYears(value.available_years); }
    }).catch(reason => { if (!controller.signal.aborted && request === sequence.current) setError(reason instanceof Error ? reason.message : '月嫂表現分析載入失敗。'); });
    return () => controller.abort();
  }, [filters, reload]);
  useEffect(() => () => exportController.current?.abort(), []);
  const update = (next: PerformanceFilters) => { sequence.current++; exportController.current?.abort(); setExporting(false); setExportMessage(''); setReport(null); setSelectedId(null); setError(''); setFilters(next); };
  const rows = useMemo(() => [...(report?.rows ?? [])].sort((a, b) => {
    const left = a.totals[metric], right = b.totals[metric];
    return Number(left === null) - Number(right === null) || (right ?? 0) - (left ?? 0)
      || compareStaffUnionNumbers({ id: a.staff_id, unionNo: a.union_no }, { id: b.staff_id, unionNo: b.union_no });
  }), [report, metric]);
  const sortedOptions = useMemo(() => [...options].sort((a, b) => compareStaffUnionNumbers({ id: a.staff_id, unionNo: a.union_no }, { id: b.staff_id, unionNo: b.union_no })), [options]);
  const top = rows.filter(row => row.totals[metric] !== null && row.totals[metric]! > 0).slice(0, 5);
  const max = Math.max(1, ...top.map(row => row.totals[metric] ?? 0));
  const selected = rows.find(row => row.staff_id === selectedId);
  const download = async () => {
    exportController.current?.abort(); const controller = new AbortController(); exportController.current = controller;
    setExporting(true); setExportMessage('');
    try { const result = await staffPerformanceClient.download(filters, metric, controller.signal); if (controller.signal.aborted) return;
      const url = URL.createObjectURL(result.blob), link = document.createElement('a'); link.href = url; link.download = result.filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); setExportMessage('XLSX 已開始下載。');
    } catch (reason) { if (!controller.signal.aborted) setExportMessage(reason instanceof Error ? reason.message : '匯出失敗，請重試。'); }
    finally { if (!controller.signal.aborted) setExporting(false); }
  };
  const periodLabel = `${filters.year}年${filters.period === 'month' ? `${filters.month}月` : filters.period === 'quarter' ? `第${filters.quarter}季` : '全年'}`;
  return <div className="staff-performance" data-surface-id="reports.staff-performance">
    <section className="performance-filters" aria-label="月嫂表現分析篩選"><div className="performance-filter-row"><div className="performance-field"><span>統計週期</span><div className="performance-period">{(['month', 'quarter', 'year'] as const).map((period, i) => <button key={period} type="button" aria-pressed={filters.period === period} onClick={() => update({ ...filters, period })}>{['月', '季', '年'][i]}</button>)}</div></div>
      <label className="performance-field"><span>年度</span><select value={filters.year} onChange={event => update({ ...filters, year: Number(event.target.value) })}>{years.map(year => <option key={year} value={year}>{year - 1911} 年（{year}）</option>)}</select></label>
      {filters.period === 'month' && <label className="performance-field"><span>月份</span><select value={filters.month} onChange={event => update({ ...filters, month: Number(event.target.value) })}>{Array.from({ length: 12 }, (_, i) => <option key={i} value={i + 1}>{i + 1} 月</option>)}</select></label>}
      {filters.period === 'quarter' && <label className="performance-field"><span>季度</span><select value={filters.quarter} onChange={event => update({ ...filters, quarter: Number(event.target.value) })}>{[1, 2, 3, 4].map(q => <option key={q} value={q}>第 {q} 季</option>)}</select></label>}
      <label className="performance-field performance-staff-select"><span>月嫂</span><select value={filters.staff_id ?? ''} onChange={event => update({ ...filters, staff_id: event.target.value ? Number(event.target.value) : undefined })}><option value="">全部月嫂</option>{sortedOptions.map(staff => <option key={staff.staff_id} value={staff.staff_id}>{staffDisplayLabel(staff.union_no, staff.staff_name)}</option>)}</select></label>
      <button type="button" className="performance-button" onClick={() => { setMetric('service_hours'); update(initialFilters()); }}>重設</button><button type="button" className="performance-button primary" disabled={!report || exporting} onClick={() => void download()}><Download size={15} />{exporting ? '正在匯出…' : '匯出 XLSX'}</button></div>
      {report && <div className="performance-period-meta"><span>統計期間　{periodLabel}</span><span>資料截至 {report.through_date} · 金額單位：新臺幣</span></div>}
    </section>
    {exportMessage && <p className="performance-state" role="status">{exportMessage}</p>}
    {error ? <div className="performance-state" role="alert">{error}<button type="button" className="performance-button" onClick={() => { setError(''); setReport(null); setReload(value => value + 1); }}>重新查詢</button></div> : !report ? <p className="performance-state" role="status">正在載入月嫂表現分析…</p> : <>
      <section className="performance-kpis" aria-label="本期摘要"><article><span>本期服務月嫂數</span><strong>{number(report.service_staff_count)}<small>位</small></strong></article>{(['case_count', 'service_hours', 'total_amount_ntd'] as const).map(key => <article key={key} className={metric === key ? 'active' : ''}><span>{labels[key]}</span><strong>{number(report.totals[key])}<small>{units[key]}</small></strong></article>)}</section>
      <div className="performance-charts"><section className="performance-panel"><div className="performance-panel-heading"><div><h2>月嫂表現排行</h2><p>依{labels[metric]}排序</p></div><span className="performance-pill">前 5 名</span></div><MetricButtons value={metric} onChange={setMetric} /><div className="performance-bars">{top.map(row => <div key={row.staff_id} className="performance-bar-row"><span className={`performance-rank ${rank(row, rows, metric) === 1 ? 'first' : ''}`}>{rank(row, rows, metric)}</span><button type="button" className="performance-name" onClick={() => setSelectedId(row.staff_id)}>{row.staff_name}<small>{row.union_no ?? '未設定'}</small></button><div className="performance-bar-track"><div style={{ width: `${(row.totals[metric] ?? 0) / max * 100}%` }} /></div><span className="performance-bar-value">{metric === 'total_amount_ntd' ? `${number((row.totals[metric] ?? 0) / 10000)}萬` : number(row.totals[metric])}</span></div>)}{!top.length && <p className="performance-empty">本期沒有可排名的資料。</p>}</div></section>
        <section className="performance-panel"><div className="performance-panel-heading"><div><h2>本期服務趨勢</h2><p>每月{labels[metric]}</p></div><span className="performance-pill">{labels[metric]}</span></div><Trend points={report.trend} metric={metric} /></section></div>
      <section className="performance-panel performance-table-panel"><div className="performance-table-heading"><h2>月嫂表現比較 <small>{rows.length} 位月嫂</small></h2><span>依{labels[metric]}由高至低</span></div><div className="performance-table-scroll" role="region" aria-label="月嫂表現比較，可左右捲動" tabIndex={0}><table aria-label="月嫂表現比較"><thead><tr><th>排名</th><th>月嫂</th>{(['case_count', 'service_hours', 'total_amount_ntd'] as const).map(key => <th key={key} className="numeric" aria-sort={metric === key ? 'descending' : undefined}><button type="button" className={metric === key ? 'selected' : ''} onClick={() => setMetric(key)}>{labels[key]}{metric === key ? ' ↓' : ''}</button></th>)}<th className="numeric">較前期</th><th>個人分析</th></tr></thead><tbody>{rows.map(row => <tr key={row.staff_id}><td><span className={`performance-rank ${rank(row, rows, metric) === 1 ? 'first' : ''}`}>{rank(row, rows, metric) ?? '—'}</span></td><td><button type="button" className="performance-name" onClick={() => setSelectedId(row.staff_id)}>{row.staff_name}</button><small className="performance-staff-number">{row.union_no ?? '未設定'}</small></td><td className="numeric">{number(row.totals.case_count)}</td><td className="numeric">{number(row.totals.service_hours)}</td><td className="numeric">{money(row.totals.total_amount_ntd)}</td><td className="numeric">{change(row, metric)}</td><td><button type="button" className="performance-detail-button" onClick={() => setSelectedId(row.staff_id)}>查看明細 →</button></td></tr>)}</tbody></table>{!rows.length && <p className="performance-empty">沒有符合條件的月嫂。</p>}</div></section>
      {selected && <StaffDetail row={selected} rows={rows} period={periodLabel} staffOptions={report.staff_options} onClose={() => setSelectedId(null)} />}
    </>}
  </div>;
}
