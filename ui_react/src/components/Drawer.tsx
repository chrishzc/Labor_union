/**
 * File: Drawer.tsx
 * Description: 側邊抽屜彈窗元件，支援尺寸、ESC、頁尾與結果未定時的關閉鎖定。
 */
import React, { useEffect } from 'react';
import './Drawer.css';

interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  size?: 'normal' | 'wide' | 'xl' | 'fullscreen';
  children: React.ReactNode;
  footer?: React.ReactNode;
  closeDisabled?: boolean;
}

export const Drawer: React.FC<DrawerProps> = ({
  isOpen,
  onClose,
  title,
  size = 'normal',
  children,
  footer,
  closeDisabled = false,
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen && !closeDisabled) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [closeDisabled, isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="drawer-backdrop" onClick={closeDisabled ? undefined : onClose}>
      <div className={`drawer-container drawer-size-${size}`} onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <h2 className="drawer-title">{title}</h2>
          <button className="drawer-close-btn" onClick={onClose} aria-label="Close drawer" disabled={closeDisabled}>
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
