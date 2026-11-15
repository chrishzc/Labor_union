/**
 * File: RosterTableLayout.tsx
 * Description: 提供名冊表格共用排版控制，包含可調欄寬、自動貼齊、自訂顯示/隱藏及任意欄位凍結。
 */
import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import './RosterTableLayout.css';

export interface RosterColumnDefinition<TId extends string = string> {
  id: TId;
  label: string;
  group: string;
  defaultWidth: number;
  minWidth?: number;
  maxWidth?: number;
  locked?: boolean;
  defaultFrozen?: boolean;
}

interface RosterLayoutState<TId extends string> {
  visibleIds: Set<TId>;
  frozenIds: Set<TId>;
  widths: Record<TId, number>;
}

interface PersistedRosterLayout {
  version: 1;
  visibleIds: string[];
  frozenIds: string[];
  widths: Record<string, number>;
}

const DEFAULT_MIN_WIDTH = 64;
const DEFAULT_MAX_WIDTH = 480;

function clampWidth(width: number, minWidth = DEFAULT_MIN_WIDTH, maxWidth = DEFAULT_MAX_WIDTH): number {
  if (!Number.isFinite(width)) return minWidth;
  return Math.max(minWidth, Math.min(maxWidth, Math.round(width)));
}

function createDefaultState<TId extends string>(columns: readonly RosterColumnDefinition<TId>[]): RosterLayoutState<TId> {
  const visibleIds = new Set<TId>(columns.map((col) => col.id));
  const frozenIds = new Set<TId>(columns.filter((col) => col.defaultFrozen).map((col) => col.id));
  const widths = Object.fromEntries(
    columns.map((col) => [col.id, clampWidth(col.defaultWidth, col.minWidth, col.maxWidth)]),
  ) as Record<TId, number>;
  return { visibleIds, frozenIds, widths };
}

function loadPersistedState<TId extends string>(
  columns: readonly RosterColumnDefinition<TId>[],
  storageKey?: string,
): RosterLayoutState<TId> {
  const fallback = createDefaultState(columns);
  if (!storageKey || typeof window === 'undefined' || !window.localStorage) return fallback;
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<PersistedRosterLayout> | null;
    if (!parsed || typeof parsed !== 'object') return fallback;

    const colMap = new Map(columns.map((col) => [col.id, col]));
    const visibleIds = Array.isArray(parsed.visibleIds)
      ? new Set<TId>(
          parsed.visibleIds.filter((id): id is TId => typeof id === 'string' && colMap.has(id as TId)),
        )
      : new Set(fallback.visibleIds);
    for (const col of columns) {
      if (col.locked) visibleIds.add(col.id);
    }
    if (visibleIds.size === 0 && columns.length > 0) {
      visibleIds.add(columns[0].id);
    }

    const frozenIds = Array.isArray(parsed.frozenIds)
      ? new Set<TId>(
          parsed.frozenIds.filter((id): id is TId => typeof id === 'string' && colMap.has(id as TId)),
        )
      : new Set(fallback.frozenIds);

    const widths = { ...fallback.widths };
    if (parsed.widths && typeof parsed.widths === 'object') {
      for (const col of columns) {
        const candidate = (parsed.widths as Record<string, unknown>)[col.id];
        if (typeof candidate === 'number' && Number.isFinite(candidate)) {
          widths[col.id] = clampWidth(candidate, col.minWidth, col.maxWidth);
        }
      }
    }

    return { visibleIds, frozenIds, widths };
  } catch {
    return fallback;
  }
}

function measureTextWidth(text: string, bold: boolean): number {
  if (typeof document !== 'undefined') {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext?.('2d');
    if (ctx) {
      ctx.font = `${bold ? '700' : '400'} 14px system-ui, -apple-system, sans-serif`;
      return ctx.measureText(text).width;
    }
  }
  let estimate = 0;
  for (const ch of text) {
    estimate += ch.charCodeAt(0) > 127 ? 14 : 8;
  }
  return estimate;
}

export interface RosterTableLayoutState<
  TId extends string = string,
  TCol extends RosterColumnDefinition<TId> = RosterColumnDefinition<TId>,
> {
  columns: readonly TCol[];
  orderedVisibleColumns: readonly TCol[];
  visibleIds: ReadonlySet<TId>;
  frozenIds: ReadonlySet<TId>;
  widths: Readonly<Record<TId, number>>;
  stickyOffsets: Partial<Record<TId, number>>;
  lastStickyId: TId | null;
  totalWidth: number;
  getThProps: (id: TId, extraClassName?: string) => { className?: string; style?: React.CSSProperties };
  getTdProps: (id: TId, extraClassName?: string) => { className?: string; style?: React.CSSProperties };
  toggleColumnVisibility: (id: TId) => void;
  hideColumn: (id: TId) => void;
  selectAllColumns: () => void;
  deselectAllColumns: () => void;
  toggleColumnFreeze: (id: TId) => void;
  clearFrozenColumns: () => void;
  setColumnWidth: (id: TId, width: number) => void;
  autoFitColumn: (id: TId, tableEl: HTMLTableElement | null) => void;
  resetLayout: () => void;
}

