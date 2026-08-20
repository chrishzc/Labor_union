/**
 * @file Drawer.tsx
 * @description 側邊抽屜彈窗元件，支援四種尺寸設定、ESC 鍵監聽中斷與自訂頁尾按鈕區。
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
}

export const Drawer: React.FC<DrawerProps> = ({
  isOpen,
  onClose,
  title,
  size = 'normal',
  children,
  footer
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div className={`drawer-container drawer-size-${size}`} onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <h2 className="drawer-title">{title}</h2>
          <button className="drawer-close-btn" onClick={onClose} aria-label="Close drawer">
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
