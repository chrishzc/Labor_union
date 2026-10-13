import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Filter } from 'lucide-react';
import { clientRegistryClient } from '../api/client_registry/client_registry_client';
import type { ClientRegistryColumnFilter, ClientRegistryFilterOperator, ClientRegistrySortOrder } from '../api/client_registry/client_registry_schemas';
import { operatorLabels, rosterFilterValueLabel, type RosterFilterColumn } from './client_roster_filter_columns';

interface Props {
  column: RosterFilterColumn;
  active?: ClientRegistryColumnFilter;
  disabled: boolean;
  onApply: (predicate: ClientRegistryColumnFilter | undefined) => void;
  onSort?: (order: ClientRegistrySortOrder) => void;
}

export function ClientRosterColumnFilter({ column, active, disabled, onApply, onSort }: Props) {
  const trigger = useRef<HTMLButtonElement>(null);
  const restoreFocus = useRef(false);
  const [open, setOpen] = useState(false);
  const close = useCallback(() => { restoreFocus.current = true; setOpen(false); }, []);
  useEffect(() => {
    if (!open && !disabled && restoreFocus.current) { trigger.current?.focus(); restoreFocus.current = false; }
  }, [open, disabled]);
  return <>
    <button type="button" ref={trigger} className={`client-roster-filter-trigger${active ? ' is-active' : ''}`} disabled={disabled}
      aria-label={`${column.label}篩選${active ? '（已套用）' : ''}`} aria-haspopup="dialog" aria-expanded={open} onClick={() => { if (open) close(); else setOpen(true); }}>
      {active ? <Filter size={15} aria-hidden="true" /> : <span aria-hidden="true">▾</span>}
    </button>
    {open && createPortal(<FilterPanel column={column} active={active} trigger={trigger} onClose={close}
      onApply={(predicate) => { onApply(predicate); close(); }} onSort={onSort ? (order) => { onSort(order); close(); } : undefined} />, document.body)}
  </>;
}