export function useRosterTableLayout<
  TId extends string,
  TCol extends RosterColumnDefinition<TId> = RosterColumnDefinition<TId>,
>({
  columns,
  storageKey,
}: {
  columns: readonly TCol[];
  storageKey?: string;
}): RosterTableLayoutState<TId, TCol> {
  const [state, setState] = useState<RosterLayoutState<TId>>(() => loadPersistedState(columns, storageKey));

  const columnMap = useMemo(() => new Map(columns.map((col) => [col.id, col])), [columns]);

  useEffect(() => {
    if (!storageKey || typeof window === 'undefined' || !window.localStorage) return;
    try {
      const payload: PersistedRosterLayout = {
        version: 1,
        visibleIds: Array.from(state.visibleIds),
        frozenIds: Array.from(state.frozenIds),
        widths: state.widths,
      };
      window.localStorage.setItem(storageKey, JSON.stringify(payload));
    } catch {
      // Ignore storage quota or restricted-environment errors without breaking table interaction.
    }
  }, [state, storageKey]);

  const orderedVisibleColumns = useMemo(() => {
    const visible = columns.filter((col) => state.visibleIds.has(col.id));
    const frozen = visible.filter((col) => state.frozenIds.has(col.id));
    const regular = visible.filter((col) => !state.frozenIds.has(col.id));
    return [...frozen, ...regular];
  }, [columns, state.visibleIds, state.frozenIds]);

  const { stickyOffsets, lastStickyId, totalWidth } = useMemo(() => {
    const offsets: Partial<Record<TId, number>> = {};
    let leftAcc = 0;
    let lastId: TId | null = null;
    let total = 0;
    for (const col of orderedVisibleColumns) {
      const width = state.widths[col.id] ?? col.defaultWidth;
      if (state.frozenIds.has(col.id)) {
        offsets[col.id] = leftAcc;
        leftAcc += width;
        lastId = col.id;
      }
      total += width;
    }
    return { stickyOffsets: offsets, lastStickyId: lastId, totalWidth: total };
  }, [orderedVisibleColumns, state.frozenIds, state.widths]);

  const stickyCellProps = useCallback(
    (id: TId, extraClassName?: string): { className?: string; style?: React.CSSProperties } => {
      const isSticky = Object.prototype.hasOwnProperty.call(stickyOffsets, id);
      const className =
        [extraClassName, isSticky ? 'is-sticky-col' : '', isSticky && lastStickyId === id ? 'is-sticky-last' : '']
          .filter(Boolean)
          .join(' ') || undefined;
      const style = isSticky ? { left: `${stickyOffsets[id]}px` } : undefined;
      return { className, style };
    },
    [stickyOffsets, lastStickyId],
  );

  const toggleColumnVisibility = useCallback(
    (id: TId) => {
      const col = columnMap.get(id);
      if (!col || col.locked) return;
      setState((prev) => {
        const nextVisible = new Set(prev.visibleIds);
        if (nextVisible.has(id)) {
          nextVisible.delete(id);
        } else {
          nextVisible.add(id);
        }
        return { ...prev, visibleIds: nextVisible };
      });
    },
    [columnMap],
  );

  const hideColumn = useCallback(
    (id: TId) => {
      const col = columnMap.get(id);
      if (!col || col.locked) return;
      setState((prev) => {
        if (!prev.visibleIds.has(id)) return prev;
        const nextVisible = new Set(prev.visibleIds);
        nextVisible.delete(id);
        return { ...prev, visibleIds: nextVisible };
      });
    },
    [columnMap],
  );

  const selectAllColumns = useCallback(() => {
    setState((prev) => ({
      ...prev,
      visibleIds: new Set(columns.map((col) => col.id)),
    }));
  }, [columns]);

  const deselectAllColumns = useCallback(() => {
    setState((prev) => {
      const nextVisible = new Set<TId>(columns.filter((col) => col.locked).map((col) => col.id));
      if (nextVisible.size === 0 && columns.length > 0) {
        nextVisible.add(columns[0].id);
      }
      return { ...prev, visibleIds: nextVisible };
    });
  }, [columns]);

  const toggleColumnFreeze = useCallback(
    (id: TId) => {
      if (!columnMap.has(id)) return;
      setState((prev) => {
        const nextFrozen = new Set(prev.frozenIds);
        const nextVisible = new Set(prev.visibleIds);
        if (nextFrozen.has(id)) {
          nextFrozen.delete(id);
        } else {
          nextFrozen.add(id);
          nextVisible.add(id);
        }
        return { ...prev, visibleIds: nextVisible, frozenIds: nextFrozen };
      });
    },
    [columnMap],
  );

  const clearFrozenColumns = useCallback(() => {
    setState((prev) => (prev.frozenIds.size === 0 ? prev : { ...prev, frozenIds: new Set<TId>() }));
  }, []);

  const setColumnWidth = useCallback(
    (id: TId, width: number) => {
      const col = columnMap.get(id);
      if (!col) return;
      const clamped = clampWidth(width, col.minWidth, col.maxWidth);
      setState((prev) => (prev.widths[id] === clamped ? prev : { ...prev, widths: { ...prev.widths, [id]: clamped } }));
    },
    [columnMap],
  );

  const autoFitColumn = useCallback(
    (id: TId, tableEl: HTMLTableElement | null) => {
      const col = columnMap.get(id);
      if (!col) return;
      const colIndex = orderedVisibleColumns.findIndex((item) => item.id === id);
      if (colIndex < 0) return;

      const pinReserve = state.frozenIds.has(id) ? 20 : 0;
      let widest = measureTextWidth(col.label, true) + 56 + pinReserve;

      if (tableEl) {
        const rows = tableEl.querySelectorAll('tbody tr');
        rows.forEach((row) => {
          const cell = row.children.item(colIndex);
          if (!cell) return;
          const divChildren = cell.querySelectorAll('div');
          if (divChildren.length > 0) {
            divChildren.forEach((line) => {
              const w = measureTextWidth((line.textContent ?? '').trim(), false) + 28;
              if (w > widest) widest = w;
            });
          } else {
            const w = measureTextWidth((cell.textContent ?? '').trim(), false) + 28;
            if (w > widest) widest = w;
          }
        });
      }

      setColumnWidth(id, Math.ceil(widest));
    },
    [columnMap, orderedVisibleColumns, state.frozenIds, setColumnWidth],
  );

  const resetLayout = useCallback(() => {
    setState(createDefaultState(columns));
  }, [columns]);

  return {
    columns,
    orderedVisibleColumns,
    visibleIds: state.visibleIds,
    frozenIds: state.frozenIds,
    widths: state.widths,
    stickyOffsets,
    lastStickyId,
    totalWidth,
    getThProps: stickyCellProps,
    getTdProps: stickyCellProps,
    toggleColumnVisibility,
    hideColumn,
    selectAllColumns,
    deselectAllColumns,
    toggleColumnFreeze,
    clearFrozenColumns,
    setColumnWidth,
    autoFitColumn,
    resetLayout,
  };
}

