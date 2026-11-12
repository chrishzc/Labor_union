/**
 * File: ClientBeClassWorkbookPairing.tsx
 * Description: 客戶 BeClass 工作簿預覽的左右核對、連線及人工確認。
 */
import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Drawer } from './Drawer';
import type { ClientBeClassWorkbookPreviewModel } from '../adapters/case_import/client_beclass_workbook_adapter';
import type { ClientBeClassPairing } from '../api/case_import/client_beclass_workbook/schemas';

interface Props {
  preview: ClientBeClassWorkbookPreviewModel;
  onConfirm: (pairings: readonly ClientBeClassPairing[]) => void;
}

type ManualRow = ClientBeClassWorkbookPreviewModel['manualRows'][number];

function groupBySharedCases(rows: ManualRow[]) {
  const rowsByCase = new Map<string, ManualRow[]>();
  for (const row of rows) {
    for (const caseNo of row.case_nos) {
      const matches = rowsByCase.get(caseNo) ?? [];
      matches.push(row);
      rowsByCase.set(caseNo, matches);
    }
  }

  const unseen = new Set(rows);
  const groups: Array<{ rows: ManualRow[]; caseNos: Set<string> }> = [];
  for (const row of rows) {
    if (!unseen.delete(row)) continue;
    const group = { rows: [row], caseNos: new Set<string>() };
    // Follow shared candidates transitively so a case only appears in one group.
    for (const member of group.rows) {
      for (const caseNo of member.case_nos) {
        if (group.caseNos.has(caseNo)) continue;
        group.caseNos.add(caseNo);
        for (const related of rowsByCase.get(caseNo) ?? []) {
          if (unseen.delete(related)) group.rows.push(related);
        }
      }
    }
    group.rows.sort((left, right) => left.source_row - right.source_row);
    groups.push(group);
  }
  return groups;
}

function ComparisonFacts({ name, phone, city, dateLabel, date, start }: {
  name: string; phone: string; city: string | null; dateLabel: string;
  date: string | null; start?: string | null;
}) {
  return <span className="beclass-pairing-facts">
    <span><small>客戶</small> {name} · {phone}</span>
    <span><small>縣市</small> {city || '未提供'}</span>
    <span><small>{dateLabel}</small> {date?.replace('T', ' ') || '未提供'}</span>
    {start !== undefined && <span><small>預計服務日期</small> <strong>{start || '未提供'}</strong></span>}
  </span>;
}