function FilterPanel({ column, active, trigger, onClose, onApply, onSort }: Omit<Props, 'disabled'> & { trigger: React.RefObject<HTMLButtonElement | null>; onClose: () => void }) {
  const panel = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ top: 0, left: 0, maxHeight: 500 });
  const [operator, setOperator] = useState<ClientRegistryFilterOperator>(active && !['in', 'not_in'].includes(active.operator) ? active.operator : 'in');
  const [selectionMode, setSelectionMode] = useState<'in' | 'not_in'>(active?.operator === 'in' ? 'in' : 'not_in');
  const [selected, setSelected] = useState<(string | null)[]>(active && ['in', 'not_in'].includes(active.operator) ? active.values : []);
  const [value, setValue] = useState(active && !['in', 'not_in'].includes(active.operator) ? active.values[0] ?? '' : '');
  const [upper, setUpper] = useState(active?.operator === 'between' ? active.values[1] ?? '' : '');
  const [search, setSearch] = useState('');
  const [options, setOptions] = useState<(string | null)[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const optionsRequest = useRef({ cancelled: false });
  const reposition = useCallback(() => {
    const rect = trigger.current!.getBoundingClientRect();
    const height = Math.min(panel.current?.scrollHeight ?? 520, window.innerHeight - 16);
    const top = Math.max(8, Math.min(rect.bottom + 6, window.innerHeight - height - 8));
    setPosition({ top, left: Math.max(8, Math.min(rect.left, window.innerWidth - 328)), maxHeight: window.innerHeight - top - 8 });
  }, [trigger]);

  useLayoutEffect(() => { reposition(); }, [options.length, operator, error, loading, nextOffset, reposition]);

  useEffect(() => {
    const triggerElement = trigger.current;
    reposition();
    panel.current?.querySelector<HTMLElement>('input,select,button')?.focus();
    const outside = (event: PointerEvent) => {
      if (!panel.current?.contains(event.target as Node) && !triggerElement?.contains(event.target as Node)) onClose();
    };
    document.addEventListener('pointerdown', outside);
    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', reposition, true);
    return () => {
      document.removeEventListener('pointerdown', outside);
      window.removeEventListener('resize', reposition);
      window.removeEventListener('scroll', reposition, true);
      triggerElement?.focus();
    };
  }, [trigger, onClose, reposition]);

  useEffect(() => {
    const request = { cancelled: false };
    optionsRequest.current = request;
    if (operator !== 'in') { setLoading(false); return () => { request.cancelled = true; }; }
    setLoading(true); setError(null); setOptions([]); setNextOffset(null);
    const timer = window.setTimeout(() => {
      void clientRegistryClient.filterOptions(column.field, column.kind === 'boolean' ? '' : search).then((result) => {
        if (request.cancelled) return;
        setOptions(column.kind === 'boolean' ? result.values.filter((value) => rosterFilterValueLabel(column, value).includes(search.trim())) : result.values); setNextOffset(result.next_offset);
      }).catch((caught: unknown) => {
        if (!request.cancelled) setError(caught instanceof Error ? caught.message : '篩選選項載入失敗。');
      }).finally(() => { if (!request.cancelled) setLoading(false); });
    }, search ? 250 : 0);
    return () => { window.clearTimeout(timer); request.cancelled = true; };
  }, [column, search, operator]);

  const moreOptions = async () => {
    if (nextOffset === null) return;
    const request = optionsRequest.current;
    setLoading(true); setError(null);
    try {
      const result = await clientRegistryClient.filterOptions(column.field, search, nextOffset);
      if (!request.cancelled) { setOptions((previous) => [...new Set([...previous, ...result.values])]); setNextOffset(result.next_offset); }
    } catch (caught) {
      if (!request.cancelled) setError(caught instanceof Error ? caught.message : '篩選選項載入失敗。');
    } finally { if (!request.cancelled) setLoading(false); }
  };
  const toggleValue = (option: string | null) => setSelected((previous) => previous.includes(option) ? previous.filter((item) => item !== option) : [...previous, option]);
  const type = column.kind === 'date' ? 'date' : column.kind === 'number' ? 'number' : 'text';
  const customOperators: ClientRegistryFilterOperator[] = column.kind === 'text' ? ['contains', 'starts_with', 'equals'] : column.kind === 'boolean' ? [] : ['equals', 'gt', 'lt', 'between'];
  const validRange = operator !== 'between' || (column.kind === 'number' ? Number(value) <= Number(upper) : value <= upper);
  const validNumber = (item: string) => /^[0-9]+$/.test(item) && Number(item) > 0;
  const canApply = operator === 'in' ? !error && !loading && selected.length <= 200 : operator === 'blank' || (value.trim().length > 0 && (column.kind !== 'number' || validNumber(value)) && (operator !== 'between' || upper.length > 0 && validRange && (column.kind !== 'number' || validNumber(upper))));
  const apply = (event: React.FormEvent) => {
    event.preventDefault();
    if (!canApply) return;
    if (operator === 'in') onApply(selectionMode === 'not_in' && !selected.length ? undefined : { field: column.field, operator: selectionMode, values: selected });
    else onApply({ field: column.field, operator, values: operator === 'blank' ? [] : operator === 'between' ? [value.trim(), upper.trim()] : [value.trim()] });
  };
  const monthRange = (offset: number) => {
    const today = new Date();
    const start = new Date(today.getFullYear(), today.getMonth() + offset, 1);
    const end = new Date(today.getFullYear(), today.getMonth() + offset + 1, 0);
    const iso = (item: Date) => `${item.getFullYear()}-${String(item.getMonth() + 1).padStart(2, '0')}-${String(item.getDate()).padStart(2, '0')}`;
    setOperator('between'); setValue(iso(start)); setUpper(iso(end));
  };
  return <div ref={panel} className="client-roster-column-panel" role="dialog" aria-label={`${column.label}篩選選項`} style={position}
    onKeyDown={(event) => { if (event.key === 'Escape') { event.preventDefault(); onClose(); } }}
    onBlur={(event) => { if (event.relatedTarget instanceof Node && !event.currentTarget.contains(event.relatedTarget) && event.relatedTarget !== trigger.current) onClose(); }}>
    <form onSubmit={apply}>
      <strong>{column.label}</strong>
      {onSort && <div className="client-roster-column-sort"><button type="button" onClick={() => onSort('asc')}>↑ 升冪排序</button><button type="button" onClick={() => onSort('desc')}>↓ 降冪排序</button></div>}
      <button type="button" className="client-roster-column-clear" onClick={() => onApply(undefined)}>清除此欄篩選</button>
      <label>篩選方式<select aria-label={`${column.label}篩選方式`} value={operator} onChange={(event) => setOperator(event.target.value as ClientRegistryFilterOperator)}>
        {(['in', ...customOperators, 'blank'] as ClientRegistryFilterOperator[]).map((item) => <option key={item} value={item}>{operatorLabels[item]}</option>)}
      </select></label>
      {column.kind === 'date' && <div className="client-roster-column-sort"><button type="button" onClick={() => monthRange(0)}>本月</button><button type="button" onClick={() => monthRange(1)}>下個月</button></div>}
      {operator === 'in' ? <>
        <label>搜尋選項<input aria-label={`${column.label}搜尋選項`} value={search} maxLength={100} placeholder="輸入關鍵字" onChange={(event) => setSearch(event.target.value)} /></label>
        <div className="client-roster-column-select-actions"><button type="button" onClick={() => { setSelectionMode('not_in'); setSelected([]); }}>全選</button><button type="button" onClick={() => { setSelectionMode('in'); setSelected([]); }}>取消全選</button></div>
        <p className="client-roster-column-hint">搜尋只縮小選項清單；全選包含此欄所有值。</p>
        <div className="client-roster-column-values">
          {options.map((option) => <label key={option ?? '(blank)'}><input type="checkbox" checked={selectionMode === 'in' ? selected.includes(option) : !selected.includes(option)} onChange={() => toggleValue(option)} />{rosterFilterValueLabel(column, option)}</label>)}
          {loading && <p role="status">載入選項中…</p>}
          {!loading && !error && !options.length && <p>沒有符合的選項。</p>}
          {nextOffset !== null && <button type="button" disabled={loading} onClick={() => void moreOptions()}>顯示更多選項</button>}
        </div>
        {selected.length > 200 && <p role="alert">勾選或排除的值超過 200 項，請改用文字或區間條件。</p>}
      </> : operator !== 'blank' && <>
        <label>{operator === 'between' ? '起始值' : '條件值'}<input aria-label={`${column.label}條件值`} type={type} min={type === 'number' ? 1 : undefined} step={type === 'number' ? 1 : undefined} maxLength={100} required value={value} onChange={(event) => setValue(event.target.value)} /></label>
        {operator === 'between' && <label>結束值<input aria-label={`${column.label}結束值`} type={type} min={type === 'number' ? 1 : undefined} required value={upper} onChange={(event) => setUpper(event.target.value)} /></label>}
        {!validRange && <p role="alert">結束值須大於或等於起始值。</p>}
      </>}
      {error && <p role="alert">{error}</p>}
      <div className="client-roster-column-footer"><button type="submit" disabled={!canApply}>確定</button><button type="button" onClick={onClose}>取消</button></div>
    </form>
  </div>;
}