export function RosterColGroup<TId extends string>({ layout }: { layout: RosterTableLayoutState<TId> }) {
  return (
    <colgroup>
      {layout.orderedVisibleColumns.map((col) => (
        <col key={col.id} style={{ width: `${layout.widths[col.id] ?? col.defaultWidth}px` }} />
      ))}
    </colgroup>
  );
}

export function RosterColumnResizer<TId extends string>({
  columnId,
  label,
  layout,
  tableRef,
}: {
  columnId: TId;
  label: string;
  layout: RosterTableLayoutState<TId>;
  tableRef: React.RefObject<HTMLTableElement | null>;
}) {
  const [resizing, setResizing] = useState(false);
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => () => { cleanupRef.current?.(); }, []);

  const beginDrag = (startX: number, moveType: 'pointermove' | 'mousemove', upType: 'pointerup' | 'mouseup') => {
    cleanupRef.current?.();
    const startWidth = layout.widths[columnId] ?? 120;
    setResizing(true);

    const onMove = (moveEvent: PointerEvent | MouseEvent) => {
      layout.setColumnWidth(columnId, startWidth + (moveEvent.clientX - startX));
    };
    const cleanup = () => {
      setResizing(false);
      window.removeEventListener(moveType, onMove);
      window.removeEventListener(upType, cleanup);
      if (upType === 'pointerup') {
        window.removeEventListener('pointercancel', cleanup);
      }
      cleanupRef.current = null;
    };

    cleanupRef.current = cleanup;
    window.addEventListener(moveType, onMove);
    window.addEventListener(upType, cleanup);
    if (upType === 'pointerup') {
      window.addEventListener('pointercancel', cleanup);
    }
  };

  return (
    <div
      className={`roster-col-resizer${resizing ? ' is-resizing' : ''}`}
      aria-hidden="true"
      data-resizer-col={columnId}
      title={`拖曳調整「${label}」欄寬；雙擊自動貼合內容`}
      onPointerDown={(event) => {
        event.preventDefault();
        event.stopPropagation();
        beginDrag(event.clientX, 'pointermove', 'pointerup');
      }}
      onMouseDown={(event) => {
        if (cleanupRef.current) return;
        event.preventDefault();
        event.stopPropagation();
        beginDrag(event.clientX, 'mousemove', 'mouseup');
      }}
      onDoubleClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        layout.autoFitColumn(columnId, tableRef.current);
      }}
    />
  );
}

