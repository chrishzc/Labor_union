/**
 * File: Drawer.tsx
 * Description: 側邊抽屜彈窗元件，支援尺寸、ESC、頁尾與結果未定時的關閉鎖定。
 */
import React, { useEffect, useId, useRef } from 'react';
import './Drawer.css';

interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  size?: 'normal' | 'wide' | 'xl' | 'fullscreen';
  children: React.ReactNode;
  footer?: React.ReactNode;
  closeDisabled?: boolean;
  closeLabel?: string;
  ariaLabel?: string;
  className?: string;
}

export const Drawer: React.FC<DrawerProps> = ({
  isOpen,
  onClose,
  title,
  size = 'normal',
  children,
  footer,
  closeDisabled = false,
  closeLabel = 'Close drawer',
  ariaLabel,
  className,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  const titleId = useId();

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    document.body.classList.add('modal-open');
    const focusableSelector = 'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])';
    const focusableElements = () => Array.from(
      containerRef.current?.querySelectorAll<HTMLElement>(focusableSelector) ?? [],
    );
    const firstTarget = focusableElements()[0] ?? containerRef.current;
    window.requestAnimationFrame(() => firstTarget?.focus());

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen && !closeDisabled) {
        onCloseRef.current();
      }
      if (e.key === 'Tab') {
        const elements = focusableElements();
        if (elements.length === 0) {
          e.preventDefault();
          containerRef.current?.focus();
          return;
        }
        const first = elements[0];
        const last = elements[elements.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.classList.remove('modal-open');
      previousFocus?.focus();
    };
  }, [closeDisabled, isOpen]);

  if (!isOpen) return null;

  return (
    <div
      className={`drawer-backdrop${className ? ` ${className}` : ''}`}
      onClick={closeDisabled ? undefined : onClose}
    >
      <div
        ref={containerRef}
        className={`drawer-container drawer-size-${size}`}
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel}
        aria-labelledby={ariaLabel ? undefined : titleId}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="drawer-header">
          <h2 className="drawer-title" id={titleId}>{title}</h2>
          <button className="drawer-close-btn" onClick={onClose} aria-label={closeLabel} disabled={closeDisabled}>
            ✕
          </button>
        </div>
        <div className="drawer-body">
          {children}
        </div>
        {footer && (
          <div className="drawer-footer">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
};

export default Drawer;