export function ClientBeClassWorkbookPairing({ preview, onConfirm }: Props) {
  const [open, setOpen] = useState(false);
  const [groupIndex, setGroupIndex] = useState(0);
  const [selected, setSelected] = useState(new Map<number, string[]>());
  const [activeRow, setActiveRow] = useState<number | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [paths, setPaths] = useState<Array<{ caseNo: string; path: string }>>([]);
  const boardRef = useRef<HTMLDivElement>(null);
  const checkRef = useRef<HTMLButtonElement>(null);
  const backRef = useRef<HTMLButtonElement>(null);
  const sourcePorts = useRef(new Map<number, HTMLSpanElement>());
  const casePorts = useRef(new Map<string, HTMLSpanElement>());
  const { manualRows, candidates } = preview;
  const groups = useMemo(() => groupBySharedCases(manualRows), [manualRows]);
  const candidatesByCase = useMemo(() => new Map(candidates.map(item => [item.case_no, item])), [candidates]);
  const group = groups[groupIndex];
  const groupRows = group?.rows ?? [];
  const groupCases = [...(group?.caseNos ?? [])].flatMap(caseNo => {
    const candidate = candidatesByCase.get(caseNo);
    return candidate ? [candidate] : [];
  });
  const active = groupRows.find(row => row.source_row === activeRow);
  const activeCases = active ? selected.get(active.source_row) ?? [] : [];
  const activeClient = candidatesByCase.get(activeCases[0])?.client_id;
  const ownerByCase = new Map(groupRows.flatMap((row, index) =>
    (selected.get(row.source_row) ?? []).map(caseNo => [caseNo, { row, alternate: index % 2 === 1 }] as const)
  ));

  useLayoutEffect(() => {
    const board = boardRef.current;
    if (!open || confirming || !board) return;
    const draw = () => {
      const frame = board.getBoundingClientRect();
      setPaths(Array.from(sourcePorts.current).flatMap(([row, port]) => (selected.get(row) ?? []).flatMap(caseNo => {
        const source = port.getBoundingClientRect();
        const target = casePorts.current.get(caseNo)?.getBoundingClientRect();
        if (!target) return [];
        const x1 = source.left + source.width / 2 - frame.left;
        const y1 = source.top + source.height / 2 - frame.top;
        const x2 = target.left + target.width / 2 - frame.left;
        const y2 = target.top + target.height / 2 - frame.top;
        const middle = (x1 + x2) / 2;
        return [{ caseNo, path: `M ${x1} ${y1} C ${middle} ${y1}, ${middle} ${y2}, ${x2} ${y2}` }];
      })));
    };
    draw();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(draw);
    observer?.observe(board);
    for (const port of [...sourcePorts.current.values(), ...casePorts.current.values()]) {
      if (port.parentElement) observer?.observe(port.parentElement);
    }
    return () => observer?.disconnect();
  }, [activeRow, confirming, groupIndex, open, selected]);

  const pairings = Array.from(selected).flatMap(([source_row, caseNos]) =>
    caseNos.map(case_no => ({ source_row, case_no }))
  );
  const confirm = () => onConfirm(pairings);
  useLayoutEffect(() => {
    if (confirming) backRef.current?.focus();
    else checkRef.current?.focus();
  }, [confirming]);
  const progress = `已配對 ${selected.size} / ${manualRows.length} 筆`;
  const notImported = preview.reviewRequiredCount + preview.existingConflictCount;

  const pendingByGroup = groups.map(item => item.rows.filter(row => !selected.has(row.source_row)).length);
  const nextPending = pendingByGroup.findIndex((pending, index) => index > groupIndex && pending > 0);
  const nextGroup = nextPending === -1 ? pendingByGroup.findIndex((pending, index) => index !== groupIndex && pending > 0) : nextPending;
  const chooseGroup = (index: number) => {
    setActiveRow(null);
    setGroupIndex(index);
  };

  return <section className="beclass-pairing" aria-label="人工配對">
    <p>可直接匯入 {preview.createCount} 筆 · 待配對 {manualRows.length - selected.size} 筆 · 重複略過 {preview.existingSourceCount} 筆 · 未匯入 {notImported} 筆</p>
    <div className="beclass-pairing-actions">
      <p>{groups.length} 組 · {progress}</p>
      <button type="button" className="import-apply-btn" onClick={() => setOpen(true)}>開啟人工配對</button>
    </div>
    <Drawer isOpen={open} onClose={() => { setOpen(false); setActiveRow(null); }}
      title={confirming ? '確認這次的配對' : '客戶 BeClass 人工配對'} closeLabel="關閉配對抽屜" size="xl"
      footer={<div className="beclass-drawer-actions">
        <p role="status">{progress}{active ? ` · 已選 ${active.query_no}，請點右側案件` : ''}</p>
        {confirming ? <>
          <button ref={backRef} type="button" className="beclass-pairing-secondary" onClick={() => setConfirming(false)}>返回修改</button>
          <button type="button" className="import-apply-btn" onClick={confirm}>確認匯入</button>
        </> : <>
          {nextGroup !== -1 && <button type="button" className="beclass-pairing-secondary" onClick={() => chooseGroup(nextGroup)}>下一組待配對</button>}
          <button ref={checkRef} type="button" className="import-apply-btn" disabled={selected.size !== manualRows.length}
            onClick={() => { setActiveRow(null); setConfirming(true); }}>檢查配對</button>
        </>}
      </div>}>
    <div className="beclass-pairing">
    {groups.length > 1 && <label className="beclass-group-picker">
      配對組別
      <select value={groupIndex} onChange={event => chooseGroup(Number(event.target.value))}>
        {groups.map((item, index) => <option key={item.rows[0].source_row} value={index}>
          第 {index + 1} 組 · {item.rows[0].name} · 第 {item.rows[0].source_row} 列起 · {pendingByGroup[index] ? `待配對 ${pendingByGroup[index]} 筆` : '已配對'}
        </option>)}
      </select>
    </label>}
    {confirming ? <>
      <p>{preview.createCount} 筆可直接匯入、{selected.size} 份問卷將套用至 {pairings.length} 個案件、{preview.existingSourceCount} 筆重複略過、{notImported} 筆未匯入。</p>
      <ul className="beclass-confirmed-pairs">
        {groupRows.map(row => <li key={row.source_row}>第 {row.source_row} 列 · {row.query_no} → <strong>{selected.get(row.source_row)?.join('、')}</strong></li>)}
      </ul>
    </> : <>
    <p>先點左側問卷，再勾選右側同一位客戶的案件。再次點選案件可解除連線。</p>
    <div className="beclass-pairing-board" ref={boardRef}>
      <svg className="beclass-pairing-wires" aria-hidden="true">
        {paths.map(({ caseNo, path }) => <path key={caseNo} d={path}
          className={ownerByCase.get(caseNo)?.alternate ? 'alternate' : undefined} />)}
      </svg>
      <section className="beclass-pairing-column" aria-label="BeClass 問卷">
        <h5>BeClass 問卷</h5>
        {groupRows.map((row, index) => {
          const match = selected.get(row.source_row);
          const isActive = activeRow === row.source_row;
          return <div key={row.source_row} className={`beclass-pairing-card source${isActive ? ' active' : ''}${match ? ' linked' : ''}${index % 2 === 1 ? ' alternate' : ''}`}>
            <button className="beclass-pairing-pick" type="button" aria-pressed={isActive}
              onClick={() => setActiveRow(row.source_row)}>
              <strong>{row.query_no}</strong>
              <small>Excel 第 {row.source_row} 列</small>
              <ComparisonFacts name={row.name} phone={row.masked_phone} city={row.city} dateLabel="問卷報名時間" date={row.submitted_at} />
              <span className="beclass-pairing-state">{match ? `已連 ${match.join('、')}` : isActive ? '已選取，請點右側' : '待配對'}</span>
            </button>
            <span className="beclass-pairing-port" aria-hidden="true" ref={node => {
              if (node) sourcePorts.current.set(row.source_row, node);
              else sourcePorts.current.delete(row.source_row);
            }} />
            {match && <button className="beclass-pairing-unlink" type="button" aria-label={`解除 ${row.query_no} 的配對`} onClick={event => {
              setSelected(previous => {
                const updated = new Map(previous);
                updated.delete(row.source_row);
                return updated;
              });
              setActiveRow(row.source_row);
              event.currentTarget.parentElement?.querySelector('button')?.focus();
            }}>解除連線</button>}
          </div>;
        })}
      </section>
      <section className="beclass-pairing-column" aria-label="HCM 候選案件">
        <h5>HCM 候選案件</h5>
        {groupCases.map(item => {
          const assigned = ownerByCase.get(item.case_no);
          const owner = assigned?.row;
          const canSelect = active !== undefined && active.case_nos.includes(item.case_no)
            && (!owner || owner === active) && (activeClient === undefined || activeClient === item.client_id);
          return <div key={item.case_no} className={`beclass-pairing-card target${owner ? ' linked' : ''}${assigned?.alternate ? ' alternate' : ''}`}>
            <button className="beclass-pairing-pick" type="button" aria-disabled={!canSelect} aria-pressed={owner !== undefined} onClick={() => {
              if (!canSelect) return;
              setSelected(previous => {
                const updated = new Map(previous);
                const cases = previous.get(active.source_row) ?? [];
                const next = cases.includes(item.case_no)
                  ? cases.filter(caseNo => caseNo !== item.case_no) : [...cases, item.case_no];
                if (next.length) updated.set(active.source_row, next);
                else updated.delete(active.source_row);
                return updated;
              });
            }}>
              <strong>{item.case_no}</strong>
              <ComparisonFacts name={item.name} phone={item.masked_phone} city={item.city} dateLabel="HCM 建檔時間" date={item.created_at} start={item.start_date} />
              <span className="beclass-pairing-state">{owner ? `已連 ${owner.query_no}` : active && !canSelect ? '目前不可配對' : '可配對'}</span>
            </button>
            <span className="beclass-pairing-port" aria-hidden="true" ref={node => {
              if (node) casePorts.current.set(item.case_no, node);
              else casePorts.current.delete(item.case_no);
            }} />
          </div>;
        })}
      </section>
    </div>
    </>}
    </div>
    </Drawer>
  </section>;
}
