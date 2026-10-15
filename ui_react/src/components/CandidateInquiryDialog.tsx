import { useLayoutEffect, useRef, type MouseEvent, type ReactNode } from 'react';

/** Native modal for candidate search and shared order information. */
export function CandidateInquiryDialog({ title, busy = false, onClose, children, wide = false, side = false }: {
  title: string; busy?: boolean; onClose: () => void; children: ReactNode; wide?: boolean; side?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const origin = useRef<HTMLElement | null>(null);
  const backdropPointer = useRef<number | null>(null);
  const isBackdrop = (event: MouseEvent<HTMLDialogElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return event.target === event.currentTarget && (
      event.clientX < bounds.left || event.clientX > bounds.right ||
      event.clientY < bounds.top || event.clientY > bounds.bottom
    );
  };
  useLayoutEffect(() => {
    const modal = dialog.current;
    origin.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    modal?.showModal();
    return () => { modal?.close(); origin.current?.focus(); };
  }, []);
  return <dialog ref={dialog} className={`candidate-inquiry-dialog${wide ? ' wide' : ''}${side ? ' side' : ''}`} aria-label={title}
    onPointerDown={event => {
      backdropPointer.current = !busy && event.button === 0 && isBackdrop(event) ? event.pointerId : null;
    }}
    onPointerUp={event => {
      if (busy || backdropPointer.current !== event.pointerId || !isBackdrop(event)) backdropPointer.current = null;
    }}
    onClick={event => {
      const startedOnBackdrop = backdropPointer.current !== null;
      backdropPointer.current = null;
      if (!busy && startedOnBackdrop && isBackdrop(event)) onClose();
    }}
    onPointerCancel={() => { backdropPointer.current = null; }}
    onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <header className="candidate-inquiry-dialog-heading"><h2>{title}</h2><button type="button" disabled={busy} onClick={onClose}>關閉</button></header>
    {children}
  </dialog>;
}