export function RosterColumnPicker<TId extends string>({
  layout,
  disabled = false,
}: {
  layout: RosterTableLayoutState<TId>;
  disabled?: boolean;
}) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef(false);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<React.CSSProperties>({ top: 0, left: 0 });

  const close = useCallback(() => {
    restoreFocusRef.current = true;
    setOpen(false);
  }, []);

  useEffect(() => {
    if (!open && !disabled && restoreFocusRef.current) {
      triggerRef.current?.focus();
      restoreFocusRef.current = false;
    }
  }, [open, disabled]);

  const reposition = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const width = Math.min(324, window.innerWidth - 16);
    const maxHeight = Math.min(440, window.innerHeight - 20);
    const panelHeight = Math.min(panelRef.current?.scrollHeight ?? 360, maxHeight);
    const left = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8));
    const top = Math.max(8, Math.min(rect.bottom + 6, window.innerHeight - panelHeight - 8));
    setPosition({ top, left, width, maxHeight });
  }, []);

  useLayoutEffect(() => {
    if (open) reposition();
  }, [open, reposition, layout.orderedVisibleColumns.length, layout.frozenIds.size]);

  useEffect(() => {
    if (!open) return;
    const handleOutside = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (!panelRef.current?.contains(target) && !triggerRef.current?.contains(target)) {
        close();
      }
    };
    document.addEventListener('pointerdown', handleOutside);
    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', reposition, true);
    return () => {
      document.removeEventListener('pointerdown', handleOutside);
      window.removeEventListener('resize', reposition);
      window.removeEventListener('scroll', reposition, true);
    };
  }, [open, close, reposition]);

  const groupedColumns = useMemo(() => {
    const groups: Array<{ name: string; columns: RosterColumnDefinition<TId>[] }> = [];
    const byName = new Map<string, RosterColumnDefinition<TId>[]>();
    for (const col of layout.columns) {
      let bucket = byName.get(col.group);
      if (!bucket) {
        bucket = [];
        byName.set(col.group, bucket);
        groups.push({ name: col.group, columns: bucket });
      }
      bucket.push(col);
    }
    return groups;
  }, [layout.columns]);

  return (
    <div className="roster-column-picker-controls">
      <button
        ref={triggerRef}
        type="button"
        className="roster-picker-trigger"
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => {
          if (open) close();
          else setOpen(true);
        }}
      >
        自訂顯示與凍結欄位 ({layout.orderedVisibleColumns.length}/{layout.columns.length}) ▾
      </button>
      <button
        type="button"
        className="roster-picker-reset"
        disabled={disabled}
        onClick={() => {
          setOpen(false);
          layout.resetLayout();
        }}
      >
        重設預設排版
      </button>
      {open && createPortal(
        <div
          ref={panelRef}
          className="roster-column-picker-popover"
          role="dialog"
          aria-label="自訂顯示與凍結欄位"
          style={position}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault();
              close();
            }
          }}
        >
          <div className="roster-picker-header">
            <strong>自訂顯示／凍結欄位</strong>
            <button type="button" onClick={close}>關閉</button>
          </div>
          <div className="roster-picker-actions">
            <button type="button" onClick={layout.selectAllColumns}>全選</button>
            <button type="button" onClick={layout.deselectAllColumns}>取消全選</button>
            <button type="button" className="roster-picker-clear-freeze" onClick={layout.clearFrozenColumns}>清除凍結</button>
          </div>
          <div className="roster-picker-groups">
            {groupedColumns.map((group) => (
              <div key={group.name} className="roster-picker-group">
                <div className="roster-picker-group-title">{group.name}</div>
                {group.columns.map((col) => {
                  const isVisible = layout.visibleIds.has(col.id);
                  const isFrozen = layout.frozenIds.has(col.id);
                  return (
                    <div key={col.id} className="roster-picker-item">
                      <label>
                        <input
                          type="checkbox"
                          checked={isVisible}
                          disabled={col.locked}
                          onChange={() => layout.toggleColumnVisibility(col.id)}
                        />
                        <span>{col.label}</span>
                        {col.locked && <span className="roster-picker-required">(必選)</span>}
                      </label>
                      <button
                        type="button"
                        className={`roster-pin-toggle-btn${isFrozen ? ' is-pinned' : ''}`}
                        aria-pressed={isFrozen}
                        aria-label={`${isFrozen ? '解除凍結' : '凍結'}${col.label}`}
                        onClick={() => layout.toggleColumnFreeze(col.id)}
                      >
                        {isFrozen ? '📌 已凍結' : '📌 凍結'}
                      </button>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
